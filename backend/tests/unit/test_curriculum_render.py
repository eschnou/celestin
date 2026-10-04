from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.domain.progress import Progress
from app.services import curriculum_render as render
from tests.fixtures.curricula import curriculum

CUR = curriculum()
SNAPSHOTS = Path(__file__).parent.parent / "fixtures" / "render"


def check(name: str, text: str) -> None:
    """Snapshot files are committed; regenerate by deleting one and rerunning."""
    path = SNAPSHOTS / f"{name}.txt"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8")


def test_overview() -> None:
    text = render.overview(CUR)
    assert "1. `intro` (cours) — Introduction." in text
    assert "2. `exos` (exercices)" in text
    assert "3. `bilan` (synthèse)" in text
    check("overview", text)


def test_overview_is_byte_stable() -> None:
    assert render.overview(CUR) == render.overview(curriculum())


def test_teach_brief() -> None:
    text = render.brief(CUR, CUR.get("intro"), review=False)
    assert text.startswith("Section « 1. Introduction » (cours), 1/3.")
    assert "1. Citer la définition." in text
    assert "Terminée quand : A répondu" in text
    assert "Révision" not in text
    check("brief_teach", text)


def test_practise_brief() -> None:
    text = render.brief(CUR, CUR.get("exos"), review=False)
    assert "Exercices types : 6.1.1 ; 6.1.2." in text
    assert "À faire : 2 exercice(s)" in text
    assert "Déroulé" not in text
    check("brief_practise", text)


def test_review_brief() -> None:
    text = render.brief(CUR, CUR.get("intro"), review=True)
    assert "Révision : cette section est déjà faite" in text
    check("brief_review", text)


def test_completion() -> None:
    assert "id : exos" in render.completion(CUR, Progress(done=frozenset({"intro"})))
    assert render.completion(CUR, Progress(done=frozenset({"intro", "exos", "bilan"}))) == (
        "Section terminée. Chapitre terminé."
    )


@pytest.mark.parametrize(
    ("name", "progress", "phrase"),
    [
        ("state_empty", Progress(), 'start_section("intro")'),
        ("state_active", Progress(done=frozenset({"intro"}), active="exos"), "Section en cours : « 2. Exercices »"),
        ("state_between", Progress(done=frozenset({"intro"})), "Prochaine : « 2. Exercices »"),
        ("state_complete", Progress(done=frozenset({"intro", "exos", "bilan"})), "Chapitre terminé"),
    ],
)
def test_state_messages(name: str, progress: Progress, phrase: str) -> None:
    text = render.state_message(CUR, progress)
    assert phrase in text
    assert len(text) < 400
    check(name, text)


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (datetime(2026, 9, 11, 10, 5), "vendredi 11 septembre, 10 h 05 (le matin)"),
        (datetime(2026, 9, 11, 14, 30), "vendredi 11 septembre, 14 h 30 (l'après-midi)"),
        (datetime(2026, 12, 20, 19, 0), "dimanche 20 décembre, 19 h 00 (le soir)"),
    ],
)
def test_moment(when: datetime, expected: str) -> None:
    assert render.moment(when) == expected


def test_state_message_opens_with_the_time_when_given() -> None:
    text = render.state_message(CUR, Progress(), datetime(2026, 9, 11, 10, 5))
    assert text.startswith("Nous sommes vendredi 11 septembre, 10 h 05 (le matin).\n")


# --- modes (007 §3.4) ---------------------------------------------------------


def test_the_parcours_branches_are_the_default() -> None:
    """The mode is a parameter; the parcours text must not move (007 Phase 0)."""
    assert render.overview(CUR, "parcours") == render.overview(CUR)
    assert render.state_message(CUR, Progress(), None, "parcours") == render.state_message(
        CUR, Progress()
    )


def test_discussion_overview_lists_the_sections_but_names_no_tool() -> None:
    text = render.overview(CUR, "discussion")
    assert "1. `intro` (cours) — Introduction." in text
    assert "3. `bilan` (synthèse)" in text
    assert "start_section" not in text and "complete_section" not in text
    assert "ne peux ni ouvrir ni terminer" in text
    check("overview_discussion", text)


@pytest.mark.parametrize(
    ("name", "progress", "phrase"),
    [
        ("state_discussion_empty", Progress(), "La prochaine serait « 1. Introduction »"),
        (
            "state_discussion_active",
            Progress(done=frozenset({"intro"}), active="exos"),
            "Section en cours dans le parcours : « 2. Exercices »",
        ),
        (
            "state_discussion_complete",
            Progress(done=frozenset({"intro", "exos", "bilan"})),
            "Chapitre terminé",
        ),
    ],
)
def test_discussion_state_messages(name: str, progress: Progress, phrase: str) -> None:
    text = render.state_message(CUR, progress, None, "discussion")
    assert phrase in text
    assert "start_section" not in text
    assert "section(s) faite(s) sur 3" in text
    assert len(text) < 400
    check(name, text)


def test_discussion_state_still_carries_the_time() -> None:
    text = render.state_message(CUR, Progress(), datetime(2026, 9, 11, 10, 5), "discussion")
    assert text.startswith("Nous sommes vendredi 11 septembre, 10 h 05 (le matin).\n")
