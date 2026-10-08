"""What an SDK `create(stream=True)` returns, scripted: an async iterator that is also a context manager, with a
`closed` flag, and the Responses events a test needs around it (spec 016)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any


class RawStream:
    """Yields `events`; with `stall`, then stays silent forever (a provider that went quiet)."""

    def __init__(self, events: list[Any], *, stall: bool = False) -> None:
        self._events = events
        self._stall = stall
        self.closed = False

    async def __aenter__(self) -> RawStream:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._run()

    async def _run(self) -> AsyncIterator[Any]:
        for event in self._events:
            yield event
        if self._stall:
            await asyncio.sleep(3600)


def delta(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="response.output_text.delta", delta=text)


def response(text: str = "", status: str = "completed", usage: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        output_text=text,
        incomplete_details=SimpleNamespace(reason="max_output_tokens") if status == "incomplete" else None,
        usage=SimpleNamespace(model_dump=lambda: usage or {"input_tokens": 3}),
    )


def done(text: str = "", status: str = "completed", usage: dict[str, Any] | None = None) -> SimpleNamespace:
    kind = "response.incomplete" if status == "incomplete" else "response.completed"
    return SimpleNamespace(type=kind, response=response(text, status, usage))
