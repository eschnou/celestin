"""Watching a streamed provider call (spec 016 §3.3).

One helper for both adapters: it opens the stream, abandons it when the provider goes quiet (a first-event
allowance, then an idle limit that every event resets), counts what arrives, hands throttled progress snapshots
to a callback and, when a call fails, classifies the exception, logs one `provider_call_failed` line and puts
the diagnostics on the domain error.

A snapshot, a log line and the diagnostics hold counts, times and class names. Never text, never an
exception's message. Imports no SDK: `_errors.py` is the one place that knows its exception classes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, NoReturn

from app.domain.usage import current_scope, read_usage
from app.providers._errors import classify, translate
from app.providers.base import ProgressCallback, ProgressSnapshot, StreamBroken, StreamLimits, StreamTimeout

__all__ = ["CallStats", "consume", "fail", "failure", "log_done"]

log = logging.getLogger(__name__)

PROGRESS_EVERY_S = 1.0


@dataclass
class CallStats:
    """What one call has shown so far. `started` is the loop's clock when the request was built."""

    started: float
    events: int = 0
    received_chars: int = 0
    first_event_at: float | None = None
    last_event_at: float | None = None

    @classmethod
    def begin(cls) -> CallStats:
        return cls(started=asyncio.get_running_loop().time())

    def on_event(self, now: float) -> None:
        self.events += 1
        if self.first_event_at is None:
            self.first_event_at = now
        self.last_event_at = now

    @property
    def elapsed_ms(self) -> int:
        return round((asyncio.get_running_loop().time() - self.started) * 1000)

    @property
    def idle_ms(self) -> int:
        since = self.last_event_at if self.last_event_at is not None else self.started
        return round((asyncio.get_running_loop().time() - since) * 1000)

    @property
    def first_event_ms(self) -> int | None:
        return None if self.first_event_at is None else round((self.first_event_at - self.started) * 1000)

    def snapshot(self) -> ProgressSnapshot:
        return ProgressSnapshot(self.received_chars, self.events, self.elapsed_ms, self.idle_ms)


def _emit(callback: ProgressCallback, stats: CallStats) -> None:
    try:
        callback(stats.snapshot())
    except Exception as exc:  # noqa: BLE001 - progress must never fail the call it describes
        log.warning("progress_callback_failed", extra={"error": type(exc).__name__})


async def consume(
    open_stream: Callable[[], Awaitable[Any]],
    handle: Callable[[Any], None],
    *,
    limits: StreamLimits,
    stats: CallStats,
    on_progress: ProgressCallback | None = None,
    progress_every_s: float = PROGRESS_EVERY_S,
) -> None:
    """Open the stream and hand each event to `handle`, a synchronous function that updates `stats` and may
    raise `StreamBroken`. Any event, of any type, is activity. Raises `StreamTimeout` when the provider is quiet
    for longer than `limits` allows; the stream is closed on every way out, cancellation included.

    There is no `yield` inside the timeout: a cancellation can only land in the SDK stream's own awaits."""
    loop = asyncio.get_running_loop()
    began = last_emit = loop.time()  # not stats.started: a second attempt of one call gets its own allowance
    scope: asyncio.Timeout | None = None
    try:
        async with asyncio.timeout_at(began + limits.first_event_s) as scope:
            raw = await open_stream()  # the headers count against the first-event allowance
            async with raw:  # closes the response whichever way this block ends
                async for event in raw:
                    now = loop.time()
                    stats.on_event(now)
                    scope.reschedule(now + limits.idle_s)
                    handle(event)
                    if on_progress is not None and now - last_emit >= progress_every_s:
                        last_emit = now
                        _emit(on_progress, stats)
    except TimeoutError as exc:
        if scope is not None and scope.expired():
            raise StreamTimeout("first_event_timeout" if stats.events == 0 else "idle_timeout") from exc
        raise
    if on_progress is not None:
        _emit(on_progress, stats)  # the final snapshot


def _attribution() -> dict[str, str]:
    scope = current_scope()
    if scope is None:
        return {}
    fields = {
        "user_id": scope.user_id,
        "course_id": scope.course_id,
        "chapter_id": scope.chapter_id,
        "correlation_id": scope.correlation_id,
    }
    return {key: value for key, value in fields.items() if value}


def failure(exc: Exception, *, role: str, model: str, host: str, stats: CallStats) -> Exception:
    """The domain error to raise for `exc`, carrying `diagnostics`, after one WARNING `provider_call_failed`."""
    domain = translate(exc)
    diagnostics = replace(
        classify(exc), elapsed_ms=stats.elapsed_ms, idle_ms=stats.idle_ms, received_chars=stats.received_chars
    )
    domain.diagnostics = diagnostics  # type: ignore[attr-defined]
    log.warning(
        "provider_call_failed",
        extra={
            "role": role,
            "model": model,
            "provider_host": host,
            **_attribution(),
            "error_class": diagnostics.error_class,
            "reason": diagnostics.reason,
            "status_code": diagnostics.status_code,
            "provider_code": diagnostics.provider_code,
            "provider_request_id": diagnostics.request_id,
            "elapsed_ms": diagnostics.elapsed_ms,
            "idle_ms": diagnostics.idle_ms,
            "received_chars": diagnostics.received_chars,
            "events": stats.events,
        },
    )
    return domain


def fail(
    exc: Exception, *, role: str, model: str, host: str, stats: CallStats, only_provider: bool = False
) -> NoReturn:
    """Raise what `failure` says, from inside an `except` block. With `only_provider`, an exception that is not
    the provider's (an SDK error, a stream timeout) is raised as it is, unlogged: the tutor's stream also sees
    what its consumer raised."""
    if only_provider and translate(exc) is exc:
        raise exc
    domain = failure(exc, role=role, model=model, host=host, stats=stats)
    if domain is exc:
        raise exc
    raise domain from exc


def log_done(*, role: str, model: str, host: str, stats: CallStats, usage: dict[str, Any]) -> None:
    tokens = read_usage(usage)
    log.info(
        "provider_call_done",
        extra={
            "role": role,
            "model": model,
            "provider_host": host,
            **_attribution(),
            "elapsed_ms": stats.elapsed_ms,
            "time_to_first_event_ms": stats.first_event_ms,
            "received_chars": stats.received_chars,
            "events": stats.events,
            "input_tokens": tokens.input_tokens,
            "cached_tokens": tokens.cached_tokens,
            "output_tokens": tokens.output_tokens,
            "reasoning_tokens": tokens.reasoning_tokens,
        },
    )
