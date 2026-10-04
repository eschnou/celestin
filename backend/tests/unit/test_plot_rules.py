from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.board import BoardCard
from app.domain.errors import ToolValidationError
from app.domain.expression import FUNCTIONS, MAX_DEPTH
from app.domain.plot import PlotBlock
from app.services.tools import plots as plot_rules
from app.services.tools import registry
from app.services.tools.plots import PACK_WORDS, gives_away, plot_refusal, plots_refusal, plots_summary
from tests.fixtures.curricula import ctx_for
from tests.unit.test_plot_models import VALID

ADAPTER: TypeAdapter[PlotBlock] = TypeAdapter(PlotBlock)
CARD: TypeAdapter[Any] = TypeAdapter(BoardCard)
CTX = ctx_for()
# Chapter 1 (sequences): names no exponential, logarithm, trigonometric function or cube root.
PACK_1 = (Path(__file__).resolve().parents[3] / "courses" / "chapitre_1" / "pack.md").read_text(encoding="utf-8")


def P(**changes: Any) -> PlotBlock:
    """A plot in the window [−5 ; 5]², with whatever the case adds."""
    base: dict[str, Any] = {"type": "plot", "x_range": [-5, 5], "y_range": [-5, 5], "x_title": "$x$", "y_title": "$y$"}
    return ADAPTER.validate_python({**base, **changes})


def rule(plot: PlotBlock, pack: str | None = None) -> str | None:
    found = plot_refusal(plot, "blocks[0]", pack)
    return None if found is None else found[0]


def message(plot: PlotBlock, pack: str | None = None) -> str:
    found = plot_refusal(plot, "blocks[0]", pack)
    assert found is not None
    assert found[1].startswith("Le graphique blocks[0]")
    return found[1]


def card(kind: str, *plots: PlotBlock) -> Any:
    body: dict[str, Any] = {"kind": kind, "title": "Graphique"}
    if kind == "explanation":
        body["blocks"] = [p.model_dump() for p in plots]
    else:
        body["statement"] = "Lis le graphique."
        body["drawing"] = plots[0].model_dump()
        if kind == "worked_example":
            body["steps"] = [{"tex": "x = 1"}]
    return CARD.validate_python(body)


def refusal_on(kind: str, *plots: PlotBlock, pack: str | None = None) -> tuple[str, str] | None:
    built = card(kind, *plots)
    items = (
        [(f"blocks[{i}]", p) for i, p in enumerate(built.blocks)]
        if kind == "explanation"
        else [("drawing", built.drawing)]
    )
    return plots_refusal(items, built, replace(CTX, pack=pack))


@pytest.mark.parametrize("name", sorted(VALID))
def test_every_valid_plot_passes(name: str) -> None:
    assert plot_refusal(ADAPTER.validate_python(VALID[name]), "blocks[0]") is None


@pytest.mark.parametrize("name", sorted(VALID))
def test_every_valid_plot_passes_against_the_sequences_pack(name: str) -> None:
    assert plot_refusal(ADAPTER.validate_python(VALID[name]), "blocks[0]", PACK_1) is None


# ---------------------------------------------------------------- the window


@pytest.mark.parametrize(
    "changes,named",
    [
        ({"x_range": [2, 2]}, "x_range va du plus petit au plus grand (2 puis 2)"),
        ({"y_range": [3, -3]}, "y_range va du plus petit au plus grand (3 puis -3)"),
        ({"x_range": [0, 1e-200]}, "ne se gradue pas"),
        ({"x_range": [0, 1e7]}, "un million"),
        ({"y_range": [-2e6, 0]}, "y_range [-2e+06 ; 0]"),
    ],
)
def test_window(changes: dict[str, Any], named: str) -> None:
    plot = P(points=[{"x": 0, "y": 0}], **changes)
    assert rule(plot) == "window"
    assert named in message(plot)


def test_window_boundaries() -> None:
    assert rule(P(x_range=[0, 0.001], points=[{"x": 0, "y": 0}])) is None
    assert rule(P(x_range=[-1e6, 1e6], points=[{"x": 0, "y": 0}])) is None


@pytest.mark.parametrize("pair", [[1.1, 1.101], [2.5, 2.501], [0.3, 0.301]])
def test_a_thousandth_wide_window_passes_despite_float_noise(pair: list[float]) -> None:
    # 1.101 − 1.1 is 0.0009999999999998899: the width the model wrote, not less.
    assert rule(P(x_range=pair, points=[{"x": pair[0], "y": 0}])) is None
    assert rule(P(y_range=pair, points=[{"x": 0, "y": pair[0]}])) is None


def test_a_window_under_a_thousandth_is_refused() -> None:
    assert rule(P(x_range=[1.1, 1.1009], points=[{"x": 1.1, "y": 0}])) == "window"


# ----------------------------------------------------------------- the steps


def test_step_accepts_float_noise_at_the_limit() -> None:
    # (−4.6 − −4.9) / 0.01 is 30.000000000000007: thirty intervals.
    assert rule(P(x_range=[-4.9, -4.6], x_step=0.01, points=[{"x": -4.7, "y": 0}])) is None
    assert rule(P(x_range=[-1.5, 1.5], x_step=0.1, points=[{"x": 0, "y": 0}])) is None


@pytest.mark.parametrize(
    "changes,named",
    [
        ({"x_range": [0, 3.1], "x_step": 0.1}, "31 intervalles ; 30 au plus"),
        ({"x_range": [0, 1], "x_step": 2}, "x_step 2 est plus grand que la fenêtre (0 à 1)"),
        ({"x_range": [0, 0.001], "x_step": 0.00005}, "plus de 4 décimales"),
        ({"x_range": [0, 1], "x_step": 1 / 3}, "plus de 4 décimales"),
        ({"y_range": [0, 100], "y_step": 1}, "y_step 1 coupe la fenêtre en 100 intervalles"),
    ],
)
def test_step(changes: dict[str, Any], named: str) -> None:
    changes.setdefault("x_range", [-5, 5])
    x0 = changes["x_range"][0]
    y0 = changes.get("y_range", [-5, 5])[0]
    plot = P(points=[{"x": x0, "y": y0}], **changes)
    assert rule(plot) == "step"
    assert named in message(plot)


def test_step_boundaries() -> None:
    assert rule(P(x_range=[0, 0.3], x_step=0.3, points=[{"x": 0.1, "y": 0}])) is None
    assert rule(P(x_range=[0, 0.01], x_step=0.0005, points=[{"x": 0.005, "y": 0}])) is None


# -------------------------------------------------------------- orthonormal


def test_orthonormal() -> None:
    assert rule(P(orthonormal=True, curves=[{"expr": "x"}])) is None  # ratio 1
    assert rule(P(orthonormal=True, x_range=[-3, 3], y_range=[-1, 9], curves=[{"expr": "x"}])) is None  # 1.67
    tall = P(orthonormal=True, x_range=[-5, 5], y_range=[-20, 20], curves=[{"expr": "x"}])
    assert rule(tall) == "orthonormal"
    assert "4 fois x_range" in message(tall)
    flat = P(orthonormal=True, x_range=[0, 100], y_range=[0, 10], curves=[{"expr": "x/10"}])
    assert rule(flat) == "orthonormal"
    # Not orthonormal: any proportions.
    assert rule(P(x_range=[0, 100], y_range=[0, 10], curves=[{"expr": "x/10"}])) is None


@pytest.mark.parametrize(
    "x_range,y_range,refused",
    [
        ([-5, 5], [-10, 10], False),  # exactly 2
        ([-5, 5], [-10, 10.01], True),  # 2.001
        ([0, 10], [0, 4], False),  # exactly 0.4
        ([0, 10], [0, 3.99], True),  # 0.399
        # Float noise on the bounds the model wrote: 0.39999999999999997 and 2.0000000000000004.
        ([0, 1], [0.3, 0.7], False),
        ([0.2, 0.3], [0, 0.2], False),
    ],
)
def test_orthonormal_boundaries(x_range: list[float], y_range: list[float], refused: bool) -> None:
    plot = P(orthonormal=True, x_range=x_range, y_range=y_range, points=[{"x": x_range[0], "y": y_range[0]}])
    assert rule(plot) == ("orthonormal" if refused else None)


def test_empty() -> None:
    assert rule(P()) == "empty"
    assert "rien à tracer" in message(P())


# ------------------------------------------------------------ expressions


@pytest.mark.parametrize(
    "layer,expr,code,named",
    [
        ("curves", "1e-3x", "expr.scientific", "« 1e-3x » — pas de notation scientifique : écris 0.001 ou 10^-3."),
        ("curves", "\\frac{1}{x}", "expr.latex", "pas du LaTeX"),
        ("curves", "1/2x", "expr.ambiguous", "1/(2x)"),
        ("curves", "y = 2x+1", "expr.equation", "sans « y = »"),
        ("curves", "2,5x", "expr.comma", "point"),
        ("curves", "x+t", "expr.variables", "une seule variable"),
        ("curves", "sen(x)", "expr.unknown_name", "« sen » inconnu"),
        ("sequences", "2x-1", "expr.unknown_name", "permis : n"),
        ("curves", "x^", "expr.syntax", "incomplète"),
    ],
)
def test_expression_refusals_name_the_layer(layer: str, expr: str, code: str, named: str) -> None:
    item: dict[str, Any] = {"expr": expr} if layer == "curves" else {"expr": expr, "last": 3}
    plot = P(**{layer: [item]})
    text = message(plot)
    assert rule(plot) == code
    assert named in text
    assert text.startswith(
        "Le graphique blocks[0], courbe 1" if layer == "curves" else "Le graphique blocks[0], suite 1"
    )


def test_a_nesting_too_deep_is_refused_by_the_parser() -> None:
    assert MAX_DEPTH == 24  # frontend/src/components/celestin/plot/expression.ts holds the same
    deep = "(" * (MAX_DEPTH + 1) + "x" + ")" * (MAX_DEPTH + 1)
    plot = P(curves=[{"expr": deep}])
    assert rule(plot) == "expr.depth"
    assert "trop imbriquée" in message(plot)
    # Exactly the limit is drawn.
    assert rule(P(curves=[{"expr": "(" * MAX_DEPTH + "x" + ")" * MAX_DEPTH}])) is None


def test_the_second_curve_is_named() -> None:
    plot = P(curves=[{"expr": "x"}, {"expr": "x^"}])
    assert message(plot).startswith("Le graphique blocks[0], courbe 2 :")


# --------------------------------------------------------------- the pack


@pytest.mark.parametrize(
    "expr,shown",
    [
        ("ln(x)", "ln"),
        ("e^x", "une exponentielle"),
        ("2^x", "une exponentielle"),
        ("exp(x)", "une exponentielle"),
        ("cbrt(x)", "cbrt"),
        ("sin(x)", "sin"),
        ("3e", "une exponentielle"),
    ],
)
def test_pack_refuses_a_function_the_course_never_names(expr: str, shown: str) -> None:
    plot = P(x_range=[0.5, 3], y_range=[-5, 25], curves=[{"expr": expr}])
    assert rule(plot, PACK_1) == "pack_function"
    assert f"{shown} n'apparaît pas dans le cours" in message(plot, PACK_1)
    assert rule(plot, None) is None  # no pack, no check


# A pack sentence per entry that names the function (allowed), and one that only
# shares its root or names something else (not allowed).
PACK_SENTENCES: list[tuple[str, str, bool]] = [
    ("exp(x)", "La fonction exponentielle de base $\\mathrm{e}$.", True),
    ("exp(x)", "la fonction $x \\mapsto \\mathrm{e}^{x}$", True),
    ("exp(x)", "On note aussi $\\exp(x)$.", True),
    ("exp(x)", "La décharge suit une exponentielle décroissante $U_0\\,\\mathrm{e}^{-t/\\tau}$.", True),
    ("e^x", "$f(x) = {e}^{x}$", True),
    ("2^x", "La fonction exponentielle de base 2", True),
    ("exp(x)", "Une population a une croissance exponentielle.", False),
    ("2^x", "une décroissance exponentielle", False),
    ("exp(x)", "L'électron $e^-$ et le positron $\\mathrm{e}^{+}$.", False),
    ("exp(x)", "Le potentiel standard $E^{\\circ}$.", False),
    ("ln(x)", "Le logarithme népérien", True),
    ("ln(x)", "On note $\\ln x$.", True),
    ("ln(x)", "Le logarithme de base $\\mathrm{e}$.", True),
    ("ln(x)", "Le pH se lit sur une échelle logarithmique.", False),
    ("ln(x)", "Le logarithme décimal, noté $\\log x$.", False),
    ("log(x)", "Le logarithme décimal.", True),
    ("log(x)", "$\\log_{10} 100$", True),
    ("log(x)", "$\\mathrm{pH} = -\\log[\\mathrm{H_3O^+}]$", True),
    ("log(x)", "Le logarithme népérien, noté $\\ln x$.", False),
    ("log(x)", "une échelle logarithmique", False),
    ("cbrt(x)", "la racine cubique", True),
    ("cbrt(x)", "$\\sqrt[3]{x}$", True),
    ("cbrt(x)", "la racine carrée $\\sqrt{x}$", False),
    ("cbrt(x)", "$\\sqrt[4]{x}$", False),
    ("sin(x)", "$\\sin x$", True),
    # The sine of an angle is the function sin; a sinusoid is its graph.
    ("sin(x)", "Le sinus d'un angle aigu est le rapport du côté opposé à l'hypoténuse.", True),
    ("sin(x)", "Une tension sinusoïdale.", True),
    ("sin(x)", "Le cosinus d'un angle aigu.", False),
    ("sin(x)", "$\\sinh x$ et $\\arcsin x$", False),
    ("cos(x)", "le cosinus", True),
    ("cos(x)", "$\\cos x$", True),
    ("cos(x)", "Le sinus d'un angle aigu.", False),
    ("cos(x)", "$\\cosh x$", False),
    ("tan(x)", "la fonction tangente", True),
    ("tan(x)", "$\\tan x$", True),
    ("tan(x)", "La tangente d'un angle aigu.", True),
    ("tan(x)", "la tangente de l'angle $\\hat{A}$", True),
    ("tan(x)", "$\\operatorname{tg} \\alpha$", True),
    ("tan(x)", "Sinus, cosinus et tangente d'un angle.", True),
    ("tan(x)", "l'équation de la tangente en A", False),
    ("tan(x)", "La tangente à la courbe au point d'abscisse 1.", False),
    ("tan(x)", "la pente de la tangente de la courbe en A", False),
    ("tan(x)", "La droite est tangente au cercle.", False),
    ("tan(x)", "$\\tanh x$ et $\\arctan x$", False),
]


@pytest.mark.parametrize("expr,pack,allowed", PACK_SENTENCES)
def test_pack_words_name_the_function_not_the_word(expr: str, pack: str, allowed: bool) -> None:
    plot = P(x_range=[0.5, 1.5], y_range=[-5, 25], curves=[{"expr": expr}])
    assert rule(plot, pack) == (None if allowed else "pack_function")


def test_every_pack_entry_has_a_sentence_it_accepts_and_one_it_refuses() -> None:
    assert set(PACK_WORDS) == set(FUNCTIONS) - {"sqrt", "abs"}
    named = {"e^x": "exp", "2^x": "exp"}
    seen = {(named.get(expr, expr.split("(")[0]), allowed) for expr, _, allowed in PACK_SENTENCES}
    assert seen == {(name, allowed) for name in PACK_WORDS for allowed in (True, False)}


def test_a_geometric_sequence_is_not_an_exponential() -> None:
    plot = P(x_range=[0, 8], y_range=[0, 4], sequences=[{"expr": "3*0.5^(n-1)", "last": 7}])
    assert rule(plot, PACK_1) is None


def test_sqrt_and_abs_are_never_looked_up() -> None:
    assert rule(P(curves=[{"expr": "sqrt(abs(x))"}]), PACK_1) is None


# ---------------------------------------------------------------- domains


def test_domain() -> None:
    reversed_ = P(curves=[{"expr": "x", "domain": [2, 2]}])
    assert rule(reversed_) == "domain"
    assert "(2 puis 2)" in message(reversed_)
    outside = P(curves=[{"expr": "x", "domain": [7, 9]}])
    assert rule(outside) == "domain"
    assert "domain [7 ; 9] est hors de la fenêtre (x de -5 à 5)" in message(outside)
    assert rule(P(curves=[{"expr": "x", "domain": [-10, 10]}])) is None


def test_a_domain_touching_the_window_at_one_point_is_outside_it() -> None:
    # [5 ; 9] meets x in [−5 ; 5] at x = 5 only: nothing of the curve would show.
    plot = P(curves=[{"expr": "x", "domain": [5, 9]}])
    assert rule(plot) == "domain"
    assert "domain [5 ; 9] est hors de la fenêtre" in message(plot)
    assert rule(P(curves=[{"expr": "x", "domain": [4.9, 9]}])) is None


def test_undefined() -> None:
    plot = P(curves=[{"expr": "sqrt(x-10)"}])
    assert rule(plot) == "undefined"
    assert "n'est définie nulle part entre -5 et 5" in message(plot)
    seq = P(x_range=[0, 5], sequences=[{"expr": "sqrt(-n)", "first": 1, "last": 4}])
    assert rule(seq) == "undefined"
    assert "aucun n de 1 à 4" in message(seq)


def test_defined_on_a_sliver_of_the_window_is_enough() -> None:
    # sqrt(x − 4.9) is defined on the last tenth of [−5 ; 5] only: four samples.
    assert rule(P(curves=[{"expr": "sqrt(x-4.9)"}])) is None
    # A sequence defined for one n of the range passes; the others are skipped.
    assert rule(P(x_range=[0, 5], sequences=[{"expr": "sqrt(1-n)", "first": 1, "last": 4}])) is None


# ---------------------------------------------------------------- outside


def test_a_curve_above_the_window_is_outside() -> None:
    plot = P(curves=[{"expr": "x^2+20"}])
    assert rule(plot) == "outside"
    assert "ne passe pas dans la fenêtre (y de -5 à 5)" in message(plot)


@pytest.mark.parametrize(
    "x_range,y_range,expr",
    [
        ([-1.1, 1], [-0.5, 0.5], "1/x"),
        ([-1, 1], [-0.5, 0.5], "1/x"),
        ([1.4, 1.8], [-0.1, 0.1], "tan(x)"),
    ],
)
def test_a_pole_is_not_a_crossing(x_range: list[float], y_range: list[float], expr: str) -> None:
    assert rule(P(x_range=x_range, y_range=y_range, curves=[{"expr": expr}])) == "outside"


@pytest.mark.parametrize("expr", ["1000(x-0.0123)", "100000(x-0.01234)"])
def test_a_steep_line_crossing_between_samples_is_visible(expr: str) -> None:
    assert rule(P(y_range=[-1, 1], curves=[{"expr": expr}])) is None


def test_sequences_in_and_out_of_the_window() -> None:
    clipped = P(x_range=[0, 8], y_range=[0, 15], sequences=[{"expr": "2+3(n-1)", "last": 7}])
    assert rule(clipped) == "outside"
    assert "le terme n = 6 (17) sort de la fenêtre" in message(clipped)
    assert rule(P(x_range=[0, 8], y_range=[0, 22], sequences=[{"expr": "2+3(n-1)", "last": 7}])) is None
    beyond = P(x_range=[0, 5], y_range=[0, 22], sequences=[{"expr": "2+3(n-1)", "last": 7}])
    assert rule(beyond) == "outside"
    assert "n va de 1 à 7, hors de x_range (0 à 5)" in message(beyond)
    # An undefined term is skipped, not refused.
    assert rule(P(x_range=[0, 8], y_range=[-5, 5], sequences=[{"expr": "1/(n-3)", "last": 7}])) is None


def test_points_and_lines_outside() -> None:
    point = P(points=[{"x": 7, "y": 1, "label": "$A$"}])
    assert rule(point) == "outside"
    assert "point 1 ($A$) : (7 ; 1) est hors de la fenêtre" in message(point)
    line = P(lines=[{"vertices": [[10, 0], [20, 0]]}])
    assert rule(line) == "outside"
    assert "ligne 1 : elle ne passe pas" in message(line)
    assert rule(P(lines=[{"vertices": [[0, -100], [0, 100]]}])) is None
    assert rule(P(lines=[{"vertices": [[-10, -10], [10, 10]]}])) is None
    assert rule(P(points=[{"x": 5, "y": -5}])) is None  # on the corner


# --------------------------------------------------------------- endpoints


def test_endpoints() -> None:
    filled_pole = P(curves=[{"expr": "1/x", "domain": [0, 5], "start_dot": "filled"}])
    assert rule(filled_pole) == "endpoint"
    assert "start_dot en x = 0, où la courbe n'est pas définie" in message(filled_pole)
    hole = P(curves=[{"expr": "(x^2-1)/(x-1)", "domain": [-3, 1], "end_dot": "hollow"}])
    assert rule(hole) is None
    hollow_pole = P(curves=[{"expr": "1/x", "domain": [0, 5], "start_dot": "hollow"}])
    assert rule(hollow_pole) == "endpoint"
    assert "(0 ; 2e+08) est hors" in message(hollow_pole)
    filled_hole = P(curves=[{"expr": "(x^2-1)/(x-1)", "domain": [-3, 1], "end_dot": "filled"}])
    assert rule(filled_hole) == "endpoint"
    out = P(curves=[{"expr": "x", "domain": [-10, 3], "start_dot": "filled"}])
    assert rule(out) == "endpoint"
    assert "start_dot (-10 ; -10) est hors de la fenêtre" in message(out)


# ------------------------------------------------------------------ terms


def test_terms() -> None:
    assert rule(P(x_range=[0, 41], y_range=[0, 100], sequences=[{"expr": "2n", "last": 40}])) is None
    too_many = P(x_range=[0, 42], y_range=[0, 100], sequences=[{"expr": "2n", "last": 41}])
    assert rule(too_many) == "terms"
    assert "41 termes ; 40 au plus" in message(too_many)
    reversed_ = P(x_range=[0, 42], y_range=[0, 100], sequences=[{"expr": "2n", "first": 5, "last": 4}])
    assert rule(reversed_) == "terms"
    assert "first (5) vient après last (4)" in message(reversed_)


# ------------------------------------------------------ the open exercise


@pytest.mark.parametrize("flag", ["show_values", "guides"])
def test_exercise_values(flag: str) -> None:
    plot = P(curves=[{"expr": "x^2-4"}], points=[{"x": 2, "y": 0, flag: True}])
    found = refusal_on("exercise", plot)
    assert found is not None and found[0] == "exercise_values"
    assert found[1].startswith("Le graphique drawing, point 1 accompagne un exercice ouvert")
    assert refusal_on("worked_example", plot) is None
    assert refusal_on("explanation", plot) is None


@pytest.mark.parametrize(
    "text",
    [
        "$y = 2x+1$",
        "$S(1\\,;\\,-4)$",
        "(2, 3)",
        "$(0{,}5 ; 12)$",
        "$x_0 \\approx 1{,}4$",
        "$x \\mapsto 2x+1$",
        "$x_0 ≈ 1,4$",
        "$S(1 ; −4)$",
        # A fractional vertex, the usual answer of « trouve le sommet ».
        "Sommet $S\\left(\\frac{1}{2} ; -\\frac{9}{4}\\right)$",
        "$S\\left(\\dfrac{1}{2}\\,;\\,-\\dfrac{9}{4}\\right)$",
        "$S(1/2 ; -9/4)$",
        "$(\\pi ; 0)$",
        "$\\left(\\frac{\\pi}{2} ; 1\\right)$",
        "$(\\sqrt{2} ; 0)$",
        "$S(x_S ; 2)$",
        # A comma then a sign or a space separates two members.
        "Le sommet est en $(1,-4)$",
        "$(-1,-4)$",
        "(1, 4)",
        "(0,5 s ; 12 cm)",
        "$(2\\ ;\\ 3)$",
        # Mappings, arrows, inequalities.
        "$f : x \\longmapsto x^2$",
        "$x \\to 2x+1$",
        "$x \\rightarrow 2x + 1$",
        "$x → 2x$",
        "$x_0 \\approxeq 1{,}4$",
        "$f(x) > 0$ pour $x > 2$",
        "$x \\leq 2$",
        "$x \\neq 1$",
        # The slanted signs FWB courses print, as characters and as commands.
        "$x ⩽ 2$",
        "$x ⩾ 0$",
        "$x ≦ 2$",
        "$x ≧ 0$",
        "$x \\leqslant 2$",
        "$x \\geqslant 0$",
        "$x \\leqq 2$",
        "$x \\geqq 0$",
        # Intervals, either way round.
        "$f$ est négative sur $]-1 ; 2[$",
        "Domaine : $[-2 ; 3[$",
        "$]-\\infty ; 2]$",
    ],
)
def test_gives_away(text: str) -> None:
    assert gives_away(text)


@pytest.mark.parametrize(
    "text",
    [
        "$f(x)$",
        "$\\mathcal{C}_f$",
        "$u_n$",
        "$v$ (m/s)",
        "Position (cm, toutes les 0,5 s)",
        "(0,5)",
        "$A$",
        "phase (2)",
        "$t$ (s)",
        "$v$ (m·s$^{-1}$)",
        "$v$ [m/s]",
        "$\\theta$ (°C)",
        "(t en s ; x en cm)",
        "$f(2)$",
        "$]a ; b[$",
        "$u_{n+1}$",
        "Graphique de $f$",
        # A command that only starts like a relation.
        "$\\leqslantfoo$",
        "$\\lefteqn{f}$",
    ],
)
def test_names_and_quantities_do_not_give_away(text: str) -> None:
    assert not gives_away(text)


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"curves": [{"expr": "2x+1", "label": "$y = 2x+1$"}]}, "courbe 1"),
        ({"points": [{"x": 1, "y": -4, "label": "$S(1\\,;\\,-4)$"}]}, "point 1"),
        ({"lines": [{"vertices": [[0, 0], [1, 1]], "label": "(2, 3)"}]}, "ligne 1"),
        ({"curves": [{"expr": "x"}], "caption": "La droite $y = 2x+1$"}, "caption"),
        ({"curves": [{"expr": "x"}], "y_title": "$y = f(x)$"}, "y_title"),
        ({"curves": [{"expr": "x"}], "x_title": "$x \\approx 1$"}, "x_title"),
        ({"curves": [{"expr": "x"}], "caption": "$f(x) ⩾ 0$ sur l'intervalle cherché"}, "caption"),
        ({"x_range": [0, 8], "sequences": [{"expr": "n", "last": 3, "label": "$u_n = n$"}]}, "suite 1"),
    ],
)
def test_exercise_text(changes: dict[str, Any], field: str) -> None:
    plot = P(**changes)
    found = refusal_on("exercise", plot)
    assert found is not None and found[0] == "exercise_text"
    assert found[1].startswith(f"Le graphique drawing, {field} : « ")
    assert "Les données vont dans l'énoncé" in found[1]
    assert refusal_on("worked_example", plot) is None


def test_gives_away_is_quick_on_a_hostile_caption() -> None:
    start = time.perf_counter()
    for text in ["(" + "1," * 100, "]" * 100 + "[" * 100, "(" * 200, "[" + "1 ;" * 66]:
        gives_away(text)
    assert time.perf_counter() - start < 0.05  # measured under 0.2 ms


def test_exercise_names_are_welcome() -> None:
    plot = P(
        x_title="$t$ (s)",
        y_title="$v$ (m/s)",
        curves=[{"expr": "x", "label": "$\\mathcal{C}_f$"}],
        points=[{"x": 1, "y": 1, "label": "$A$"}],
        caption="Position (cm, toutes les 0,5 s)",
    )
    assert refusal_on("exercise", plot) is None


def test_exercise_rules_come_first() -> None:
    # A broken window and a shown value: the exercise rule speaks first.
    plot = P(x_range=[0, 1e7], points=[{"x": 1, "y": 1, "show_values": True}])
    found = refusal_on("exercise", plot)
    assert found is not None and found[0] == "exercise_values"


# ---------------------------------------------------------------- per card


def test_two_plots_pass_and_a_third_is_the_boards_rule(caplog: pytest.LogCaptureFixture) -> None:
    # The plot rules hold no card limit of their own: display_board's, across every
    # drawing family, runs first.
    plot = P(curves=[{"expr": "x"}])
    assert refusal_on("explanation", plot, plot) is None
    assert refusal_on("explanation", plot, plot, plot) is None
    caplog.set_level(logging.INFO)
    with pytest.raises(ToolValidationError):
        registry.execute("display_board", _explain(*[plot.model_dump()] * 3), CTX)
    refused = [(r.message, getattr(r, "rule", None)) for r in caplog.records if r.message.endswith("_refused")]
    assert refused == [("drawing_refused", "per_card")]


def test_the_card_names_the_block_path() -> None:
    good = P(curves=[{"expr": "x"}])
    bad = P(curves=[{"expr": "x^2+20"}])
    found = refusal_on("explanation", good, bad)
    assert found is not None and found[1].startswith("Le graphique blocks[1], courbe 1")


def test_the_pack_comes_from_the_turn() -> None:
    plot = P(x_range=[0.5, 3], curves=[{"expr": "ln(x)"}])
    found = refusal_on("explanation", plot, pack=PACK_1)
    assert found is not None and found[0] == "pack_function"
    assert refusal_on("explanation", plot, pack=None) is None


# ----------------------------------------------------------------- summary


def test_summary_counts_layers_and_names_functions() -> None:
    motion = ADAPTER.validate_python(VALID["motion"])
    assert plots_summary([("drawing", motion)]) == {
        "count": 1,
        "layers": {"curves": 3, "sequences": 0, "points": 0, "lines": 0},
        "functions": [],
    }
    mixed = P(
        x_range=[0, 5],
        y_range=[-2, 40],
        curves=[{"expr": "2^x"}, {"expr": "sin(x)"}],
        sequences=[{"expr": "0.5^n", "last": 3}],
        points=[{"x": 1, "y": 1}],
    )
    summary = plots_summary([("blocks[0]", mixed), ("blocks[1]", motion)])
    assert summary["functions"] == ["exp", "sin"]
    assert summary["layers"] == {"curves": 5, "sequences": 1, "points": 1, "lines": 0}
    assert summary["count"] == 2


def test_summary_never_raises_on_a_bad_expression() -> None:
    plot = P(curves=[{"expr": "x^"}])
    assert plots_summary([("blocks[0]", plot)])["functions"] == []


def test_display_parses_each_expression_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The check and the log line share one parse per expression text.
    calls: list[str] = []
    real = plot_rules.parse

    def counted(source: str, variables: frozenset[str]) -> Any:
        calls.append(source)
        return real(source, variables)

    monkeypatch.setattr(plot_rules, "parse", counted)
    plot_rules._parsed.cache_clear()
    caplog.set_level(logging.INFO)
    block = {
        **VALID["parabola"],
        "curves": [{"expr": "x^2-4"}, {"expr": "2^x"}],
        "sequences": [{"expr": "0.5n", "last": 3}],
    }
    registry.execute("display_board", _explain(block), CTX)
    assert sorted(calls) == ["0.5n", "2^x", "x^2-4"]
    record = next(r for r in caplog.records if r.message == "plot_displayed")
    assert record.functions == ["exp"]  # type: ignore[attr-defined]
    assert record.layers == {"curves": 2, "sequences": 1, "points": 1, "lines": 0}  # type: ignore[attr-defined]


def test_six_heavy_curves_are_checked_quickly() -> None:
    heavy = P(
        x_range=[-10, 10],
        y_range=[-10, 10],
        curves=[{"expr": "sin(x)/x + sqrt(abs(x)) - 2x^2 + e^(-x/3)"}] * 6,
    )
    start = time.perf_counter()
    assert rule(heavy) is None
    assert time.perf_counter() - start < 0.5  # measured about 7 ms; generous for CI


# --------------------------------------------------- through display_board


def _explain(*blocks: dict[str, Any]) -> str:
    return json.dumps({"card": {"kind": "explanation", "title": "Graphique", "blocks": list(blocks)}})


def test_display_logs_counts_and_codes_never_content(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    registry.execute("display_board", _explain(VALID["parabola"]), CTX)
    record = next(r for r in caplog.records if r.message == "plot_displayed")
    assert record.layers == {"curves": 1, "sequences": 0, "points": 1, "lines": 0}  # type: ignore[attr-defined]
    assert record.functions == []  # type: ignore[attr-defined]
    logged = json.dumps([r.__dict__ for r in caplog.records], default=str)
    assert "x^2-4" not in logged and "$S$" not in logged


def test_a_broken_plot_logs_its_rule(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    broken = {**VALID["parabola"], "curves": [{"expr": "1e-3x"}]}
    with pytest.raises(ToolValidationError, match="notation scientifique"):
        registry.execute("display_board", _explain(broken), CTX)
    record = next(r for r in caplog.records if r.message == "plot_refused")
    assert record.rule == "expr.scientific"  # type: ignore[attr-defined]
    assert not any(r.message == "plot_displayed" for r in caplog.records)


@pytest.mark.parametrize(
    "where,text",
    [
        ("caption", "Sommet $S\\left(\\frac{1}{2} ; -\\frac{9}{4}\\right)$"),
        ("point", "$S(1/2 ; -9/4)$"),
        ("curve", "$f : x \\longmapsto x^2$"),
        ("caption", "Le sommet est en $(1,-4)$"),
        ("caption", "$f$ est négative sur $]-1 ; 2[$"),
    ],
)
def test_an_open_exercise_never_shows_the_vertex_it_asks_for(where: str, text: str) -> None:
    plot: dict[str, Any] = {**VALID["parabola"], "x_range": [-3, 4], "y_range": [-4, 6], "points": []}
    plot["curves"] = [{"expr": "x^2-x-2", "label": text if where == "curve" else "$f$"}]
    if where == "caption":
        plot["caption"] = text
    if where == "point":
        plot["points"] = [{"x": 0.5, "y": -2.25, "label": text}]
    card = {"kind": "exercise", "title": "Sommet", "statement": "Lis les coordonnées du sommet de la parabole."}
    with pytest.raises(ToolValidationError, match="Les données vont dans l'énoncé"):
        registry.execute("display_board", json.dumps({"card": {**card, "drawing": plot}}), CTX)


def test_latex_in_an_expression_reaches_the_parser() -> None:
    broken = {**VALID["parabola"], "curves": [{"expr": "\\frac{1}{x}"}]}
    with pytest.raises(ToolValidationError, match="pas du LaTeX"):
        registry.execute("display_board", _explain(broken), CTX)
