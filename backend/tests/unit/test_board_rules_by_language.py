"""Spec 011 R6.6/task 3.4: `display_board` hands each drawing rule the turn's language.

The rules are tested one by one in `test_*_rules*.py`; this goes through the tool, with a
`TurnContext` of each language, for the four drawing families.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from app.domain.errors import ToolValidationError
from app.services.tools import registry
from tests.fixtures.curricula import ctx_for
from tests.unit.test_chart_models import VALID as CHARTS
from tests.unit.test_flowchart_models import VALID as FLOWCHARTS
from tests.unit.test_figure_models import VALID as FIGURES


def show(drawing: dict[str, Any], language: str, pack: str | None = None, kind: str = "explanation") -> Any:
    card = {"kind": kind, "title": "Drawing", "blocks": [drawing]}
    ctx = replace(ctx_for(language=language), pack=pack)
    return registry.execute("display_board", json.dumps({"card": card}), ctx)


def refused(drawing: dict[str, Any], language: str, pack: str | None = None) -> str | None:
    try:
        show(drawing, language, pack)
    except ToolValidationError as error:
        return error.message
    return None


SINE = {"type": "plot", "x_range": [0, 6], "y_range": [-2, 2], "x_title": "$x$", "y_title": "$y$", "curves": [{"expr": "sin(x)"}]}


def test_a_plot_must_be_in_the_pack_of_its_own_language() -> None:
    english_pack, french_pack = "The sine of an angle.", "Le sinus d'un angle."
    assert refused(SINE, "en", english_pack) is None
    assert refused(SINE, "fr", french_pack) is None
    assert "n'apparaît pas dans le cours" in (refused(SINE, "en", french_pack) or "")
    assert "n'apparaît pas dans le cours" in (refused(SINE, "fr", english_pack) or "")


def test_a_flowchart_hole_is_refused_in_its_own_language() -> None:
    def with_text(text: str) -> dict[str, Any]:
        nodes = [dict(n) for n in FLOWCHARTS["method"]["nodes"]]
        nodes[2]["text"] = text
        return {**FLOWCHARTS["method"], "nodes": nodes}

    assert "marque un trou" in (refused(with_text("To complete"), "en") or "")
    assert refused(with_text("To complete"), "fr") is None
    assert "marque un trou" in (refused(with_text("À compléter"), "fr") or "")
    assert refused(with_text("À compléter"), "en") is None


def test_hand_written_pairs_are_refused_in_their_own_notation() -> None:
    def labelled(label: str) -> dict[str, Any]:
        return {**FIGURES["sets"], "caption": label}

    assert "à la main" in (refused({"type": "figure", "figure": labelled("A = (2, 3)")}, "en") or "")
    assert refused({"type": "figure", "figure": labelled("A = (2, 3)")}, "fr") is None
    assert "à la main" in (refused({"type": "figure", "figure": labelled("A = (2 ; 3)")}, "fr") or "")


@pytest.mark.parametrize("language", ["fr", "en"])
def test_a_chart_has_no_language_rule(language: str) -> None:
    assert refused({"type": "chart", "chart": CHARTS[sorted(CHARTS)[0]]}, language) is None
