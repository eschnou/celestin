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
    return Progress(done=frozenset(case["progress"]["done"]), active=case["progress"]["active"])


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_state_table(case: dict) -> None:
    assert path.section_states(CUR, progress(case)) == case["states"]


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_can_start_per_state(case: dict) -> None:
    p = progress(case)
    for section_id, state in case["states"].items():
        refusal = path.can_start(CUR, p, section_id)
        if state == "locked":
            assert refusal, section_id
        else:
            assert refusal is None, (section_id, state)


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_can_complete_only_the_active_one(case: dict) -> None:
    p = progress(case)
    for section_id, state in case["states"].items():
        refusal = path.can_complete(CUR, p, section_id)
        assert (refusal is None) == (state == "active"), (section_id, state)


def test_locked_refusal_names_the_startable_section() -> None:
    refusal = path.can_start(CUR, Progress(done=frozenset({"sa"})), "sd")
    assert "2. SB" in refusal and "id : sb" in refusal

    refusal = path.can_start(CUR, Progress(done=frozenset({"sa"}), active="sb"), "sd")
    assert "id : sb" in refusal


def test_complete_refusals() -> None:
    assert "Aucune section" in path.can_complete(CUR, Progress(), "sa")
    assert "id : sa" in path.can_complete(CUR, Progress(active="sa"), "sb")


def test_unknown_id_is_refused_with_the_list() -> None:
    refusal = path.can_start(CUR, Progress(), "zz")
    assert "zz" in refusal and "sa, sb, sc, sd" in refusal
    assert path.can_complete(CUR, Progress(active="sa"), "zz") is not None


def test_next_section() -> None:
    assert path.next_section(CUR, Progress()).id == "sa"
    assert path.next_section(CUR, Progress(done=frozenset({"sa"}), active="sb")).id == "sc"
    assert path.next_section(CUR, Progress(done=frozenset({"sa", "sb", "sc", "sd"}))) is None
