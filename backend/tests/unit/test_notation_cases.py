"""Spec 011 §4.6: what the board writes is what the rules recognise.

`notation_cases.json` is read by the frontend formatter (it must produce each `text`) and
here (the rule patterns must recognise it, and the number reader must read it back). The
two copies are byte-identical, formatted with prettier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.tools.figures import COORDS, INTERVAL, _bare, _number

FIXTURES = Path(__file__).parent.parent / "fixtures"
FRONTEND_COPY = (
    Path(__file__).parents[3]
    / "frontend"
    / "src"
    / "components"
    / "celestin"
    / "charts"
    / "__tests__"
    / "notation_cases.json"
)
CASES = json.loads((FIXTURES / "notation_cases.json").read_text(encoding="utf-8"))


def test_the_two_copies_are_identical() -> None:
    assert (FIXTURES / "notation_cases.json").read_bytes() == FRONTEND_COPY.read_bytes()


def test_the_table_covers_each_kind_in_both_languages() -> None:
    assert {(c["language"], c["kind"]) for c in CASES} == {
        (language, kind) for language in ("fr", "en") for kind in ("interval", "pair", "number")
    }


@pytest.mark.parametrize("case", [c for c in CASES if c["kind"] == "interval"], ids=lambda c: f"{c['language']} {c['text']}")
def test_a_written_interval_is_recognised_as_hand_written_notation(case: dict) -> None:
    language = case["language"]
    assert INTERVAL[language].search(_bare(case["text"])), case["text"]


@pytest.mark.parametrize("case", [c for c in CASES if c["kind"] == "pair"], ids=lambda c: f"{c['language']} {c['text']}")
def test_a_written_pair_is_recognised_as_hand_written_notation(case: dict) -> None:
    language = case["language"]
    assert COORDS[language].search(_bare(case["text"])), case["text"]


@pytest.mark.parametrize("case", [c for c in CASES if c["kind"] == "number"], ids=lambda c: f"{c['language']} {c['text']}")
def test_a_written_number_is_read_back(case: dict) -> None:
    assert _number(_bare(case["text"]), case["language"]) == case["args"][0]


def test_the_other_languages_pair_is_prose() -> None:
    """`(2, −1.5)` is a pair in English and prose in French; `(2 ; −1,5)` the French pair."""
    english = next(c for c in CASES if c["language"] == "en" and c["kind"] == "pair")
    french = next(c for c in CASES if c["language"] == "fr" and c["kind"] == "pair" and c["text"] == "(0 ; 0)")
    assert not COORDS["fr"].search(_bare(english["text"]))
    assert COORDS["en"].search(_bare(french["text"]))  # `;` is no better by hand in English
