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


# --- the only store hook (spec 018 D7, amended) -------------------------------------------


class _Hooks:
    def __init__(self) -> None:
        self.completed: list[list[Any]] = []

    async def complete(self, produced: list[Any], end: Any) -> None:
        self.completed.append(list(produced))


def _stream(tutor: Any, request: Any, hooks: _Hooks):
    return sse_module.stream_turn(tutor, [], None, request, hooks.complete)


async def test_a_completed_turn_is_stored_once_with_what_it_produced() -> None:
    from app.api.schemas.events import TurnEnd

    class _Tutor:
        async def run_turn(self, items: list[Any], ctx: Any) -> AsyncIterator[Any]:
            yield TurnStart(turn_id="t")
            yield TurnEnd(reason="end")

    hooks = _Hooks()
    frames = [f async for f in _stream(_Tutor(), _Request(), hooks)]
    assert len(frames) == 2 and len(hooks.completed) == 1
    assert [type(e).__name__ for e in hooks.completed[0]] == ["TurnStart"]


async def test_a_failed_turn_stores_nothing() -> None:
    class _Tutor:
        async def run_turn(self, items: list[Any], ctx: Any) -> AsyncIterator[Any]:
            yield TurnStart(turn_id="t")
            raise RuntimeError("provider down")

    hooks = _Hooks()
    [f async for f in _stream(_Tutor(), _Request(), hooks)]
    assert hooks.completed == []


async def test_a_disconnect_between_events_stores_nothing() -> None:
    """The browser reports a turn the learner stopped itself; a dropped connection is a turn
    that never happened, which is what its `retry()` assumes."""

    class _Tutor:
        async def run_turn(self, items: list[Any], ctx: Any) -> AsyncIterator[Any]:
            for _ in range(10):
                yield TurnStart(turn_id="t")

    hooks = _Hooks()
    [f async for f in _stream(_Tutor(), _Request(disconnect_after=3), hooks)]
    assert hooks.completed == []


async def test_a_stream_closed_mid_turn_cancels_the_pump_and_stores_nothing(monkeypatch) -> None:
    """What a cancelled request does: the response stops iterating and closes the stream while
    the turn is still running. Nothing is left running behind it."""
    monkeypatch.setattr(sse_module, "HEARTBEAT_INTERVAL_S", 0.01)
    tutor = _SlowTutor(silence_s=5)
    hooks = _Hooks()
    agen = _stream(tutor, _Request(), hooks)
    first = await agen.__anext__()
    assert first.startswith("event: turn.start")
    await agen.aclose()
    assert tutor.closed is True
    assert hooks.completed == []
    assert not hasattr(sse_module, "settle") and not hasattr(sse_module, "_PENDING")
