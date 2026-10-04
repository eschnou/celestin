"""Scripted LLMClient (design 3.2 of the plan).

One list of provider events per round. Records the input it was given so tests
can assert on prompt assembly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.providers.base import ProviderEvent


class FakeLLM:
    model = "fake-model"

    def __init__(self, rounds: list[list[ProviderEvent]]) -> None:
        self._rounds = list(rounds)
        self.calls: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self.closed = 0

    @property
    def rounds_used(self) -> int:
        return len(self.calls)

    @asynccontextmanager
    async def stream(
        self,
        *,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[AsyncIterator[ProviderEvent]]:
        index = len(self.calls)
        self.calls.append({"input": list(input)})
        self.tools = tools
        if index >= len(self._rounds):
            raise AssertionError(
                f"FakeLLM was asked for round {index + 1} but only "
                f"{len(self._rounds)} were scripted"
            )
        events = self._rounds[index]

        async def gen() -> AsyncIterator[ProviderEvent]:
            for event in events:
                yield event

        try:
            yield gen()
        finally:
            self.closed += 1


class ExplodingLLM:
    """Raises on entry, to exercise the pre-first-byte error path."""

    model = "fake-model"

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    @asynccontextmanager
    async def stream(self, **_: Any) -> AsyncIterator[AsyncIterator[ProviderEvent]]:
        self.calls += 1
        raise self._error
        yield  # pragma: no cover
