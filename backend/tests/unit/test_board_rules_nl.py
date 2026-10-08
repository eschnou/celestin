"""Spec 017 R6, §4.6: the tool rules in a Dutch course.

French and English stay in `test_*_rules.py` and `test_*_rules_en.py`, untouched. The Dutch rows keep the Belgian
notation by reference (a decimal comma, outward brackets) and add the Dutch words: one accepted and one refused
sentence per `PACK_WORDS` entry, the hole phrases, the hand-written intervals and pairs a Flemish teacher writes.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.expression import FUNCTIONS
from app.domain.figure import Figure
from app.domain.plot import PlotBlock
from app.services.tools.figures import COORDS, DEGREES, INTERVAL, LENGTH, NUMBER, _bare, _number, figure_refusal
from app.services.tools.flowcharts import HOLE_WORDS
from app.services.tools.plots import COMMA, GROUPS, PACK_WORDS, PACK_WORDS_BY_LANGUAGE, gives_away, plot_refusal
from tests.unit.test_board_rules_by_language import FLOWCHARTS, refused
from tests.unit.test_figure_models import VALID as FIGURES

NL = "nl"
PLOT: TypeAdapter[PlotBlock] = TypeAdapter(PlotBlock)
FIGURE: TypeAdapter[Any] = TypeAdapter(Figure)


def P(**changes: Any) -> PlotBlock:
    base: dict[str, Any] = {"type": "plot", "x_range": [-5, 5], "y_range": [-5, 5], "x_title": "$x$", "y_title": "$y$"}
    return PLOT.validate_python({**base, **changes})


def rule(plot: PlotBlock, pack: str | None, language: str = NL) -> str | None:
    found = plot_refusal(plot, "blocks[0]", pack, language)  # type: ignore[arg-type]
    return None if found is None else found[0]


# --- the pack must name the function, in Dutch ------------------------------------------------------------------

PACK_SENTENCES = [
    ("e^x", "De exponentiële functie met grondtal $e$.", True),
    ("e^x", "$\\exp x$", True),
    ("e^x", "Een exponentiële functie.", True),
    ("e^x", "Exponentiële groei van een populatie.", False),
    ("e^x", "De exponentiële groei is snel.", False),
    ("ln(x)", "De natuurlijke logaritme, $\\ln x$.", True),
    ("ln(x)", "De neperiaanse logaritme.", True),
    ("ln(x)", "De logaritme met grondtal $e$.", True),
    ("ln(x)", "Een logaritmische schaal.", False),
    ("ln(x)", "De logaritme met grondtal 10.", False),
    ("log(x)", "De 10-logaritme.", True),
    ("log(x)", "De tientallige logaritme.", True),
    ("log(x)", "De logaritme met grondtal 10.", True),
    ("log(x)", "De natuurlijke logaritme, $\\ln x$.", False),
    ("log(x)", "Een logaritmische schaal.", False),
    ("cbrt(x)", "De derdemachtswortel.", True),
    ("cbrt(x)", "$\\sqrt[3]{x}$", True),
    ("cbrt(x)", "De vierkantswortel $\\sqrt{x}$.", False),
    ("cbrt(x)", "$\\sqrt[4]{x}$", False),
    ("sin(x)", "$\\sin x$", True),
    ("sin(x)", "De sinus van een scherpe hoek is overstaande door schuine zijde.", True),
    ("sin(x)", "Een sinusoïdale spanning.", True),
    ("sin(x)", "De cosinus van een scherpe hoek.", False),
    ("sin(x)", "$\\sinh x$ en $\\arcsin x$", False),
    ("cos(x)", "De cosinus.", True),
    ("cos(x)", "$\\cos x$", True),
    ("cos(x)", "De sinus van een scherpe hoek.", False),
    ("cos(x)", "$\\cosh x$", False),
    ("tan(x)", "De tangens van een hoek.", True),
    ("tan(x)", "$\\tan x$ en $\\operatorname{tg} x$", True),
    ("tan(x)", "Sinus, cosinus en tangens.", True),
    ("tan(x)", "De vergelijking van de raaklijn in A", False),
    ("tan(x)", "De raaklijn aan de kromme in het punt met abscis 1.", False),
    ("tan(x)", "$\\tanh x$ en $\\arctan x$", False),
]


@pytest.mark.parametrize("expr,pack,allowed", PACK_SENTENCES)
def test_the_dutch_pack_names_the_function_not_the_word(expr: str, pack: str, allowed: bool) -> None:
    plot = P(x_range=[0.5, 1.5], y_range=[-5, 25], curves=[{"expr": expr}])
    assert rule(plot, pack) == (None if allowed else "pack_function")


def test_every_dutch_entry_has_a_sentence_it_accepts_and_one_it_refuses() -> None:
    assert set(PACK_WORDS_BY_LANGUAGE["nl"]) == set(PACK_WORDS) == set(FUNCTIONS) - {"sqrt", "abs"}
    named = {"e^x": "exp", "2^x": "exp"}
    seen = {(named.get(expr, expr.split("(")[0]), allowed) for expr, _, allowed in PACK_SENTENCES}
    assert seen == {(name, allowed) for name in PACK_WORDS_BY_LANGUAGE["nl"] for allowed in (True, False)}


def test_each_languages_pack_licenses_only_its_own_words() -> None:
    plot = P(x_range=[0.5, 1.5], y_range=[-5, 25], curves=[{"expr": "ln(x)"}])
    assert rule(plot, "De natuurlijke logaritme") is None
    assert rule(plot, "Le logarithme népérien") == "pack_function"
    assert rule(plot, "The natural logarithm") == "pack_function"
    assert rule(plot, "De natuurlijke logaritme", "fr") == "pack_function"
    assert rule(plot, "De natuurlijke logaritme", "en") == "pack_function"


# --- what an open exercise may not show -------------------------------------------------------------------------


def test_the_decimal_comma_is_one_value_and_a_comma_with_a_space_separates() -> None:
    assert COMMA["nl"] is COMMA["fr"]  # the Belgian convention, by reference
    assert COMMA["nl"].split("(0,5)") == ["(0,5)"]
    assert COMMA["nl"].split("(1, 4)") == ["(1", " 4)"]


@pytest.mark.parametrize(
    ("text", "gives"),
    [
        ("(1, 4)", True),
        ("(1 ; 4)", True),
        ("(-1, -4)", True),
        ("]2 ; 3[", True),
        ("[0 ; 5]", True),
        ("]−∞ ; 2]", True),
        ("(2, 5]", True),
        ("[2, 5)", True),
        ("(0,5)", False),
        ("(1,4)", False),
        ("$f$", False),
        ("Afstand (m)", False),
        ("f(x) = 2", True),
    ],
)
def test_gives_away_in_dutch(text: str, gives: bool) -> None:
    assert gives_away(text, NL) is gives


def test_the_groups_are_the_english_ones_which_hold_the_french_shapes_too() -> None:
    # Outward brackets (the board's) and the mixed ones a teacher writes by hand.
    assert GROUPS["nl"] is GROUPS["en"] and GROUPS["fr"].pattern in GROUPS["nl"].pattern


# --- hand-written notation in a figure ---------------------------------------------------------------------------


def figure(base: str, language: str = NL, **changes: Any) -> tuple[str, str] | None:
    return figure_refusal(FIGURE.validate_python({**FIGURES[base], **changes}), "blocks[0]", language)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "label",
    ["A = ]2 ; 3[", "B = ]2, 3[", "$[0 ; 5]$", "$]-\\infty ; 2]$", "P = (2 ; 3)", "P = (2, 3)", "C = [1, 4]"],
)
def test_a_hand_written_interval_or_pair_is_refused_in_a_dutch_caption(label: str) -> None:
    found = figure("sets", caption=label)
    assert found is not None and found[0] == "label_notation", (label, found)


@pytest.mark.parametrize("caption", ["De verzamelingen A en B", "Een verzameling van 12 elementen", "Figuur 3"])
def test_a_dutch_caption_is_not_read_as_notation(caption: str) -> None:
    assert figure("sets", caption=caption) is None


def test_the_patterns_are_recognised_in_both_separators() -> None:
    """On the label as the rule reads it (`_bare`: no spaces, no LaTeX sizing)."""
    for text in ("]2 ; 3[", "]2, 3[", "[0 ; 5]", "]−∞ ; 2]", "[2, 5["):
        assert INTERVAL["nl"].search(_bare(text)), text
    for text in ("(2 ; −1,5)", "(2, 3)", "(−3 ; 4)"):
        assert COORDS["nl"].search(_bare(text)), text
    assert not INTERVAL["nl"].search(_bare("De cirkel"))
    assert INTERVAL["nl"].search(_bare("]2, 3[")) and not INTERVAL["fr"].search(_bare("]2, 3["))  # French needs `;`


# --- numbers -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "value"), [("2,5", 2.5), ("12", 12.0), ("0,45", 0.45), ("1000,5", 1000.5)])
def test_a_dutch_number_has_a_decimal_comma(text: str, value: float) -> None:
    assert _number(text, NL) == value
    assert NUMBER["nl"] is NUMBER["fr"]


def test_measures_are_read_with_a_decimal_comma() -> None:
    assert DEGREES["nl"].match("37,5°") and LENGTH["nl"].match("3,5 cm".replace(" ", ""))
    assert DEGREES["nl"] is DEGREES["fr"] and LENGTH["nl"] is LENGTH["fr"]


# --- flowchart holes ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "in te vullen", "Aan te vullen", "vul in", "Vul aan", "vul hier in", "??? te vinden", "te bepalen",
        "Ontbrekende stap", "ontbrekend", "Vak 3", "stap nr 2 ontbreekt".replace("ontbreekt", "in te vullen"),
        "Verborgen stap", "onbekend", "tbd", "Vak 3 in te vullen door de leerling",
        "Nog in te vullen", "invullen", "Hier invullen", "Waarde ontbreekt", "Vak ontbreekt", "leeg", "leeg vak",
        "Vul het antwoord in", "blanco",
    ],
)
def test_a_dutch_hole_phrase_is_a_hole(text: str) -> None:
    from app.services.tools.flowcharts import _plain_words

    assert HOLE_WORDS["nl"].fullmatch(_plain_words(text)), text


@pytest.mark.parametrize(
    "text",
    ["Is het quotiënt constant?", "Bereken het verschil", "De vorm invullen in de tabel", "Stap uitvoeren", "Ja", "Einde"],
)
def test_an_ordinary_dutch_step_is_not_a_hole(text: str) -> None:
    from app.services.tools.flowcharts import _plain_words

    assert not HOLE_WORDS["nl"].fullmatch(_plain_words(text)), text


def test_a_hole_in_a_flowchart_is_refused_through_the_tool_in_dutch() -> None:
    def with_text(text: str) -> dict[str, Any]:
        nodes = [dict(n) for n in FLOWCHARTS["method"]["nodes"]]
        nodes[2]["text"] = text
        return {**FLOWCHARTS["method"], "nodes": nodes}

    assert "marque un trou" in (refused(with_text("In te vullen"), NL) or "")
    assert refused(with_text("Is het quotiënt constant?"), NL) is None
    assert refused(with_text("To complete"), NL) is None  # an English hole is not a Dutch one
