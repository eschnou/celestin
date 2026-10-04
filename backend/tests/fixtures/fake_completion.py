"""Scripted CompletionClient for the authoring agent (005 design 6).

One `CompletionResult` or exception per call, in order. Records what each call was
given so tests can assert on instructions, input and whether a schema was used.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from app.providers.base import CompletionResult


class FakeCompletion:
    def __init__(self, script: list[CompletionResult | Exception], delay_s: float = 0.0) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.delay_s = delay_s

    async def complete(
        self,
        *,
        role: str = "authoring",
        instructions: list[str],
        input: list[dict[str, Any]],
        schema: type[BaseModel] | None = None,
        schema_name: str | None = None,
        max_output_tokens: int,
    ) -> CompletionResult:
        self.calls.append(
            {"role": role, "instructions": list(instructions), "input": [dict(i) for i in input], "schema": schema}
        )
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if not self._script:
            raise AssertionError(f"FakeCompletion was asked for call {len(self.calls)} but none was scripted")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def text(value: str, usage: dict[str, Any] | None = None) -> CompletionResult:
    return CompletionResult(text=value, usage=usage or {"input_tokens": 100, "output_tokens": 50})


def data(value: dict[str, Any], usage: dict[str, Any] | None = None) -> CompletionResult:
    import json

    return CompletionResult(text=json.dumps(value), data=value, usage=usage or {"input_tokens": 80, "output_tokens": 40})
