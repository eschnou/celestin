"""SSE framing for a tutor turn, shared by the two turn routes (007 design 3.9).

Once the first byte is out the status is already 200, so every later failure
becomes an in-stream error event rather than an HTTP code (001 design 5).

`on_complete` is how a discussion stores what was said: it runs after the turn's
last event and before `turn.end` reaches the browser, so a failure to store is
still an `error` event the learner sees, and a turn that ended badly — a provider
failure, a disconnect, a cancellation — never calls it at all (007 NFR 4.4.1).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.api.locale import locale_of
from app.api.schemas.events import HEARTBEAT, SSE_HEADERS, ErrorEvent, TurnEnd, TurnEvent, to_sse
from app.domain.errors import TutorError
from app.domain.locale import Locale
from app.services.tools.context import TurnContext
from app.services.tutor_service import TutorService

log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 15.0

OnComplete = Callable[[list[TurnEvent], TurnEnd], Awaitable[None]]


def turn_response(
    tutor: TutorService,
    items: list,
    ctx: TurnContext,
    request: Request,
    on_complete: OnComplete | None = None,
) -> StreamingResponse:
    """One turn as an SSE response. The media type and the headers are part of the
    contract, so they live here rather than in each controller."""
    return StreamingResponse(
        stream_turn(tutor, items, ctx, request, on_complete),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _error_event(exc: TutorError, locale: Locale) -> ErrorEvent:
    """The `error` event of a turn that failed, in the language of the request."""
    return ErrorEvent(code=exc.code, message=exc.message(locale))


async def stream_turn(
    tutor: TutorService,
    items: list,
    ctx: TurnContext,
    request: Request,
    on_complete: OnComplete | None = None,
) -> AsyncIterator[str]:
    generator = tutor.run_turn(items, ctx)
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    locale = locale_of(request)

    async def pump() -> None:
        # Only the discussion reads these back; the parcours must not pay to buffer
        # a thousand deltas it will discard.
        produced: list[TurnEvent] = []
        try:
            async for event in generator:
                # Checked as each event is produced, so an abandoned turn stops
                # driving the provider instead of running to completion.
                if await request.is_disconnected():
                    return
                if isinstance(event, TurnEnd) and on_complete is not None:
                    try:
                        await on_complete(produced, event)
                    except TutorError as exc:
                        await queue.put(to_sse(_error_event(exc, locale)))
                    except Exception:
                        log.exception("turn_complete_hook_failed")
                        await queue.put(to_sse(_error_event(TutorError(), locale)))
                if on_complete is not None:
                    produced.append(event)
                await queue.put(to_sse(event))
        except Exception as exc:
            if not isinstance(exc, TutorError):
                log.exception("turn_failed")
                exc = TutorError()
            await queue.put(to_sse(_error_event(exc, locale)))
            await queue.put(to_sse(TurnEnd(reason="end")))
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_S)
            except TimeoutError:
                if await request.is_disconnected():
                    break
                yield HEARTBEAT
                continue
            if frame is None:
                break
            yield frame
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await generator.aclose()
