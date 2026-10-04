from __future__ import annotations

from app.api.ratelimit import SlidingWindow


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_limit_then_refuse() -> None:
    w = SlidingWindow(2, window_s=10, clock=Clock())
    assert w.allow("a") and w.allow("a")
    assert not w.allow("a")


def test_window_slides() -> None:
    clock = Clock()
    w = SlidingWindow(1, window_s=10, clock=clock)
    assert w.allow("a")
    clock.t = 9.9
    assert not w.allow("a")
    clock.t = 10.0
    assert w.allow("a")


def test_keys_are_independent() -> None:
    w = SlidingWindow(1, window_s=10, clock=Clock())
    assert w.allow("a") and w.allow("b")
    assert not w.allow("a")
