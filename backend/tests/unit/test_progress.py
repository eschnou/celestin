from __future__ import annotations

from app.domain.progress import Progress, normalise
from tests.fixtures.curricula import curriculum

CUR = curriculum()


def test_unknown_and_duplicate_done_ids_are_dropped() -> None:
    p = normalise(["intro", "ghost", "intro"], None, CUR)
    assert p == Progress(done=frozenset({"intro"}), active=None)


def test_active_unknown_is_cleared() -> None:
    assert normalise([], "ghost", CUR) == Progress()


def test_active_in_done_is_cleared() -> None:
    assert normalise(["intro"], "intro", CUR) == Progress(done=frozenset({"intro"}))


def test_transitions() -> None:
    p = Progress().with_active("intro")
    assert p.active == "intro"
    p = p.with_done("intro")
    assert p == Progress(done=frozenset({"intro"}), active=None)
