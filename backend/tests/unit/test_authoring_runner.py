"""The authoring runner on an in-memory database (005 design 3.9)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from tests.fixtures.fake_clients import FixedAiConfig
from app.services.ai_settings import load_ai_config
from app.config import Settings
from app.db.base import utcnow
from app.db.models import AuthoringRunRow, ChapterRow
from app.db.repositories import Repositories
from app.domain.errors import (
    AuthoringBusy,
    AuthoringQuota,
    AuthoringRunning,
    DocumentNeeded,
    NothingToRetry,
    ProviderUnavailable,
)
from app.domain.progress import Progress
from app.services.authoring.agent import AuthoringAgent
from app.services.authoring.runner import AuthoringRunner
from app.services.documents import Document, PageImage
from app.services.prompts import PromptLibrary
from tests.fixtures.fake_completion import FakeCompletion, data, text
from tests.unit.test_authoring_agent import CURRICULUM, PACK

PROMPTS = PromptLibrary(Path(__file__).resolve().parents[2] / "prompts")
AUTHOR = [text(PACK), data(CURRICULUM)]


def read(material: str = "matériel", pages: int = 1):
    return text("\n".join(f"--- page {n} ---\n{material}" for n in range(1, pages + 1)))


GOOD = [read(), *AUTHOR]


def document(pages: int = 1) -> Document:
    return Document("images", [PageImage(n, b"\xff\xd8\xff") for n in range(1, pages + 1)], 3 * pages)


async def new_chapter(r: AuthoringRunner, user, course, pages: int = 1):
    return await r.start_document(user, course, None, document(pages))


@pytest.fixture
def world(repos: Repositories):
    user = repos.users.create("a@b.be", "Léa", "h")
    course = repos.courses.create(user.id, "Maths", "mathematics", max_courses=30)
    return repos, user, course


def runner(repos: Repositories, script, delay_s: float = 0.0, **overrides) -> tuple[AuthoringRunner, FakeCompletion]:
    fake = FakeCompletion(script, delay_s=delay_s)
    settings = Settings(openai_api_key="k", _env_file=None, **overrides)
    ai = FixedAiConfig(load_ai_config(settings))
    return AuthoringRunner(AuthoringAgent(fake, PROMPTS, settings, ai), repos, settings, ai), fake  # type: ignore[arg-type]


def runs(db_engine) -> list[AuthoringRunRow]:
    with Session(db_engine) as s:
        return list(s.scalars(select(AuthoringRunRow).order_by(AuthoringRunRow.started_at)))


async def test_new_chapter_is_generating_then_adopted(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, GOOD)
    chapter = await new_chapter(r, user, course)
    assert chapter.authoring_state == "generating" and not chapter.ready and chapter.source_kind == "document"
    assert chapter.authoring_stage == "transcription" and chapter.page_count == 1
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned and owned.chapter.ready and owned.chapter.content_version == 1
    assert owned.chapter.authoring_state == "idle" and owned.chapter.title == "Les fonctions du premier degré"
    assert owned.chapter.curriculum and owned.chapter.curriculum["id"] == chapter.id
    (run,) = runs(db_engine)
    assert run.state == "succeeded" and run.trigger == "create" and run.attempts_pack == 1
    assert run.input_tokens == 280 and run.cost_estimate_usd > 0 and run.finished_at is not None


async def test_failure_marks_chapter_and_run_then_retry_succeeds(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, [read(), ProviderUnavailable(), *AUTHOR])
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned and owned.chapter.authoring_state == "failed" and owned.chapter.authoring_error == "provider"
    assert runs(db_engine)[0].state == "failed" and runs(db_engine)[0].stage == "pack"
    await r.start_retry(user, owned)
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned and owned.chapter.ready and owned.chapter.authoring_state == "idle"
    assert [run.trigger for run in runs(db_engine)] == ["create", "retry"]


async def test_retry_needs_a_failed_chapter(world):
    repos, user, course = world
    r, _ = runner(repos, GOOD)
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    with pytest.raises(NothingToRetry):
        await r.start_retry(user, repos.chapters.get_owned(user.id, course.id, chapter.id))


async def test_source_edit_keeps_previous_content_until_success_and_on_failure(world):
    repos, user, course = world
    r, _ = runner(repos, [*GOOD, ProviderUnavailable()], delay_s=0.01)
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    repos.progress.save(user.id, chapter.id, Progress(active="definition"))

    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    editing = await r.start_source_edit(user, owned, "v2")
    assert editing.authoring_state == "generating" and editing.ready and editing.content_version == 1
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id, source=True)
    assert owned.chapter.authoring_state == "failed" and owned.chapter.content_version == 1
    assert owned.chapter.pack == PACK and owned.chapter.source_text == "v2"
    assert repos.progress.load(user.id, chapter.id) is not None  # nothing adopted, nothing reset


async def test_successful_source_edit_resets_progress(world):
    repos, user, course = world
    r, _ = runner(repos, [*GOOD, *AUTHOR])
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    repos.progress.save(user.id, chapter.id, Progress(active="definition"))
    await r.start_source_edit(user, repos.chapters.get_owned(user.id, course.id, chapter.id), "v2")
    await r.wait_idle()
    assert repos.chapters.get_owned(user.id, course.id, chapter.id).chapter.content_version == 2
    assert repos.progress.load(user.id, chapter.id) is None


async def test_per_student_concurrency_limit(world):
    repos, user, course = world
    r, _ = runner(repos, [*GOOD, *GOOD], delay_s=0.05, authoring_concurrent_per_student=2)
    await new_chapter(r, user, course)
    await new_chapter(r, user, course)
    with pytest.raises(AuthoringBusy) as exc:
        await new_chapter(r, user, course)
    assert "2 chapitres" in exc.value.message()
    await r.wait_idle()
    other = repos.users.create("b@b.be", "B", "h")
    assert repos.runs.running_for_user(other.id) == 0


async def test_daily_quota_counts_runs_in_the_table(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, GOOD, authoring_runs_per_day=2, timezone="UTC")
    old = utcnow() - timedelta(hours=23)
    with Session(db_engine) as s:
        for i in range(2):
            s.add(AuthoringRunRow(id=f"r{i}", user_id=user.id, chapter_id=None, trigger="create", state="succeeded", model="m", started_at=old + timedelta(minutes=i)))
        s.commit()
    with pytest.raises(AuthoringQuota) as exc:
        await new_chapter(r, user, course)
    assert (old + timedelta(hours=24)).strftime("%H:%M") in exc.value.message()
    assert repos.courses.detail(user.id, course.id).chapters == []


async def test_a_generating_chapter_cannot_be_started_again(world):
    repos, user, course = world
    r, _ = runner(repos, GOOD, delay_s=0.05)
    chapter = await new_chapter(r, user, course)
    stale = repos.chapters.get_owned(user.id, course.id, chapter.id)
    with pytest.raises(AuthoringRunning):
        await r.start_source_edit(user, stale, "b")
    await r.wait_idle()
    # Even from a stale read (state idle on the caller's side), the repository refuses.
    with Session(repos.courses._factory.kw["bind"]) as s:
        s.execute(update(ChapterRow).where(ChapterRow.id == chapter.id).values(authoring_state="generating"))
        s.commit()
    with pytest.raises(AuthoringRunning):
        repos.chapters.begin_authoring(
            user_id=user.id, course_id=course.id, chapter_id=chapter.id, source_text="c",
            trigger="source_edit", model="m", max_chapters=40,
        )


async def test_run_timeout(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, GOOD, delay_s=0.2, authoring_timeout_s=10)
    r._settings.authoring_timeout_s = 0.05  # below the settings minimum, for the test only
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned.chapter.authoring_error == "timeout" and runs(db_engine)[0].error_code == "timeout"


async def test_wait_idle_returns_when_a_run_has_just_finished(world, monkeypatch):
    # A rare hang of the suite: a run finished and the test resumed in the same loop
    # pass, before the run's done callback had taken it out of the set.
    repos, _, _ = world
    r, _ = runner(repos, [])

    async def finished() -> None:
        return None

    task = asyncio.create_task(finished())
    r._tasks.add(task)
    task.add_done_callback(r._tasks.discard)
    await asyncio.sleep(0)  # the task runs first in this pass; its callback waits for the next
    assert task.done() and task in r._tasks

    real, calls = asyncio.gather, []

    def gather(*futures, **kwargs):
        calls.append(futures)
        assert len(calls) < 10, "wait_idle spins on a finished run"
        return real(*futures, **kwargs)

    monkeypatch.setattr(asyncio, "gather", gather)
    await r.wait_idle()
    assert not r._tasks


async def test_shutdown_interrupts_running_runs(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, GOOD, delay_s=1.0)
    chapter = await new_chapter(r, user, course)
    await asyncio.sleep(0.01)
    await r.shutdown()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned.chapter.authoring_error == "interrupted" and runs(db_engine)[0].state == "failed"


async def test_fail_orphans_at_startup(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, GOOD)
    repos.chapters.begin_authoring(
        user_id=user.id, course_id=course.id, chapter_id=None, source_text="a", trigger="create", model="m", max_chapters=40
    )
    assert r.fail_orphans() == 1
    assert runs(db_engine)[0].error_code == "interrupted"


async def test_chapter_deleted_mid_run_is_discarded(world, db_engine, caplog):
    repos, user, course = world
    r, _ = runner(repos, GOOD, delay_s=0.05)
    chapter = await new_chapter(r, user, course)
    assert repos.chapters.delete(user.id, course.id, chapter.id)
    with caplog.at_level("INFO"):
        await r.wait_idle()
    (run,) = runs(db_engine)
    assert run.chapter_id is None and run.state == "failed" and run.error_code == "discarded"
    assert any(rec.getMessage() == "authoring_discarded" for rec in caplog.records)


async def test_logs_never_carry_content(world, caplog):
    repos, user, course = world
    broken = PACK.replace("## 5. Vocabulaire", "## 5. SECRET-CONTENT")
    r, _ = runner(repos, [read("matériel SECRET-SOURCE"), *[text(broken)] * 3])
    with caplog.at_level("INFO"):
        await new_chapter(r, user, course)
        await r.wait_idle()
    dump = " ".join(str(rec.__dict__) for rec in caplog.records)
    assert "SECRET-CONTENT" not in dump and "SECRET-SOURCE" not in dump
    assert any(rec.getMessage() == "authoring_failed" for rec in caplog.records)



async def test_retry_on_a_running_chapter_says_it_is_running(world):
    repos, user, course = world
    r, _ = runner(repos, GOOD, delay_s=0.05)
    chapter = await new_chapter(r, user, course)
    with pytest.raises(AuthoringRunning):
        await r.start_retry(user, repos.chapters.get_owned(user.id, course.id, chapter.id))
    await r.wait_idle()


async def test_an_internal_error_logs_its_type_only(world, caplog, monkeypatch):
    repos, user, course = world
    r, _ = runner(repos, GOOD)

    def boom(*_args, **_kwargs):
        raise RuntimeError("INSERT … parameters: ('# SECRET-PACK-CONTENT',)")

    monkeypatch.setattr(repos.chapters, "adopt_authored", boom)
    with caplog.at_level("INFO"):
        chapter = await new_chapter(r, user, course)
        await r.wait_idle()
    dump = " ".join(str(rec.__dict__) for rec in caplog.records)
    assert "SECRET-PACK-CONTENT" not in dump
    internal = next(rec for rec in caplog.records if rec.getMessage() == "authoring_internal_error")
    assert internal.error == "RuntimeError" and internal.exc_info is None
    assert repos.chapters.get_owned(user.id, course.id, chapter.id).chapter.authoring_error == "internal"


async def test_run_logs_carry_course_and_usage(world, caplog):
    repos, user, course = world
    r, _ = runner(repos, GOOD)
    with caplog.at_level("INFO"):
        await new_chapter(r, user, course)
        await r.wait_idle()
    done = next(rec for rec in caplog.records if rec.getMessage() == "authoring_succeeded")
    assert done.course_id == course.id and done.input_tokens == 280 and hasattr(done, "pack_ms")
    stages = [rec for rec in caplog.records if rec.getMessage() == "authoring_stage"]
    assert stages and all(hasattr(rec, "ms") for rec in stages)


# ---------------------------------------------------------------- documents (006)


async def test_document_progress_is_written_per_batch_then_the_transcription_stored(world, db_engine, monkeypatch):
    repos, user, course = world
    r, _ = runner(
        repos, [text("--- page 1 ---\nun"), text("--- page 2 ---\ndeux"), *AUTHOR],
        transcription_batch_pages=1, transcription_concurrency=1,
    )
    progress: list[tuple] = []
    real = repos.chapters.set_progress
    monkeypatch.setattr(repos.chapters, "set_progress", lambda *a: (progress.append(a[1:]), real(*a))[1])
    chapter = await new_chapter(r, user, course, pages=2)
    await r.wait_idle()
    assert progress == [("transcription", 1), ("transcription", 2), ("curriculum", None)]
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id, source=True)
    assert owned.chapter.ready and owned.chapter.source_kind == "document" and owned.chapter.authoring_stage is None
    assert owned.chapter.source_text == "--- page 1 ---\n\nun\n\n--- page 2 ---\n\ndeux\n"
    assert repos.chapters.uploads(chapter.id) == [(1, 2)]
    (run,) = runs(db_engine)
    assert run.source_kind == "document" and run.page_count == 2 and run.attempts_transcription == 2
    assert run.transcription_ms >= 0 and run.transcription_cost_usd > 0


async def test_pack_failure_keeps_the_transcription_and_retry_starts_from_pack(world, db_engine):
    repos, user, course = world
    r, fake = runner(repos, [read("[manuscrit] 12 [illisible]"), ProviderUnavailable(), *AUTHOR])
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id, source=True)
    assert owned.chapter.authoring_state == "failed" and owned.chapter.authoring_stage == "pack"
    assert owned.chapter.source_text == "--- page 1 ---\n\n[manuscrit] 12 [illisible]\n"
    run = runs(db_engine)[0]
    assert (run.stage, run.handwritten_marks, run.illegible_marks) == ("pack", 1, 1)
    calls = len(fake.calls)
    await r.start_retry(user, owned)
    await r.wait_idle()
    assert repos.chapters.get_owned(user.id, course.id, chapter.id).chapter.ready
    assert len(fake.calls) == calls + 2  # pack and curriculum: no page read again
    assert [run.trigger for run in runs(db_engine)] == ["create", "retry"]


async def test_transcription_failure_leaves_the_source_and_retry_needs_the_document(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, [text("pas de marqueur")] * 2)
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id, source=True)
    assert owned.chapter.authoring_error == "transcription_failed"
    assert owned.chapter.authoring_stage == "transcription" and owned.chapter.source_text == ""
    assert runs(db_engine)[0].stage == "transcription" and repos.chapters.uploads(chapter.id) == []
    with pytest.raises(DocumentNeeded) as exc:
        await r.start_retry(user, owned)
    assert exc.value.code == "document_needed" and len(runs(db_engine)) == 1


async def test_replacing_a_document_keeps_the_old_source_until_the_new_one_is_read(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, [*GOOD, text("--- page 1 ---\nnouveau")], delay_s=0.02)
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    replacing = await r.start_document(user, course, owned.chapter, document())
    assert replacing.source_text == "--- page 1 ---\n\nmatériel\n" and replacing.authoring_stage == "transcription"
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id, source=True)
    assert owned.chapter.source_text == "--- page 1 ---\n\nnouveau\n" and owned.chapter.content_version == 1
    assert [run.trigger for run in runs(db_engine)] == ["create", "replace"]


async def test_a_timeout_after_the_transcription_is_stored_keeps_it_retryable(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, [read(), *AUTHOR], delay_s=0.2)
    r._settings.authoring_timeout_s = 0.3  # below the settings minimum, for the test only
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id, source=True)
    assert owned.chapter.authoring_error == "timeout" and owned.chapter.authoring_stage == "pack"
    assert not owned.chapter.needs_document and runs(db_engine)[0].stage == "pack"


# ---------------------------------------------------------------- spec 016: progress and why a run failed

from app.domain.errors import CallDiagnostics, ProviderTimeout  # noqa: E402
from tests.fixtures.fake_completion import streamed  # noqa: E402


def quiet_provider() -> ProviderTimeout:
    error = ProviderTimeout()
    error.diagnostics = CallDiagnostics("StreamTimeout", "idle_timeout", None, 61_000, 60_000, 4200, None, "req_9")
    return error


async def test_a_provider_that_went_quiet_fails_the_run_as_a_timeout_and_the_log_says_why(world, db_engine, caplog):
    repos, user, course = world
    r, _ = runner(repos, [read(), quiet_provider()])
    with caplog.at_level("INFO"):
        chapter = await new_chapter(r, user, course)
        await r.wait_idle()
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned.chapter.authoring_error == "timeout" and runs(db_engine)[0].error_code == "timeout"
    (line,) = [rec for rec in caplog.records if rec.getMessage() == "authoring_failed"]
    assert (line.code, line.stage, line.error_class, line.reason) == ("timeout", "pack", "StreamTimeout", "idle_timeout")
    assert (line.idle_ms, line.received_chars, line.provider_request_id) == (60_000, 4200, "req_9")


async def test_another_provider_failure_stays_a_provider_failure(world, caplog):
    repos, user, course = world
    r, _ = runner(repos, [read(), ProviderUnavailable()])
    with caplog.at_level("INFO"):
        chapter = await new_chapter(r, user, course)
        await r.wait_idle()
    assert repos.chapters.get_owned(user.id, course.id, chapter.id).chapter.authoring_error == "provider"
    (line,) = [rec for rec in caplog.records if rec.getMessage() == "authoring_failed"]
    assert line.code == "provider" and not hasattr(line, "reason")  # a bare exception carries no diagnostics


async def test_the_run_ceiling_is_logged_as_such(world, caplog):
    repos, user, course = world
    r, _ = runner(repos, GOOD, delay_s=0.2, authoring_timeout_s=10)
    r._settings.authoring_timeout_s = 0.05
    with caplog.at_level("INFO"):
        await new_chapter(r, user, course)
        await r.wait_idle()
    (line,) = [rec for rec in caplog.records if rec.getMessage() == "authoring_failed"]
    assert (line.code, line.reason) == ("timeout", "run_ceiling")


async def test_the_chapter_row_shows_the_pack_arriving_while_it_is_written(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, [read(), streamed(text(PACK), 5000, hold_s=0.3), streamed(data(CURRICULUM), 10)])
    chapter = await new_chapter(r, user, course)
    seen: list[tuple[str | None, int]] = []
    for _ in range(40):
        await asyncio.sleep(0.02)
        row = repos.chapters.get_owned(user.id, course.id, chapter.id).chapter
        seen.append((row.authoring_stage, row.authoring_received_chars))
    await r.wait_idle()
    assert ("pack", 5000) in seen
    done = repos.chapters.get_owned(user.id, course.id, chapter.id).chapter
    assert done.authoring_state == "idle" and done.authoring_received_chars == 0 and done.authoring_progress_at is None


async def test_a_failed_run_leaves_no_count_behind(world):
    repos, user, course = world
    r, _ = runner(repos, [read(), streamed(ProviderUnavailable(), 800)])
    chapter = await new_chapter(r, user, course)
    await r.wait_idle()
    row = repos.chapters.get_owned(user.id, course.id, chapter.id).chapter
    assert row.authoring_state == "failed" and row.authoring_received_chars == 0 and row.authoring_progress_at is None


async def test_a_cancelled_run_is_interrupted_and_its_writer_is_closed(world, db_engine):
    repos, user, course = world
    r, _ = runner(repos, [read(), streamed(text(PACK), 100)], delay_s=60)
    chapter = await new_chapter(r, user, course)
    await asyncio.sleep(0.05)
    await r.shutdown()
    row = repos.chapters.get_owned(user.id, course.id, chapter.id).chapter
    assert row.authoring_error == "interrupted" and runs(db_engine)[0].error_code == "interrupted"
    assert row.authoring_received_chars == 0


async def test_the_progress_lines_never_carry_content(world, caplog):
    repos, user, course = world
    broken = PACK.replace("## 5. Vocabulaire", "## 5. SECRET-CONTENT")
    r, _ = runner(repos, [read("matériel SECRET-SOURCE"), streamed(text(broken), 99), *[text(broken)] * 2])
    r._settings.authoring_progress_log_s = 0  # every snapshot is « due »
    with caplog.at_level("DEBUG"):
        await new_chapter(r, user, course)
        await r.wait_idle()
    assert [rec for rec in caplog.records if rec.getMessage() == "provider_call_progress"]
    dump = " ".join(str(rec.__dict__) for rec in caplog.records)
    assert "SECRET-SOURCE" not in dump and "SECRET-CONTENT" not in dump
