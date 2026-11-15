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


# --- spec 019: skipped ---------------------------------------------------------------


def test_unknown_skipped_ids_are_dropped_and_done_wins_over_skipped() -> None:
    p = normalise(["intro"], None, CUR, ["ghost", "intro", "exos"])
    assert p == Progress(done=frozenset({"intro"}), skipped=frozenset({"exos"}))


def test_an_active_section_that_is_skipped_is_cleared() -> None:
    assert normalise([], "exos", CUR, ["exos"]) == Progress(skipped=frozenset({"exos"}))


def test_no_skipped_argument_is_nothing_skipped() -> None:
    assert normalise(["intro"], "exos", CUR) == Progress(done=frozenset({"intro"}), active="exos")


def test_starting_a_skipped_section_un_skips_it() -> None:
    p = Progress(skipped=frozenset({"intro", "exos"})).with_active("exos")
    assert p == Progress(active="exos", skipped=frozenset({"intro"}))


def test_skipping_the_active_section_clears_it_and_another_one_leaves_it() -> None:
    assert Progress(active="intro").with_skipped("intro") == Progress(skipped=frozenset({"intro"}))
    assert Progress(active="intro").with_skipped("exos") == Progress(active="intro", skipped=frozenset({"exos"}))
    again = Progress(skipped=frozenset({"exos"}))
    assert again.with_skipped("exos") == again


def test_starting_another_section_parks_the_active_one() -> None:
    """Spec 019 D4: the section left is neither done nor skipped."""
    assert Progress(done=frozenset({"intro"}), active="exos").with_active("bilan") == Progress(
        done=frozenset({"intro"}), active="bilan"
    )
