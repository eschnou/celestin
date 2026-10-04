from __future__ import annotations

import types

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.api import sse as sse_module
from app.api.schemas.events import HEARTBEAT, TurnStart


class _Request:
    def __init__(self, disconnect_after: int = 999) -> None:
        self._checks = 0
        self._after = disconnect_after
        self.state = types.SimpleNamespace()  # what locale_of reads
        self.headers: dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks >= self._after


class _SlowTutor:
    """One event, then a long silence, so the heartbeat has to fire."""

    def __init__(self, silence_s: float) -> None:
        self._silence = silence_s
        self.closed = False

    async def run_turn(self, items: list[Any], ctx: Any) -> AsyncIterator[Any]:
        try:
            yield TurnStart(turn_id="t")
            await asyncio.sleep(self._silence)
        finally:
            self.closed = True


async def _collect(tutor: Any, request: Any, limit: int) -> list[str]:
    out: list[str] = []
    agen = sse_module.stream_turn(tutor, [], None, request)
    try:
        async for frame in agen:
            out.append(frame)
            if len(out) >= limit:
                break
    finally:
        await agen.aclose()
    return out


async def test_heartbeat_on_an_idle_stream(monkeypatch) -> None:
    monkeypatch.setattr(sse_module, "HEARTBEAT_INTERVAL_S", 0.01)
    tutor = _SlowTutor(silence_s=5)
    frames = await _collect(tutor, _Request(), limit=3)
    assert frames[0].startswith("event: turn.start")
    assert frames[1] == HEARTBEAT
    assert frames[2] == HEARTBEAT


async def test_disconnect_stops_the_stream_and_closes_the_generator(monkeypatch) -> None:
    monkeypatch.setattr(sse_module, "HEARTBEAT_INTERVAL_S", 0.01)
    tutor = _SlowTutor(silence_s=5)
    # Already gone before the first event: nothing is sent, and the turn is closed.
    frames = [f async for f in sse_module.stream_turn(tutor, [], None, _Request(disconnect_after=1))]
    assert frames == []
    await asyncio.sleep(0)
    assert tutor.closed is True


async def test_disconnect_stops_driving_the_turn_between_events() -> None:
    """An abandoned turn must not keep calling the provider to the last round."""
    produced = 0

    class _Tutor:
        async def run_turn(self, items: list[Any], ctx: Any) -> AsyncIterator[Any]:
            nonlocal produced
            for _ in range(10):
                produced += 1
                yield TurnStart(turn_id="t")

    frames = [f async for f in sse_module.stream_turn(_Tutor(), [], None, _Request(disconnect_after=3))]
    assert len(frames) < 10
    assert produced < 10


async def test_generator_closed_exactly_once_on_normal_completion() -> None:
    closes = 0

    class _Tutor:
        async def run_turn(self, items: list[Any], ctx: Any) -> AsyncIterator[Any]:
            nonlocal closes
            try:
                yield TurnStart(turn_id="t")
            finally:
                closes += 1

    frames = [f async for f in sse_module.stream_turn(_Tutor(), [], None, _Request())]
    assert len(frames) == 1
    assert closes == 1
