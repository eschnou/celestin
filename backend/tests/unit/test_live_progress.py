"""Spec 016 §3.9: a run's live progress, stored without ever slowing or failing the run."""

from __future__ import annotations

import asyncio
import logging

import pytest

from app.config import Settings
from app.providers.base import ProgressSnapshot
from app.services.authoring.progress import LiveProgress
from tests.fixtures.fake_chapters import EXTRA, Chapters

def live(chapters: Chapters, log_every_s: float | None = None) -> LiveProgress:
    settings = Settings(openai_api_key="k", _env_file=None)
    return LiveProgress(chapters, "ch1", settings, EXTRA, log_every_s=log_every_s)  # type: ignore[arg-type]


def snap(chars: int, n: int = 1) -> ProgressSnapshot:
    return ProgressSnapshot(received_chars=chars, events=n, elapsed_ms=n * 1000, idle_ms=10)


async def test_a_pack_call_stores_the_characters_received() -> None:
    chapters = Chapters()
    progress = live(chapters)
    callback = progress.for_call("pack", 1)
    callback(snap(100))
    await progress.settle()
    assert chapters.writes == [("ch1", 100)]


async def test_only_the_latest_value_is_kept_while_a_write_is_under_way() -> None:
    chapters = Chapters(delay_s=0.05)
    progress = live(chapters)
    callback = progress.for_call("pack", 1)
    for chars in (100, 200, 300, 400, 500):
        callback(snap(chars))
    await progress.settle()
    await asyncio.sleep(0.12)
    stored = [chars for _, chars in chapters.writes]
    assert stored[-1] == 500 and len(stored) <= 2 and chapters.peak == 1  # never two writes at once


async def test_a_page_batch_only_marks_the_run_alive() -> None:
    chapters = Chapters()
    progress = live(chapters)
    progress.for_call("transcription", 1)(snap(9999))
    await progress.settle()
    assert chapters.writes == [("ch1", None)]


async def test_a_repair_attempt_zeroes_the_count() -> None:
    chapters = Chapters()
    await live(chapters).restart_count()
    assert chapters.writes == [("ch1", 0)]


async def test_a_failing_write_is_logged_by_class_and_ignored(caplog: pytest.LogCaptureFixture) -> None:
    chapters = Chapters(fail=RuntimeError("SECRET-DB-MESSAGE"))
    progress = live(chapters)
    with caplog.at_level(logging.WARNING):
        progress.for_call("pack", 1)(snap(10))
        await progress.settle()
        await progress.restart_count()  # does not raise either
    lines = [r for r in caplog.records if r.getMessage() == "authoring_progress_not_stored"]
    assert lines and all(r.error == "RuntimeError" and r.chapter_id == "ch1" for r in lines)  # type: ignore[attr-defined]
    assert "SECRET-DB-MESSAGE" not in " ".join(str(r.__dict__) for r in caplog.records)


async def test_the_progress_line_is_logged_at_the_configured_interval(caplog: pytest.LogCaptureFixture) -> None:
    progress = live(Chapters(), log_every_s=0)
    callback = progress.for_call("curriculum", 2)
    with caplog.at_level(logging.INFO):
        callback(snap(10, 1))
        callback(snap(20, 2))
    await progress.settle()
    lines = [r for r in caplog.records if r.getMessage() == "provider_call_progress"]
    assert [r.received_chars for r in lines] == [10, 20]  # type: ignore[attr-defined]
    first = lines[0]
    assert (first.run_id, first.chapter_id, first.stage, first.attempt) == ("r1", "ch1", "curriculum", 2)  # type: ignore[attr-defined]
    assert (first.elapsed_ms, first.idle_ms) == (1000, 10)  # type: ignore[attr-defined]


async def test_nothing_is_logged_before_the_interval(caplog: pytest.LogCaptureFixture) -> None:
    progress = live(Chapters(), log_every_s=3600)
    with caplog.at_level(logging.INFO):
        progress.for_call("pack", 1)(snap(10))
    await progress.settle()
    assert not [r for r in caplog.records if r.getMessage() == "provider_call_progress"]


async def test_close_drops_a_write_that_has_not_started() -> None:
    chapters = Chapters(delay_s=0.1)
    progress = live(chapters)
    callback = progress.for_call("pack", 1)
    callback(snap(1))
    await asyncio.sleep(0.01)  # the first write is in its thread
    callback(snap(2))
    progress.close()
    await asyncio.sleep(0.25)
    assert ("ch1", 2) not in chapters.writes


async def test_the_progress_line_carries_counts_and_names_only(caplog: pytest.LogCaptureFixture) -> None:
    progress = live(Chapters(), log_every_s=0)
    with caplog.at_level(logging.DEBUG):
        progress.for_call("pack", 1)(snap(10))
    await progress.settle()
    (line,) = [r for r in caplog.records if r.getMessage() == "provider_call_progress"]
    shown = {k: v for k, v in line.__dict__.items() if k in {"stage", "attempt", "received_chars", "elapsed_ms", "idle_ms"}}
    assert shown == {"stage": "pack", "attempt": 1, "received_chars": 10, "elapsed_ms": 1000, "idle_ms": 10}
