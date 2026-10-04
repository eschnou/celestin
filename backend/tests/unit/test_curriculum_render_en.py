"""Spec 011 R5.1/R5.2: the path as the model reads it in an English course.

French is pinned by `test_curriculum_render.py` and its goldens, which this file does not
touch; the English goldens (`*_en.txt`) were generated once, read by a person, and pinned.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.domain.curriculum import KIND_LABELS
from app.domain.progress import Progress
from app.services import curriculum_render as render
from tests.fixtures.curricula import curriculum

CUR = curriculum("valid_en.yaml")
SNAPSHOTS = Path(__file__).parent.parent / "fixtures" / "render"
EN = "en"


def check(name: str, text: str) -> None:
    """Snapshot files are committed; regenerate by deleting one and rerunning."""
    path = SNAPSHOTS / f"{name}_en.txt"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8")


def test_overview_in_both_modes() -> None:
    text = render.overview(CUR, "parcours", EN)
    assert "1. `intro` (lesson) — Introduction. Understand what we are talking about." in text
    assert "2. `exos` (practice)" in text and "3. `bilan` (summary)" in text
    check("overview", text)
    discussion = render.overview(CUR, "discussion", EN)
    assert "start_section" not in discussion and "path mode" in discussion
    check("overview_discussion", discussion)


def test_the_overview_is_byte_stable_and_differs_from_the_french_one() -> None:
    assert render.overview(CUR, "parcours", EN) == render.overview(curriculum("valid_en.yaml"), "parcours", EN)
    assert render.overview(CUR, "parcours", EN) != render.overview(CUR)


@pytest.mark.parametrize(("section", "review", "name"), [("intro", False, "brief_teach"), ("exos", False, "brief_practise"), ("intro", True, "brief_review")])
def test_briefs(section: str, review: bool, name: str) -> None:
    text = render.brief(CUR, CUR.get(section), review, EN)
    assert text.startswith(f"Section “{CUR.get(section).label}” (")
    assert ("Review: this section is already done" in text) is review
    check(name, text)


def test_a_teach_brief_lists_the_outline_and_a_practice_brief_the_exercises() -> None:
    teach = render.brief(CUR, CUR.get("intro"), False, EN)
    assert "Outline:\n1. State the definition.\n2. Check question." in teach
    assert "Finished when: Has answered" in teach
    practise = render.brief(CUR, CUR.get("exos"), False, EN)
    assert "Typical exercises: 6.1.1; 6.1.2." in practise
    assert "To do: 2 exercise(s), one at a time." in practise and "Outline" not in practise


def test_completion() -> None:
    assert render.completion(CUR, Progress(done=frozenset({"intro"})), EN) == (
        "Section finished. Next section: “2. Exercises” (practice), id: exos."
    )
    assert render.completion(CUR, Progress(done=frozenset({"intro", "exos", "bilan"})), EN) == (
        "Section finished. Chapter finished."
    )


@pytest.mark.parametrize(
    ("name", "progress", "phrase"),
    [
        ("state_empty", Progress(), 'start_section("intro")'),
        ("state_active", Progress(done=frozenset({"intro"}), active="exos"), "Current section: “2. Exercises” (practice)."),
        ("state_between", Progress(done=frozenset({"intro"})), "Next: “2. Exercises”"),
        ("state_complete", Progress(done=frozenset({"intro", "exos", "bilan"})), "Chapter finished."),
    ],
)
def test_state_messages(name: str, progress: Progress, phrase: str) -> None:
    text = render.state_message(CUR, progress, None, "parcours", EN)
    assert phrase in text and len(text) < 400
    check(name, text)


@pytest.mark.parametrize(
    ("name", "progress", "phrase"),
    [
        ("state_discussion_empty", Progress(), "The next would be “1. Introduction”"),
        ("state_discussion_active", Progress(active="exos"), "Current section in the path: “2. Exercises”"),
        ("state_discussion_complete", Progress(done=frozenset({"intro", "exos", "bilan"})), "the whole path is done"),
    ],
)
def test_discussion_state_names_no_tool(name: str, progress: Progress, phrase: str) -> None:
    text = render.state_message(CUR, progress, None, "discussion", EN)
    assert phrase in text and "start_section" not in text
    check(name, text)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (datetime(2026, 9, 11, 10, 5), "Friday 11 September, 10:05 (morning)"),
        (datetime(2026, 9, 11, 11, 59), "Friday 11 September, 11:59 (morning)"),
        (datetime(2026, 9, 11, 12, 0), "Friday 11 September, 12:00 (afternoon)"),
        (datetime(2026, 9, 11, 17, 59), "Friday 11 September, 17:59 (afternoon)"),
        (datetime(2026, 12, 20, 18, 0), "Sunday 20 December, 18:00 (evening)"),
        (datetime(2026, 1, 5, 0, 7), "Monday 5 January, 0:07 (morning)"),
    ],
)
def test_moment(when: datetime, expected: str) -> None:
    assert render.moment(when, EN) == expected


def test_the_french_moment_is_unchanged_by_the_parameter() -> None:
    when = datetime(2026, 9, 11, 10, 5)
    assert render.moment(when) == render.moment(when, "fr") == "vendredi 11 septembre, 10 h 05 (le matin)"


def test_the_state_message_opens_with_the_time_in_the_courses_language() -> None:
    text = render.state_message(CUR, Progress(), datetime(2026, 9, 11, 10, 5), "parcours", EN)
    assert text.startswith("It is Friday 11 September, 10:05 (morning).\nPath status: 0 section(s) done out of 3.\n")


def test_the_kind_labels_cover_every_wire_kind_in_both_languages() -> None:
    assert {tuple(sorted(labels)) for labels in KIND_LABELS.values()} == {("practise", "synthesis", "teach")}
    assert KIND_LABELS["en"] == {"teach": "lesson", "practise": "practice", "synthesis": "summary"}
