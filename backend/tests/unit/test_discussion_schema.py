"""A stored discussion replays its board cards through the card model (008 R1.6)."""

from __future__ import annotations

from typing import Any

import pytest

from app.api.schemas.chat import ToolEntry
from app.api.schemas.discussion import StoredEntry
from tests.unit.test_chart_models import VALID
from tests.unit.test_figure_models import VALID as FIGURES
from tests.unit.test_flowchart_models import VALID as FLOWCHARTS
from tests.unit.test_plot_models import VALID as PLOTS


def _stored(card: dict) -> StoredEntry:
    return StoredEntry.of(ToolEntry(kind="tool", name="display_board", arguments={"card": card}))


def test_a_stored_chart_card_replays_with_its_marker() -> None:
    explanation = {
        "kind": "explanation",
        "title": "Les notes",
        "blocks": [{"type": "chart", "chart": VALID["histogram"]}],
    }
    exercise = {
        "kind": "exercise",
        "title": "Lecture",
        "statement": "Quel est le mode ?",
        "drawing": {"type": "chart", "chart": VALID["sticks"]},
    }
    assert _stored(explanation).marker == "explication affichée"
    assert _stored(exercise).marker == "exercice posé"
    assert _stored(exercise).arguments == {"card": exercise}


# The drawing blocks after 008, each as the model sends it (`type` always given).
DRAWINGS: dict[str, dict[str, Any]] = {
    "flowchart": FLOWCHARTS["loop"],
    "figure": {"type": "figure", "figure": FIGURES["number_line"]},
    "plot": PLOTS["sequence"],
}


@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_a_stored_drawing_card_replays_with_its_marker(name: str) -> None:
    drawing = DRAWINGS[name]
    explanation = {"kind": "explanation", "title": "Au tableau", "blocks": [drawing]}
    worked = {"kind": "worked_example", "title": "Exemple", "statement": "Lis.", "drawing": drawing, "steps": [{"tex": "x"}]}
    exercise = {"kind": "exercise", "title": "Exercice", "statement": "Cherche.", "drawing": drawing}
    for card, marker in (
        (explanation, "explication affichée"),
        (worked, "exemple guidé affiché"),
        (exercise, "exercice posé"),
    ):
        stored = _stored(card)
        assert stored.marker == marker
        assert stored.arguments == {"card": card}
        assert StoredEntry.model_validate(stored.model_dump()) == stored


def test_a_stored_chart_drawing_without_type_still_replays() -> None:
    """A discussion stored under 008 may hold a chart drawing without `type`."""
    exercise = {"kind": "exercise", "title": "Lecture", "statement": "Quel est le mode ?", "drawing": {"chart": VALID["sticks"]}}
    assert _stored(exercise).marker == "exercice posé"


@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_a_stored_later_drawing_without_type_has_no_marker(name: str) -> None:
    """Read from its keys as its own block, it fails the card model for the missing
    `type` (the model was refused it live too): the call shows without a label
    rather than as the wrong drawing."""
    untagged = {key: value for key, value in DRAWINGS[name].items() if key != "type"}
    exercise = {"kind": "exercise", "title": "Exercice", "statement": "Cherche.", "drawing": untagged}
    assert _stored(exercise).marker is None
