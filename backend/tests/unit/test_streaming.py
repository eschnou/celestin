"""Spec 016 §3.3: watching a streamed call. Timeouts of tens of milliseconds against scripted async iterators."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.domain.errors import ProviderRateLimited, ProviderTimeout, ProviderUnavailable
from app.domain.usage import UsageScope, usage_scope
from app.providers.base import ProgressSnapshot, StreamBroken, StreamLimits, StreamTimeout
from app.providers.streaming import CallStats, consume, failure, log_done


class Script:
    """What `responses.create(stream=True)` returns: an async iterator that is also a context manager.
    Each item is an event, or a number of seconds to wait before the next one."""

    def __init__(self, *items: Any, open_delay: float = 0.0, end_forever: bool = False) -> None:
        self.items = items
        self.open_delay = open_delay
        self.end_forever = end_forever
        self.closed = False

    async def open(self) -> Script:
        if self.open_delay:
            await asyncio.sleep(self.open_delay)
        return self

    async def __aenter__(self) -> Script:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._run()

    async def _run(self) -> AsyncIterator[Any]:
        for item in self.items:
            if isinstance(item, float):
                await asyncio.sleep(item)
            else:
                yield item
        if self.end_forever:
            await asyncio.sleep(3600)


LIMITS = StreamLimits(first_event_s=0.15, idle_s=0.05)


async def run(script: Script, handle=None, *, limits: StreamLimits = LIMITS, on_progress=None, every: float = 1.0):
    stats = CallStats.begin()
    seen: list[Any] = []
    await consume(
        script.open,
        handle or seen.append,
        limits=limits,
        stats=stats,
        on_progress=on_progress,
        progress_every_s=every,
    )
    return stats, seen


async def test_a_stream_is_read_to_its_end_and_closed() -> None:
    script = Script("a", "b", "c")
    stats, seen = await run(script)
    assert seen == ["a", "b", "c"] and stats.events == 3 and script.closed


async def test_a_silent_stream_fails_the_first_event_allowance() -> None:
    script = Script(end_forever=True)
    with pytest.raises(StreamTimeout) as raised:
        await run(script)
    assert raised.value.reason == "first_event_timeout" and script.closed


async def test_the_wait_for_the_headers_counts_against_the_first_event_allowance() -> None:
    script = Script("a", open_delay=0.5)
    with pytest.raises(StreamTimeout) as raised:
        await run(script)
    assert raised.value.reason == "first_event_timeout"


async def test_a_stream_that_goes_quiet_after_events_fails_the_idle_limit() -> None:
    script = Script("a", "b", end_forever=True)
    with pytest.raises(StreamTimeout) as raised:
        await run(script)
    assert raised.value.reason == "idle_timeout" and script.closed


async def test_a_slow_but_flowing_stream_is_not_cut() -> None:
    """Longer in total than the idle limit, never quiet for as long as it."""
    script = Script(*["x", 0.03] * 8)
    stats, seen = await run(script)
    assert len(seen) == 8 and stats.elapsed_ms > 50


async def test_the_first_event_may_take_longer_than_a_pause_between_events() -> None:
    script = Script(0.1, "late")  # 100 ms of silence: over the idle limit, inside the first-event allowance
    _, seen = await run(script)
    assert seen == ["late"]


async def test_any_event_is_activity_including_ones_the_handler_ignores() -> None:
    script = Script(*["reasoning.delta", 0.03] * 6, "response.completed")
    stats, _ = await run(script, handle=lambda event: None)
    assert stats.events == 7


async def test_progress_is_throttled_to_the_interval_plus_one_final_snapshot() -> None:
    snapshots: list[ProgressSnapshot] = []
    stats = CallStats.begin()

    def handle(event: Any) -> None:
        stats.received_chars += len(event)

    script = Script("aaaa", 0.03, "bb", 0.03, "c", 0.03, "d")
    await consume(
        script.open, handle, limits=LIMITS, stats=stats, on_progress=snapshots.append, progress_every_s=0.05
    )
    assert 2 <= len(snapshots) <= 4
    assert snapshots[-1].received_chars == 8 and snapshots[-1].events == 4
    assert [s.received_chars for s in snapshots] == sorted(s.received_chars for s in snapshots)


async def test_without_a_callback_nothing_is_emitted_and_a_short_call_still_ends_with_one() -> None:
    snapshots: list[ProgressSnapshot] = []
    await run(Script("a"), on_progress=snapshots.append)
    assert len(snapshots) == 1  # no interval elapsed: only the final one


async def test_a_raising_callback_does_not_break_the_stream(caplog: pytest.LogCaptureFixture) -> None:
    def boom(_: ProgressSnapshot) -> None:
        raise RuntimeError("SECRET-CALLBACK-MESSAGE")

    with caplog.at_level(logging.WARNING):
        stats, seen = await run(Script("a", 0.02, "b"), on_progress=boom, every=0.0)
    assert seen == ["a", "b"] and stats.events == 2
    dump = " ".join(str(r.__dict__) for r in caplog.records)
    assert "progress_callback_failed" in dump and "RuntimeError" in dump and "SECRET-CALLBACK-MESSAGE" not in dump


async def test_a_handler_may_break_the_stream_and_the_stream_is_closed() -> None:
    def handle(event: Any) -> None:
        if event == "bad":
            raise StreamBroken("error_event", ProviderRateLimited.code)

    script = Script("ok", "bad", "never")
    with pytest.raises(StreamBroken):
        await run(script, handle=handle)
    assert script.closed


async def test_cancellation_closes_the_stream_and_leaves_no_task() -> None:
    script = Script("a", end_forever=True)
    before = asyncio.all_tasks()
    task = asyncio.create_task(run(script, limits=StreamLimits(5, 5)))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert script.closed
    assert asyncio.all_tasks() == before


# --- failure() and log_done() ---------------------------------------------------------------------------------


def records(caplog: pytest.LogCaptureFixture, message: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == message]


async def test_failure_translates_attaches_diagnostics_and_logs_one_line(caplog: pytest.LogCaptureFixture) -> None:
    stats = CallStats.begin()
    stats.on_event(stats.started)
    stats.received_chars = 1234
    with caplog.at_level(logging.WARNING):
        error = failure(StreamTimeout("idle_timeout"), role="authoring", model="m", host="api.example", stats=stats)
    assert isinstance(error, ProviderTimeout)
    assert error.diagnostics is not None and error.diagnostics.reason == "idle_timeout"
    assert error.diagnostics.received_chars == 1234 and error.diagnostics.error_class == "StreamTimeout"
    (line,) = records(caplog, "provider_call_failed")
    assert line.levelno == logging.WARNING
    assert (line.role, line.model, line.provider_host, line.reason) == ("authoring", "m", "api.example", "idle_timeout")  # type: ignore[attr-defined]
    assert line.received_chars == 1234 and line.events == 1  # type: ignore[attr-defined]


async def test_failure_maps_a_broken_stream_to_the_error_its_code_names() -> None:
    stats = CallStats.begin()
    limited = failure(StreamBroken("error_event", ProviderRateLimited.code), role="r", model="m", host="h", stats=stats)
    ended = failure(StreamBroken("stream_ended", ProviderUnavailable.code), role="r", model="m", host="h", stats=stats)
    assert isinstance(limited, ProviderRateLimited) and isinstance(ended, ProviderUnavailable)
    assert ended.diagnostics is not None and ended.diagnostics.reason == "stream_ended"


async def test_failure_logs_the_scope_attribution_only_inside_a_scope(caplog: pytest.LogCaptureFixture) -> None:
    stats = CallStats.begin()
    with caplog.at_level(logging.WARNING):
        failure(StreamTimeout("idle_timeout"), role="r", model="m", host="h", stats=stats)
        with usage_scope(UsageScope("u1", "authoring", "c1", "ch1", "run1")):
            failure(StreamTimeout("idle_timeout"), role="r", model="m", host="h", stats=stats)
    outside, inside = records(caplog, "provider_call_failed")
    assert not hasattr(outside, "user_id")
    assert (inside.user_id, inside.course_id, inside.chapter_id, inside.correlation_id) == ("u1", "c1", "ch1", "run1")  # type: ignore[attr-defined]


async def test_failure_never_logs_an_exceptions_message(caplog: pytest.LogCaptureFixture) -> None:
    stats = CallStats.begin()
    with caplog.at_level(logging.DEBUG):
        failure(RuntimeError("SECRET-MESSAGE quoting the prompt"), role="r", model="m", host="h", stats=stats)
    dump = " ".join(str(r.__dict__) for r in caplog.records)
    assert "SECRET-MESSAGE" not in dump and "RuntimeError" in dump


async def test_log_done_has_timings_characters_and_tokens(caplog: pytest.LogCaptureFixture) -> None:
    stats = CallStats.begin()
    stats.on_event(stats.started)
    stats.received_chars = 99
    usage = {"input_tokens": 10, "output_tokens": 5, "input_tokens_details": {"cached_tokens": 4}}
    with caplog.at_level(logging.INFO):
        log_done(role="authoring", model="m", host="h", stats=stats, usage=usage)
    (line,) = records(caplog, "provider_call_done")
    assert line.levelno == logging.INFO
    assert (line.received_chars, line.input_tokens, line.cached_tokens, line.output_tokens) == (99, 10, 4, 5)  # type: ignore[attr-defined]
    assert line.time_to_first_event_ms == 0 and line.events == 1  # type: ignore[attr-defined]
