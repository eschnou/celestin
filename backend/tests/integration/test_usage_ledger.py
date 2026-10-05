"""Spec 015 R1, R2: through the app, every call a student or an administrator causes lands in the ledger, for
them, with the course and chapter when there are some. The clients are scripted fakes behind the real hub, so the
recording wrappers, the scopes and the repository are the real ones."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine

from app.db.repositories import CallFilters, Period
from app.main import create_app
from app.providers.base import Completed, TextDelta
from app.providers.hub import Clients
from app.services.documents import DocumentService
from tests.conftest import CARD, CHAPTER_ID, COURSE_ID, LESSON, http_client, sign_in, tool_call
from tests.fixtures.documents import page_image
from tests.fixtures.fake_completion import FakeCompletion, data, text
from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.fake_realtime import FakeRealtime
from tests.fixtures.fake_transcriber import FakeTranscriber
from tests.unit.test_authoring_agent import CURRICULUM, PACK

USAGE = {"input_tokens": 100, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 40}}
SOURCE = "Chapitre : les fonctions du premier degré. " * 20


class Scripted:
    """A client factory whose fakes are scripted per test."""

    def __init__(self, tutor=(), authoring=(), transcription=()) -> None:
        self.llm = FakeLLM(list(tutor))
        self.authoring = FakeCompletion(list(authoring))
        self.transcription = FakeCompletion(list(transcription))
        self.transcriber = FakeTranscriber()

    def __call__(self, settings, config) -> Clients:
        return Clients(
            config=config,
            tutor=self.llm,  # type: ignore[arg-type]
            authoring=self.authoring,  # type: ignore[arg-type]
            transcription=self.transcription,  # type: ignore[arg-type]
            realtime=FakeRealtime(),
            transcriber=self.transcriber if config.dictation else None,
        )


async def ledger(app) -> list:
    """The entries written so far, oldest first."""
    await app.state.usage_recorder.drain()
    calls, more = app.state.repos.ai_usage.calls(Period(), CallFilters(), limit=200)
    assert not more
    return [c.entry for c in reversed(calls)]


@pytest.fixture
def app_with_routes(settings, db_engine: Engine):
    return create_app(settings, engine=db_engine)


@pytest.fixture
def make_app(settings, db_engine: Engine):
    def _make(scripted: Scripted):
        app = create_app(settings, engine=db_engine, client_factory=scripted)
        app.state.documents = DocumentService(app.state.settings, executor=ThreadPoolExecutor(1))
        return app

    return _make


async def test_a_turn_is_a_row_per_round_for_the_student(make_app) -> None:
    scripted = Scripted(tutor=[
        [tool_call("display_board", {"card": CARD}), Completed(usage=USAGE)],
        [TextDelta("Tu suis ?"), Completed(usage=USAGE)],
    ])
    app = make_app(scripted)
    student, headers = sign_in(app)
    async with http_client(app, headers) as client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    assert r.status_code == 200
    first, second = await ledger(app)
    for entry in (first, second):
        assert (entry.user_id, entry.course_id, entry.chapter_id) == (student["id"], COURSE_ID, CHAPTER_ID)
        assert (entry.role, entry.feature, entry.status, entry.input_tokens, entry.cached_tokens) == ("tutor", "tutor_turn", "ok", 100, 40)
        assert entry.model == app.state.hub.config.tutor.model and entry.provider == "api.openai.com"
    assert first.correlation_id == second.correlation_id and first.correlation_id


async def test_a_document_run_is_attributed_to_its_owner_in_the_background(make_app) -> None:
    scripted = Scripted(authoring=[text(PACK), data(CURRICULUM)], transcription=[text(f"--- page 1 ---\n{SOURCE}")])
    app = make_app(scripted)
    student, headers = sign_in(app, lesson=False)
    async with http_client(app, headers) as client:
        course = (await client.post("/api/courses", json={"name": "Maths", "subject": "mathematics"})).json()["id"]
        files = [("files", ("IMG_1.jpg", page_image(text="Page 1"), "image/jpeg"))]
        r = await client.post(f"/api/courses/{course}/chapters", files=files)
        assert r.status_code == 202
        chapter = r.json()["id"]
        await app.state.authoring.wait_idle()
    entries = await ledger(app)
    assert [(e.role, e.feature) for e in entries] == [
        ("transcription", "document_reading"), ("authoring", "authoring"), ("authoring", "authoring"),
    ]
    assert {(e.user_id, e.course_id, e.chapter_id) for e in entries} == {(student["id"], course, chapter)}
    assert len({e.correlation_id for e in entries}) == 1 and entries[0].correlation_id
    assert [e.status for e in entries] == ["ok"] * 3


async def test_a_repair_call_and_a_failed_stage_each_leave_their_own_row(make_app) -> None:
    from app.domain.errors import ProviderTimeout

    repaired = Scripted(
        authoring=[text("# not a pack"), text(PACK), data(CURRICULUM)], transcription=[text(f"--- page 1 ---\n{SOURCE}")]
    )
    failing = Scripted(authoring=[ProviderTimeout()], transcription=[text(f"--- page 1 ---\n{SOURCE}")])
    seen = []
    for scripted in (repaired, failing):
        app = make_app(scripted)
        _, headers = sign_in(app, lesson=False)
        async with http_client(app, headers) as client:
            course = (await client.post("/api/courses", json={"name": "Maths", "subject": "mathematics"})).json()["id"]
            files = [("files", ("IMG_1.jpg", page_image(text="Page 1"), "image/jpeg"))]
            await client.post(f"/api/courses/{course}/chapters", files=files)
            await app.state.authoring.wait_idle()
        rows = [(e.feature, e.status, e.error_code) for e in await ledger(app)]  # the engine is shared: earlier rows too
        seen.append(rows[sum(len(r) for r in seen):])
    # The repair is a call of its own: the invalid pack, the corrected one, the curriculum.
    assert seen[0] == [("document_reading", "ok", None)] + [("authoring", "ok", None)] * 3
    assert seen[1] == [("document_reading", "ok", None), ("authoring", "failed", "provider_timeout")]


async def test_a_dictation_is_a_voice_row_with_its_length_and_no_tokens(make_app) -> None:
    app = make_app(Scripted())
    student, headers = sign_in(app)
    async with http_client(app, headers) as client:
        r = await client.post(
            "/api/dictation",
            files={"audio": ("d.webm", b"\x1a\x45 audio", "audio/webm")},
            data={"language": "fr", "duration_ms": "4200"},
        )
    assert r.status_code == 200
    (entry,) = await ledger(app)
    assert (entry.user_id, entry.role, entry.feature, entry.audio_seconds) == (student["id"], "voice", "dictation", 4.2)
    assert (entry.course_id, entry.input_tokens, entry.cost_usd, entry.status) == (None, None, None, "ok")
    assert entry.model == app.state.hub.config.dictation.model


async def test_a_dictation_is_capped_like_its_log_line(make_app) -> None:
    app = make_app(Scripted())
    _, headers = sign_in(app)
    async with http_client(app, headers) as client:
        await client.post("/api/dictation", files={"audio": ("d.webm", b"x", "audio/webm")}, data={"duration_ms": "3600000"})
    (entry,) = await ledger(app)
    assert entry.audio_seconds == float(app.state.settings.dictation_max_s)


async def test_a_photo_of_work_is_a_row_for_the_course(make_app) -> None:
    app = make_app(Scripted(transcription=[text("$x = 3$", USAGE)]))
    student, headers = sign_in(app)
    async with http_client(app, headers) as client:
        r = await client.post(f"/api/courses/{COURSE_ID}/work", files={"photo": ("w.jpg", page_image(text="x = 3"), "image/jpeg")})
    assert r.status_code == 200
    (entry,) = await ledger(app)
    assert (entry.user_id, entry.course_id, entry.chapter_id) == (student["id"], COURSE_ID, None)
    assert (entry.role, entry.feature, entry.input_tokens) == ("transcription", "work_reading", 100)


async def test_a_failing_provider_is_a_failed_row_and_the_usual_answer(make_app) -> None:
    from app.domain.errors import ProviderUnavailable

    app = make_app(Scripted(transcription=[ProviderUnavailable()]))
    _, headers = sign_in(app)
    async with http_client(app, headers) as client:
        r = await client.post(f"/api/courses/{COURSE_ID}/work", files={"photo": ("w.jpg", page_image(text="x"), "image/jpeg")})
    assert r.status_code == 502
    (entry,) = await ledger(app)
    assert (entry.status, entry.error_code) == ("failed", "provider_unavailable")


async def test_the_admins_live_checks_are_rows_for_the_admin(settings, db_engine: Engine) -> None:
    from tests.fixtures.fake_clients import PassingFactory
    from tests.fixtures.fake_probe import FakeProbe

    app = create_app(settings, engine=db_engine, probe=FakeProbe(), client_factory=PassingFactory())
    admin, headers = sign_in(app, email="root@example.be", name="Root", role="admin", lesson=False)
    async with http_client(app, headers) as client:
        r = await client.post("/api/admin/ai/test", json={"live": True})
    assert r.status_code == 200
    entries = await ledger(app)
    assert {(e.user_id, e.feature) for e in entries} == {(admin["id"], "ai_test")}
    assert {e.role for e in entries} == {"tutor", "authoring", "transcription"}  # the secret mint is not a call
    # The tutor check leaves as soon as it has its tool call: the rest of the answer is not wanted.
    assert next(e for e in entries if e.role == "tutor").status == "cancelled"


async def test_a_call_without_a_user_is_not_recorded(make_app) -> None:
    """The startup and script paths hold no scope."""
    app = make_app(Scripted(authoring=[text("x")]))
    await app.state.hub.authoring_llm.complete(role="authoring", instructions=[], input=[], max_output_tokens=1)
    assert await ledger(app) == []


async def test_a_ledger_that_cannot_be_written_does_not_touch_the_lesson(make_app, monkeypatch, caplog) -> None:
    app = make_app(Scripted(tutor=[[TextDelta("Salut"), Completed(usage=USAGE)]]))

    def boom(entry) -> None:  # noqa: ANN001
        raise RuntimeError("database is locked")

    monkeypatch.setattr(app.state.usage_recorder, "_write", boom)
    _, headers = sign_in(app)
    async with http_client(app, headers) as client:
        with caplog.at_level("ERROR"):
            r = await client.post("/api/chat", json={**LESSON, "history": []})
            await app.state.usage_recorder.drain()
            health = await client.get("/api/health")
    assert r.status_code == 200 and "turn.end" in r.text and health.json()["status"] == "ok"
    assert any(rec.getMessage() == "ai_usage_not_stored" for rec in caplog.records)
    assert "database is locked" not in caplog.text


async def test_a_run_cut_by_its_timeout_leaves_a_cancelled_row(settings, db_engine: Engine) -> None:
    """The call in flight when the run's own timeout fires was sent and is billed: it is a row, `cancelled`."""
    scripted = Scripted(authoring=[text(PACK), data(CURRICULUM)], transcription=[text(f"--- page 1 ---\n{SOURCE}")])
    scripted.authoring.delay_s = 5
    app = create_app(settings.model_copy(update={"authoring_timeout_s": 0.3}), engine=db_engine, client_factory=scripted)
    app.state.documents = DocumentService(app.state.settings, executor=ThreadPoolExecutor(1))
    student, headers = sign_in(app, lesson=False)
    async with http_client(app, headers) as client:
        course = (await client.post("/api/courses", json={"name": "Maths", "subject": "mathematics"})).json()["id"]
        files = [("files", ("IMG_1.jpg", page_image(text="Page 1"), "image/jpeg"))]
        await client.post(f"/api/courses/{course}/chapters", files=files)
        await app.state.authoring.wait_idle()
    entries = await ledger(app)
    assert [(e.feature, e.status) for e in entries] == [("document_reading", "ok"), ("authoring", "cancelled")]
    assert {e.user_id for e in entries} == {student["id"]}


def test_the_usage_routes_are_among_the_routes_the_guard_test_visits(app_with_routes) -> None:
    from tests.conftest import iter_api_routes

    routes = {path: route for path, route in iter_api_routes(app_with_routes)}
    for path in ("/api/admin/usage/summary", "/api/admin/usage/users", "/api/admin/usage/users/{user_id}", "/api/admin/usage/calls"):
        assert path in routes and routes[path].methods == {"GET"}
