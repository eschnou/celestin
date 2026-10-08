"""Spec 017 R5.1, R5.2: the path as the model reads it in a Dutch course.

French and English are pinned by `test_curriculum_render.py`, `test_curriculum_render_en.py` and their goldens,
which this file does not touch; the Dutch goldens (`*_nl.txt`) were generated once, read by a person, and pinned.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.domain.curriculum import KIND_LABELS
from app.domain.progress import Progress
from app.services import curriculum_render as render
from tests.fixtures.curricula import curriculum

CUR = curriculum("valid_nl.yaml")
SNAPSHOTS = Path(__file__).parent.parent / "fixtures" / "render"
NL = "nl"


def check(name: str, text: str) -> None:
    """Snapshot files are committed; regenerate by deleting one and rerunning."""
    path = SNAPSHOTS / f"{name}_nl.txt"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8")


def test_overview_in_both_modes() -> None:
    text = render.overview(CUR, "parcours", NL)
    assert "1. `intro` (les) — Inleiding. Begrijpen waarover we praten." in text
    assert "2. `exos` (oefeningen)" in text and "3. `bilan` (samenvatting)" in text
    check("overview", text)
    discussion = render.overview(CUR, "discussion", NL)
    assert "start_section" not in discussion and "trajectmodus" in discussion
    check("overview_discussion", discussion)


def test_the_overview_is_byte_stable_and_differs_from_the_others() -> None:
    assert render.overview(CUR, "parcours", NL) == render.overview(curriculum("valid_nl.yaml"), "parcours", NL)
    assert render.overview(CUR, "parcours", NL) != render.overview(CUR)
    assert render.overview(CUR, "parcours", NL) != render.overview(CUR, "parcours", "en")


@pytest.mark.parametrize(
    ("section", "review", "name"),
    [("intro", False, "brief_teach"), ("exos", False, "brief_practise"), ("intro", True, "brief_review")],
)
def test_briefs(section: str, review: bool, name: str) -> None:
    text = render.brief(CUR, CUR.get(section), review, NL)
    assert text.startswith(f"Sectie “{CUR.get(section).label}” (")
    assert ("Herhaling: deze sectie is al afgerond" in text) is review
    check(name, text)


def test_a_teach_brief_lists_the_outline_and_a_practice_brief_the_exercises() -> None:
    teach = render.brief(CUR, CUR.get("intro"), False, NL)
    assert "Verloop:\n1. De definitie aanhalen.\n2. Controlevraag." in teach
    assert "Afgerond wanneer: De controlevraag beantwoord heeft." in teach
    practise = render.brief(CUR, CUR.get("exos"), False, NL)
    assert "Typische oefeningen: 6.1.1; 6.1.2." in practise
    assert "Te doen: 2 oefening(en), één per keer." in practise and "Verloop" not in practise


def test_completion() -> None:
    assert render.completion(CUR, Progress(done=frozenset({"intro"})), NL) == (
        "Sectie afgerond. Volgende sectie: “2. Oefeningen” (oefeningen), id: exos."
    )
    assert render.completion(CUR, Progress(done=frozenset({"intro", "exos", "bilan"})), NL) == (
        "Sectie afgerond. Hoofdstuk afgerond."
    )


@pytest.mark.parametrize(
    ("name", "progress", "phrase"),
    [
        ("state_empty", Progress(), 'start_section("intro")'),
        ("state_active", Progress(done=frozenset({"intro"}), active="exos"), "Huidige sectie: “2. Oefeningen” (oefeningen)."),
        ("state_between", Progress(done=frozenset({"intro"})), "Volgende: “2. Oefeningen”"),
        ("state_complete", Progress(done=frozenset({"intro", "exos", "bilan"})), "Hoofdstuk afgerond."),
    ],
)
def test_state_messages(name: str, progress: Progress, phrase: str) -> None:
    text = render.state_message(CUR, progress, None, "parcours", NL)
    assert phrase in text and len(text) < 400
    check(name, text)


@pytest.mark.parametrize(
    ("name", "progress", "phrase"),
    [
        ("state_discussion_empty", Progress(), "De volgende zou “1. Inleiding” (les) zijn"),
        ("state_discussion_active", Progress(active="exos"), "Huidige sectie in het traject: “2. Oefeningen”"),
        ("state_discussion_complete", Progress(done=frozenset({"intro", "exos", "bilan"})), "het hele traject is gedaan"),
    ],
)
def test_discussion_state_names_no_tool(name: str, progress: Progress, phrase: str) -> None:
    text = render.state_message(CUR, progress, None, "discussion", NL)
    assert phrase in text and "start_section" not in text
    check(name, text)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (datetime(2026, 10, 8, 10, 5), "donderdag 8 oktober, 10:05 (voormiddag)"),
        (datetime(2026, 9, 11, 11, 59), "vrijdag 11 september, 11:59 (voormiddag)"),
        (datetime(2026, 9, 11, 12, 0), "vrijdag 11 september, 12:00 (namiddag)"),
        (datetime(2026, 9, 11, 17, 59), "vrijdag 11 september, 17:59 (namiddag)"),
        (datetime(2026, 12, 20, 18, 0), "zondag 20 december, 18:00 (avond)"),
        (datetime(2026, 1, 5, 0, 7), "maandag 5 januari, 0:07 (voormiddag)"),
    ],
)
def test_moment(when: datetime, expected: str) -> None:
    assert render.moment(when, NL) == expected


def test_the_state_message_opens_with_the_time_in_the_courses_language() -> None:
    text = render.state_message(CUR, Progress(), datetime(2026, 10, 8, 10, 5), "parcours", NL)
    assert text.startswith(
        "Het is donderdag 8 oktober, 10:05 (voormiddag).\nStand van het traject: 0 van de 3 sectie(s) afgerond.\n"
    )


def test_the_kind_labels_cover_every_wire_kind_in_every_language() -> None:
    assert {tuple(sorted(labels)) for labels in KIND_LABELS.values()} == {("practise", "synthesis", "teach")}
    assert KIND_LABELS["nl"] == {"teach": "les", "practise": "oefeningen", "synthesis": "samenvatting"}
