from __future__ import annotations

import pytest

from app.providers.base import Completed, TextDelta
from tests.fixtures.fake_llm import FakeLLM


async def _drain(llm: FakeLLM) -> list[object]:
    async with llm.stream(input=[], tools=[]) as stream:
        return [event async for event in stream]


async def test_replays_events_in_order() -> None:
    llm = FakeLLM([[TextDelta("a"), TextDelta("b"), Completed()]])
    assert await _drain(llm) == [TextDelta("a"), TextDelta("b"), Completed()]


async def test_records_the_input_it_received() -> None:
    llm = FakeLLM([[Completed()]])
    async with llm.stream(input=[{"role": "user", "content": "hi"}], tools=[{"name": "t"}]):
        pass
    assert llm.calls[0]["input"] == [{"role": "user", "content": "hi"}]
    assert llm.tools == [{"name": "t"}]


async def test_raises_when_asked_for_an_unscripted_round() -> None:
    llm = FakeLLM([[Completed()]])
    await _drain(llm)
    with pytest.raises(AssertionError, match="only 1 were scripted"):
        await _drain(llm)


async def test_closes_the_stream() -> None:
    llm = FakeLLM([[Completed()]])
    await _drain(llm)
    assert llm.closed == 1
