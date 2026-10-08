"""Live progress of one authoring run (spec 016 §3.9).

A streamed call reports how far it has got; this turns the reports into (a) the chapter row's count of characters
received and the time it last moved, which the course screen polls, and (b) a `provider_call_progress` log line
every `authoring_progress_log_s`. Counts, durations, a stage: never text.

Writes never slow the stream and never fail the run: the latest value is kept, one task writes it off the event
loop, and a write that fails is logged and forgotten.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import Settings
from app.db.repositories import ChapterRepository
from app.domain.chapter import COUNTED_STAGES, Stage
from app.providers.base import ProgressCallback, ProgressSnapshot

log = logging.getLogger(__name__)


class _Writer:
    """Holds the latest value to store; one task at a time stores it. `None` means « still alive, no count »."""

    def __init__(self, store: Any, extra: dict[str, Any]) -> None:
        self._store = store
        self._extra = extra
        self._chars: int | None = None
        self._dirty = False
        self._task: asyncio.Task[None] | None = None

    def put(self, chars: int | None) -> None:
        if chars is not None:
            self._chars = chars
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._drain())

    async def _drain(self) -> None:
        while self._dirty:
            chars, self._chars, self._dirty = self._chars, None, False
            await self.write(chars)

    async def write(self, chars: int | None) -> None:
        try:
            await asyncio.to_thread(self._store, chars)
        except Exception as exc:  # noqa: BLE001 - a progress write must never fail the run
            log.warning("authoring_progress_not_stored", extra={**self._extra, "error": type(exc).__name__})

    async def settle(self) -> None:
        task = self._task
        if task is not None and not task.done():
            await asyncio.shield(task)

    def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()


class LiveProgress:
    """One per run. `extra` is the run's log attribution (`run_id`, `user_id`, `course_id`, `chapter_id`)."""

    def __init__(
        self,
        chapters: ChapterRepository,
        chapter_id: str,
        settings: Settings,
        extra: dict[str, Any],
        *,
        log_every_s: float | None = None,
    ) -> None:
        self._extra = extra
        self._log_every_s = settings.authoring_progress_log_s if log_every_s is None else log_every_s
        self._writer = _Writer(lambda chars: chapters.set_received(chapter_id, chars), extra)

    async def restart_count(self) -> None:
        """A repair attempt is about to start: the count goes back to zero. Awaited, so the screen never shows the
        count of the attempt before. A stage's first attempt needs no call: starting the stage already did it."""
        await self._writer.write(0)

    def for_call(self, stage: Stage, attempt: int) -> ProgressCallback:
        """The callback for one call, handed to `complete(on_progress=…)`."""
        counted = stage in COUNTED_STAGES
        last_logged = time.monotonic()

        def callback(snapshot: ProgressSnapshot) -> None:
            nonlocal last_logged
            self._writer.put(snapshot.received_chars if counted else None)
            now = time.monotonic()
            if now - last_logged >= self._log_every_s:
                last_logged = now
                log.info(
                    "provider_call_progress",
                    extra={
                        **self._extra,
                        "stage": stage,
                        "attempt": attempt,
                        "received_chars": snapshot.received_chars,
                        "elapsed_ms": snapshot.elapsed_ms,
                        "idle_ms": snapshot.idle_ms,
                    },
                )

        return callback

    async def settle(self) -> None:
        """Let the last value land before the stage's own log line."""
        await self._writer.settle()

    def close(self) -> None:
        """The run is over (or cancelled): drop a write that has not started."""
        self._writer.close()
