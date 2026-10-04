"""Spec 011 R6.2: the placeholder rule in an English course.

The French phrases and their tests stay in `test_flowchart_rules.py`, untouched.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.board import BoardCard, card_blocks
from app.domain.flowchart import FlowchartBlock
from app.services.tools.charts import Refusal
from app.services.tools.flowcharts import _is_hole, flowcharts_refusal
from tests.fixtures.curricula import ctx_for
from tests.unit.test_flowchart_rules import changed, exercise, explanation, setting

CARD: TypeAdapter[Any] = TypeAdapter(BoardCard)


def refusal(card: dict[str, Any], language: str = "en") -> Refusal | None:
    parsed = CARD.validate_python(card)
    items = [(path, block) for path, block in card_blocks(parsed) if isinstance(block, FlowchartBlock)]
    return flowcharts_refusal(items, parsed, ctx_for(language=language))


HOLE_PHRASES = [
    "To complete",
    "to complete…",
    "??? to find",
    "(fill in)",
    "… ?",
    "Missing step",
    "TO BE COMPLETED!",
    "Box to fill in",
    "Step 3 : ?",
    "Box no. 2 to complete",
    "Hidden node",
    "[to place]",
    "Answer ?",
    "Mystery",
    "TBD",
    "To be determined",
    "To fill in by the student",
]


@pytest.mark.parametrize("text", HOLE_PHRASES)
def test_an_english_box_whose_whole_text_is_a_hole_phrase_is_refused(text: str) -> None:
    found = refusal(exercise(changed("method", setting("sa", text=text))))
    assert found is not None and found[0] == "placeholder", found
    assert "hidden" in found[1]


@pytest.mark.parametrize(
    "text",
    [
        "Are they equal ?",
        "$q$ ?",
        "It is a GS…",
        # A hole phrase inside a real step is the step.
        "Fill in the table",
        "Find the ratio",
        "Compute the missing value",
        "Answer: $q = 2$",
        "Print “?”",
        "Next step",
        "Blank box ?",
        "Complete",
        "Your turn: compute $u_2$",
        "A",
        "$0$",
    ],
)
def test_a_real_english_text_is_not_a_placeholder(text: str) -> None:
    assert refusal(explanation(changed("method", setting("sa", text=text)))) is None


def test_each_language_reads_its_own_hole_phrases() -> None:
    assert _is_hole("To complete", "en") and not _is_hole("To complete", "fr")
    assert _is_hole("À compléter", "fr") and not _is_hole("À compléter", "en")
    assert _is_hole("?", "en") and _is_hole("?", "fr") and _is_hole("…", "en")
    assert _is_hole("À compléter") is True  # French by default


def test_a_french_hole_phrase_passes_the_english_rule_and_the_english_one_the_french_rule() -> None:
    french = exercise(changed("method", setting("sa", text="À compléter")))
    english = exercise(changed("method", setting("sa", text="To complete")))
    assert refusal(french, "fr") is not None and refusal(english, "en") is not None
    assert refusal(english, "fr") is None and refusal(french, "en") is None
