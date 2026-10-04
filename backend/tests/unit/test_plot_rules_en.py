"""Spec 011 R6.1/R6.3: the plot rules in an English course.

The French cases stay in `test_plot_rules.py` and pass untouched; this adds the English
ones beside them: one accepted and one refused sentence per `PACK_WORDS` entry, and the
comma `gives_away` reads as a separator.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.expression import FUNCTIONS
from app.domain.plot import PlotBlock
from app.services.tools.plots import (
    COMMA,
    PACK_WORDS,
    PACK_WORDS_BY_LANGUAGE,
    gives_away,
    plot_refusal,
    plots_refusal,
)
from tests.fixtures.curricula import ctx_for

ADAPTER: TypeAdapter[PlotBlock] = TypeAdapter(PlotBlock)


def P(**changes: Any) -> PlotBlock:
    base: dict[str, Any] = {"type": "plot", "x_range": [-5, 5], "y_range": [-5, 5], "x_title": "$x$", "y_title": "$y$"}
    return ADAPTER.validate_python({**base, **changes})


def rule(plot: PlotBlock, pack: str | None, language: str = "en") -> str | None:
    found = plot_refusal(plot, "blocks[0]", pack, language)  # type: ignore[arg-type]
    return None if found is None else found[0]


PACK_SENTENCES: list[tuple[str, str, bool]] = [
    ("exp(x)", "The exponential function is the inverse of ln.", True),
    ("exp(x)", "We also write $\\exp(x)$.", True),
    ("exp(x)", "The discharge follows $U_0\\,\\mathrm{e}^{-t/\\tau}$.", True),
    ("exp(x)", "$f(x) = {e}^{x}$", True),
    ("2^x", "The exponential with base 2.", True),
    ("2^x", "The exponential of a number grows quickly.", True),
    ("exp(x)", "A population has exponential growth.", False),
    ("2^x", "Radioactive exponential decay.", False),
    ("exp(x)", "The electron $e^-$ and the positron $\\mathrm{e}^{+}$.", False),
    ("exp(x)", "The standard potential $E^{\\circ}$.", False),
    ("ln(x)", "The natural logarithm.", True),
    ("ln(x)", "We write $\\ln x$.", True),
    ("ln(x)", "The logarithm to base $\\mathrm{e}$.", True),
    ("ln(x)", "The Napierian logarithm.", True),
    ("ln(x)", "pH is read on a logarithmic scale.", False),
    ("ln(x)", "The common logarithm, written $\\log x$.", False),
    ("log(x)", "The common logarithm.", True),
    ("log(x)", "$\\log_{10} 100$", True),
    ("log(x)", "The logarithm to base 10.", True),
    ("log(x)", "The natural logarithm, written $\\ln x$.", False),
    ("log(x)", "A logarithmic scale.", False),
    ("cbrt(x)", "The cube root.", True),
    ("cbrt(x)", "$\\sqrt[3]{x}$", True),
    ("cbrt(x)", "The square root $\\sqrt{x}$.", False),
    ("cbrt(x)", "$\\sqrt[4]{x}$", False),
    ("sin(x)", "$\\sin x$", True),
    ("sin(x)", "The sine of an acute angle is opposite over hypotenuse.", True),
    ("sin(x)", "A sinusoidal voltage.", True),
    ("sin(x)", "The cosine of an acute angle.", False),
    ("sin(x)", "$\\sinh x$ and $\\arcsin x$", False),
    ("cos(x)", "The cosine.", True),
    ("cos(x)", "$\\cos x$", True),
    ("cos(x)", "The sine of an acute angle.", False),
    ("cos(x)", "$\\cosh x$", False),
    ("tan(x)", "The tangent function.", True),
    ("tan(x)", "$\\tan x$", True),
    ("tan(x)", "The tangent of an acute angle.", True),
    ("tan(x)", "The tangent of the angle $\\hat{A}$.", True),
    ("tan(x)", "Sine, cosine and tangent of an angle.", True),
    ("tan(x)", "The equation of the tangent at A", False),
    ("tan(x)", "The tangent to the curve at the point of abscissa 1.", False),
    ("tan(x)", "The slope of the tangent of the curve at A", False),
    ("tan(x)", "The line is tangent to the circle.", False),
    ("tan(x)", "$\\tanh x$ and $\\arctan x$", False),
]


@pytest.mark.parametrize("expr,pack,allowed", PACK_SENTENCES)
def test_the_english_pack_names_the_function_not_the_word(expr: str, pack: str, allowed: bool) -> None:
    plot = P(x_range=[0.5, 1.5], y_range=[-5, 25], curves=[{"expr": expr}])
    assert rule(plot, pack) == (None if allowed else "pack_function")


def test_every_english_entry_has_a_sentence_it_accepts_and_one_it_refuses() -> None:
    assert set(PACK_WORDS_BY_LANGUAGE["en"]) == set(PACK_WORDS) == set(FUNCTIONS) - {"sqrt", "abs"}
    named = {"e^x": "exp", "2^x": "exp"}
    seen = {(named.get(expr, expr.split("(")[0]), allowed) for expr, _, allowed in PACK_SENTENCES}
    assert seen == {(name, allowed) for name in PACK_WORDS_BY_LANGUAGE["en"] for allowed in (True, False)}


def test_a_french_pack_does_not_license_a_function_in_an_english_course_and_conversely() -> None:
    plot = P(x_range=[0.5, 1.5], y_range=[-5, 25], curves=[{"expr": "ln(x)"}])
    assert rule(plot, "Le logarithme népérien", "fr") is None
    assert rule(plot, "Le logarithme népérien", "en") == "pack_function"
    assert rule(plot, "The natural logarithm", "en") is None
    assert rule(plot, "The natural logarithm", "fr") == "pack_function"


def test_the_rule_reads_the_turns_language() -> None:
    card = TypeAdapter(Any).validate_python(
        {"kind": "explanation", "title": "Graph", "blocks": [P(curves=[{"expr": "sin(x)"}]).model_dump()]}
    )
    from app.domain.board import BoardCard

    built = TypeAdapter(BoardCard).validate_python(card)
    items = [(f"blocks[{i}]", b) for i, b in enumerate(built.blocks)]
    english = replace(ctx_for(language="en"), pack="The sine of an angle.")
    assert plots_refusal(items, built, english) is None
    assert plots_refusal(items, built, replace(english, language="fr")) is not None


# ---------------------------------------------------------------- what an open exercise may not show


def test_the_decimal_point_is_not_a_separator_and_the_comma_is() -> None:
    assert COMMA["fr"].split("(0,5)") == ["(0,5)"]
    assert COMMA["en"].split("(1,4)") == ["(1", "4)"]
    assert COMMA["en"].split("(3,100)") == ["(3", "100)"]  # a pair, whatever the digits


@pytest.mark.parametrize(
    ("text", "gives"),
    [
        ("(1,4)", True),
        ("(1, 4)", True),
        ("(0.5, 2)", True),
        ("(-1,-4)", True),
        ("(x_S ; 2)", True),
        ("(3,100)", True),
        ("(2,500)", True),
        ("(1,500 m)", True),  # a thousands comma is not told from a pair: one rewrite, no leak
        ("(cm, every 0.5 s)", False),
        ("(cm, every 5 s)", False),
        ("$f$", False),
        ("$A$", False),
        ("Distance (m)", False),
        ("f(x) = 2", True),
        ("(2, 3]", True),
    ],
)
def test_gives_away_in_english(text: str, gives: bool) -> None:
    assert gives_away(text, "en") is gives


def test_the_french_reading_of_a_decimal_comma_is_unchanged() -> None:
    assert gives_away("(0,5)") is False
    assert gives_away("(0,5)", "fr") is False
    assert gives_away("(1,-4)") is True
    assert gives_away("(1,4)", "en") is True  # a pair in English, one decimal in French
    assert gives_away("(1,4)", "fr") is False
