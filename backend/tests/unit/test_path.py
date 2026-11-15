from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.curriculum import Curriculum
from app.domain.progress import Progress
from app.services import path

CASES = json.loads((Path(__file__).parent.parent / "fixtures" / "path_cases.json").read_text())


def curriculum(ids: list[str]) -> Curriculum:
    return Curriculum.model_validate(
        {
            "id": "tt",
            "title": "T",
            "sections": [
                {"id": i, "kind": "teach", "title": i.upper(), "goal": "g", "beats": ["b"], "done_when": "d"}
                for i in ids
            ],
        }
    )


CUR = curriculum(CASES["sections"])


def progress(case: dict) -> Progress:
    p = case["progress"]
    return Progress(done=frozenset(p["done"]), active=p["active"], skipped=frozenset(p["skipped"]))


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_state_table(case: dict) -> None:
    assert path.section_states(CUR, progress(case)) == case["states"]


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_next_section_table(case: dict) -> None:
    following = path.next_section(CUR, progress(case))
    assert (following.id if following else None) == case["next"]


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_the_available_one_is_the_next_one_when_nothing_is_active(case: dict) -> None:
    states = case["states"]
    available = [s for s, state in states.items() if state == "available"]
    if case["progress"]["active"] is None:
        assert available == ([case["next"]] if case["next"] else [])
    else:
        assert available == []


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_every_section_can_be_started_whatever_its_state(case: dict) -> None:
    """Spec 019 D1: no section is locked."""
    for section_id in case["states"]:
        assert path.can_start(CUR, section_id) is None, section_id


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_every_section_but_a_done_one_can_be_skipped(case: dict) -> None:
    p = progress(case)
    for section_id, state in case["states"].items():
        refusal = path.can_skip(CUR, p, section_id)
        assert (refusal is not None) == (state == "done"), (section_id, state)


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_can_complete_only_the_active_one(case: dict) -> None:
    p = progress(case)
    for section_id, state in case["states"].items():
        refusal = path.can_complete(CUR, p, section_id)
        assert (refusal is None) == (state == "active"), (section_id, state)


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_finished_is_every_section_done_or_skipped(case: dict) -> None:
    states = case["states"].values()
    assert path.finished(CUR, progress(case)) == all(s in ("done", "skipped") for s in states)


def test_the_skip_refusal_names_the_done_section() -> None:
    assert path.can_skip(CUR, Progress(done=frozenset({"sa"})), "sa") == (
        "La section « 1. SA » est déjà faite : elle ne peut pas être passée."
    )
    assert path.can_skip(CUR, Progress(done=frozenset({"sa"})), "sa", "en") == (
        "Section “1. SA” is already done: it cannot be skipped."
    )
    assert path.can_skip(CUR, Progress(done=frozenset({"sa"})), "sa", "nl") == (
        "Sectie “1. SA” is al afgerond: ze kan niet overgeslagen worden."
    )


def test_complete_refusals() -> None:
    assert "Aucune section" in path.can_complete(CUR, Progress(), "sa")
    assert "id : sa" in path.can_complete(CUR, Progress(active="sa"), "sb")


def test_unknown_id_is_refused_with_the_list() -> None:
    refusal = path.can_start(CUR, "zz")
    assert "zz" in refusal and "sa, sb, sc, sd" in refusal
    assert path.can_complete(CUR, Progress(active="sa"), "zz") is not None
    assert path.can_skip(CUR, Progress(), "zz") == refusal


def test_next_section() -> None:
    assert path.next_section(CUR, Progress()).id == "sa"
    assert path.next_section(CUR, Progress(done=frozenset({"sa"}), active="sb")).id == "sc"
    assert path.next_section(CUR, Progress(done=frozenset({"sa", "sb", "sc", "sd"}))) is None
    assert path.next_section(CUR, Progress(skipped=frozenset({"sa"}), active="sb")).id == "sc"


def test_the_page_turns_to_the_next_section_only_while_nothing_is_active() -> None:
    """One rule for both section events and both restored entries (spec 019)."""
    assert path.page_turn(CUR, Progress(skipped=frozenset({"sa"}), active="sc")) is None
    assert path.page_turn(CUR, Progress(skipped=frozenset({"sa"}))).id == "sb"
    assert path.page_turn(CUR, Progress(done=frozenset({"sa", "sb"}), skipped=frozenset({"sc", "sd"}))) is None


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_the_page_turn_is_the_available_section(case: dict) -> None:
    """The button proposes the section the map shows `available`, and nothing else."""
    turned = path.page_turn(CUR, progress(case))
    available = [sid for sid, state in case["states"].items() if state == "available"]
    assert ([turned.id] if turned is not None else []) == available
