from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.board import ExerciseCard, ExplanationCard, WorkedExampleCard
from app.domain.curriculum import Curriculum
from app.domain.figure import Figure, FigureBlock
from app.services.tools.context import TurnContext
from app.services.tools.figures import figure_refusal, figures_refusal, figures_summary
from tests.unit.test_figure_models import AXES_ONLY, NESTED, STATS, VALID

ADAPTER: TypeAdapter[Any] = TypeAdapter(Figure)
BASES: dict[str, dict[str, Any]] = {**VALID, "nested": NESTED, "stats": STATS, "axes": AXES_ONLY}

TRIANGLE = {"A": [0, 0], "B": [4, 0], "C": [0, 3]}


def refusal(base: str, **changes: Any) -> tuple[str, str] | None:
    return figure_refusal(ADAPTER.validate_python({**BASES[base], **changes}), "blocks[0]")


def plane(points: dict[str, list[float]], *shapes: dict[str, Any], **changes: Any) -> tuple[str, str] | None:
    return refusal("plane", points=points, shapes=list(shapes), **changes)


def seg(a: str, b: str, **more: Any) -> dict[str, Any]:
    return {"draw": "segment", "of": [a, b], **more}


def angle(a: str, b: str, c: str, **more: Any) -> dict[str, Any]:
    return {"draw": "angle", "of": [a, b, c], **more}


def interval(start: float | None, end: float | None, closed: str, label: str | None = None) -> dict[str, Any]:
    return {"start": start, "end": end, "closed": closed, "label": label}


def line(*intervals: dict[str, Any], **changes: Any) -> tuple[str, str] | None:
    return refusal("number_line", intervals=list(intervals), marks=[], **changes)


def elements(*pairs: tuple[str, list[str]]) -> list[dict[str, Any]]:
    return [{"text": t, "within": w} for t, w in pairs]


@pytest.mark.parametrize("base", sorted(BASES))
def test_every_valid_figure_passes(base: str) -> None:
    assert refusal(base) is None


# Six angles around a point, 60° apart, none coded.
_HEX = {"O": [0, 0], **{n: [x, y] for n, (x, y) in zip("ABCDEF", [(2, 0), (1, 2), (-1, 2), (-2, 0), (-1, -2), (1, -2)])}}

CASES: list[tuple[str, Any, str, str]] = [
    ("arity", lambda: plane(TRIANGLE, {"draw": "segment", "of": ["A", "B", "C"]}), "shapes[0] (segment)", "of attend 2 points, il y en a 3"),
    ("arity", lambda: plane(TRIANGLE, {"draw": "arc", "of": ["A", "B"]}), "(arc)", "une extrémité, le centre"),
    ("repeated", lambda: plane(TRIANGLE, seg("A", "A")), "shapes[0]", "« A » apparaît deux fois dans of"),
    ("repeated", lambda: refusal("sets", elements=elements(("1", ["A", "A"]))), "elements[0]", "« A » apparaît deux fois"),
    ("repeated", lambda: refusal("sets", shade=[["A", "B"], ["B", "A"]]), "shade[1]", "déjà hachurée"),
    ("repeated", lambda: refusal("number_line", marks=[{"x": 1}, {"x": 1.0}]), "marks", "1 apparaît deux fois"),
    ("repeated", lambda: refusal("sets", sets=[{"id": "A", "label": "x"}, {"id": "A", "label": "y"}]), "sets", "« A » apparaît deux fois"),
    ("repeated", lambda: refusal("nested", shade=[["N"], ["N", "Z"]]), "shade[1]", "déjà hachurée"),
    ("unknown_point", lambda: plane(TRIANGLE, seg("A", "D")), "shapes[0] (segment)", "le point « D » n'est pas dans points"),
    ("field", lambda: plane(TRIANGLE, {"draw": "line", "of": ["A", "B"], "radius": 2}), "(line)", "radius ne sert qu'à un cercle"),
    ("field", lambda: plane(TRIANGLE, {"draw": "circle", "of": ["A", "B"], "marks": 1}), "(circle)", "marks (le codage)"),
    ("field", lambda: plane(TRIANGLE, {"draw": "right_angle", "of": ["B", "A", "C"], "marks": 1}), "(right_angle)", "marks"),
    ("circle", lambda: plane(TRIANGLE, {"draw": "circle", "of": ["A", "B"], "radius": 2}), "(circle)", "pas les deux, ni aucun"),
    ("circle", lambda: plane(TRIANGLE, {"draw": "circle", "of": ["A"]}), "(circle)", "pas les deux, ni aucun"),
    ("degenerate", lambda: plane({**TRIANGLE, "D": [0, 0]}, seg("A", "D")), "shapes[0]", "A et D sont au même endroit"),
    ("degenerate", lambda: plane({"A": [0, 0], "B": [1, 1], "C": [2, 2]}, {"draw": "polygon", "of": ["A", "B", "C"]}), "(polygon)", "le polygone est plat"),
    ("degenerate", lambda: plane({"A": [2, 0], "B": [0, 0], "C": [4, 0]}, angle("A", "B", "C")), "(angle)", "nul ou plat"),
    ("degenerate", lambda: plane({"A": [0, 0], "B": [10, 10]}, {"draw": "circle", "of": ["A"], "radius": 0.01}), "(circle)", "trop petit"),
    ("crossed", lambda: plane({"A": [0, 0], "B": [2, 2], "C": [2, 0], "D": [0, 2]}, {"draw": "polygon", "of": ["A", "B", "C", "D"]}), "(polygon)", "des côtés se croisent"),
    ("close_points", lambda: plane({"A": [0, 0], "B": [0.001, 0], "C": [10, 10]}, seg("A", "B")), "", "A et B sont presque au même endroit"),
    ("not_right", lambda: plane({**TRIANGLE, "C": [1, 3]}, {"draw": "right_angle", "of": ["B", "A", "C"]}), "(right_angle)", "l'angle en A mesure 72°"),
    ("arc_radius", lambda: plane({"A": [3, 0], "O": [0, 0], "B": [0, 3.5]}, {"draw": "arc", "of": ["A", "O", "B"]}), "(arc)", "(3 et 3.5)"),
    ("codage", lambda: plane(TRIANGLE, seg("A", "B", marks=1), seg("A", "C", marks=1)), "shapes[0] et shapes[1]", "mesurent 4 et 3"),
    ("codage", lambda: plane({"A": [0, 0], "B": [4, 0], "C": [0, 3], "D": [9, 0]}, seg("A", "C", marks=2), seg("B", "D", marks=2)), "shapes[0] et shapes[1]", "mesurent 3 et 5"),
    (
        "codage",
        lambda: plane(
            {"O": [0, 0], "A": [1, 0], "B": [0.766, 0.643], "C": [0.574, 0.819]},
            angle("A", "O", "B", marks=1),
            angle("A", "O", "C", marks=1),
        ),
        "shapes[0] et shapes[1]",
        "mesurent 40° et 55°",
    ),
    ("codage", lambda: plane(_HEX, *(angle(a, "O", b) for a, b in zip("ABCDEF", "BCDEFA"))), "", "6 angles sans codage"),
    ("measure", lambda: plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$40°$")), "shapes[0] (angle)", "l'étiquette dit 40° mais l'angle en B mesure 45°"),
    ("measure", lambda: plane(TRIANGLE, seg("A", "B", label="$4$ cm"), seg("B", "C", label="6 cm")), "", "shapes[0] et shapes[1]"),
    ("window", lambda: plane(TRIANGLE, x_range=[5, 0]), "", "x_range va du plus petit au plus grand (5 puis 0)"),
    ("window", lambda: plane(TRIANGLE, y_range=[2, 2]), "", "y_range va du plus petit au plus grand (2 puis 2)"),
    ("window", lambda: plane({"A": [3, 1]}, axes=True, x_range=[2, 8]), "", "avec axes, x_range contient 0"),
    ("outside", lambda: plane(TRIANGLE, x_range=[0, 3]), "", "le point B (4 ; 0) sort de x_range (0 à 3)"),
    ("outside", lambda: plane({"O": [0, 0]}, {"draw": "circle", "of": ["O"], "radius": 2}, y_range=[-1, 1]), "shapes[0] (circle)", "sort de y_range"),
    ("label_notation", lambda: plane(TRIANGLE, seg("A", "B", label="$(2 ; 3)$")), "", "« $(2 ; 3)$ »"),
    ("label_notation", lambda: line(interval(2, 5, "left", "$[2 ; 5[$")), "", "à la main"),
    ("label_notation", lambda: refusal("number_line", caption="S = ]−∞ ; 2]"), "", "show_values"),
    ("label_notation", lambda: refusal("sets", caption="A = [0 ; 1]"), "", "à la main"),
    ("empty", lambda: refusal("plane", points={}, shapes=[]), "", "la figure est vide"),
    ("empty", lambda: refusal("number_line", intervals=[], marks=[]), "", "la droite graduée est vide"),
    ("order", lambda: line(interval(2, 2, "both")), "intervals[0]", "[2 ; 2] est un seul nombre"),
    ("order", lambda: line(interval(5, 2, "both")), "intervals[0]", "start (5) doit être plus petit que end (2)"),
    ("infinite_bound", lambda: line(interval(None, 2, "both")), "intervals[0]", "−∞ n'est jamais compris"),
    ("infinite_bound", lambda: line(interval(2, None, "right")), "intervals[0]", "+∞ n'est jamais compris"),
    ("union", lambda: line(interval(None, 2, "right", "$S$"), interval(2, 5, "neither", "$S$")), "intervals[0] et intervals[1]", "« $S$ »"),
    ("union", lambda: line(interval(3, 6, "both", "$S$"), interval(0, 4, "both", "$S$")), "intervals[0] et intervals[1]", "un seul intervalle"),
    ("set_count", lambda: refusal("sets", sets=[{"id": "A", "label": "x"}], elements=[], shade=[]), "", "layout « overlap » dessine 2 ou 3 ensembles, il y en a 1"),
    ("set_count", lambda: refusal("sets", layout="separate", sets=[{"id": c, "label": c} for c in "ABCD"], elements=[], shade=[]), "", "il y en a 4"),
    ("unknown_set", lambda: refusal("sets", elements=elements(("1", ["C"]))), "elements[0]", "l'ensemble « C » n'est pas dans sets"),
    ("unknown_set", lambda: refusal("sets", shade=[["C"]]), "shade[0]", "« C »"),
    ("region", lambda: refusal("sets", layout="separate", elements=elements(("1", ["A", "B"])), shade=[]), "elements[0]", "disjoints"),
    ("universe", lambda: refusal("sets", elements=elements(("5", []))), "elements[0]", "donne universe"),
    ("universe", lambda: refusal("sets", shade=[[]]), "shade[0]", "donne universe"),
    ("crowded", lambda: refusal("sets", elements=elements(("1 ; 2 ; 3 ; 6 ; 9 ; 18 ; 24", ["A", "B"]))), "", "la zone [A, B] ne tient pas"),
    ("crowded", lambda: refusal("sets", elements=elements(*((str(i), ["A"]) for i in range(7)))), "", "la zone [A] (plus de 6 éléments)"),
    (
        "crowded",
        lambda: refusal(
            "nested",
            elements=elements(
                ("−3 ; −2 ; −1", ["Z"]),
                ("$\\sqrt{2}$ ; $\\pi$ ; $e$", ["R"]),
                ("0,5 ; 0,25", ["D"]),
                ("$\\frac{1}{3}$ ; $\\frac{2}{7}$", ["Q"]),
            ),
        ),
        "",
        "l'emboîtement",
    ),
    (
        "crowded",
        lambda: refusal("sets", sets=[{"id": "A", "label": "A"}, {"id": "B", "label": "B"}, {"id": "C", "label": "c" * 40}], elements=[], shade=[]),
        "",
        "la ligne des noms d'ensembles",
    ),
    # Measures written the way the subject prompt teaches LaTeX: `3{,}5`, `\degree`, « = ».
    ("measure", lambda: plane({"A": [0, 0], "B": [3, 0], "C": [0, 7]}, seg("A", "B", label="$3{,}5$ cm"), seg("A", "C", label="$7$ cm")), "shapes[0] et shapes[1]", "rapport"),
    ("measure", lambda: plane(TRIANGLE, seg("A", "B", label="$|AB| = 4$ cm"), seg("B", "C", label="$|BC| = 6$ cm")), "shapes[0] et shapes[1]", "rapport"),
    ("measure", lambda: plane(TRIANGLE, seg("A", "B", label="$4\\text{ cm}$"), seg("B", "C", label="$6\\,\\text{cm}$")), "shapes[0] et shapes[1]", "rapport"),
    ("measure", lambda: plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$37{,}5^\\circ$")), "shapes[0] (angle)", "l'étiquette dit 37,5°"),
    ("measure", lambda: plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$40\\degree$")), "(angle)", "mesure 45°"),
    ("measure", lambda: plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$40\\,°$")), "(angle)", "mesure 45°"),
    ("measure", lambda: plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$\\widehat{ABC} = 40°$")), "(angle)", "mesure 45°"),
    # The window counts in the span: 0,3 apart in [−10 ; 10] is 4 px at a 400 px board.
    ("close_points", lambda: plane({"A": [0, 0], "B": [0.3, 0]}, x_range=[-10, 10]), "", "A et B sont presque au même endroit"),
    # So does the origin of a repère.
    ("close_points", lambda: plane({"A": [100, 100], "B": [100.5, 100]}, axes=True), "", "A et B"),
    ("scale", lambda: plane({"A": [0, 0], "B": [2e6, 0]}, seg("A", "B")), "", "dépasse un million"),
    ("scale", lambda: plane({"A": [0, 0]}, x_range=[-2e6, 10]), "", "dépasse un million"),
    ("scale", lambda: plane({"O": [0, 0]}, {"draw": "circle", "of": ["O"], "radius": 5e6}), "", "dépasse un million"),
    ("scale", lambda: plane({"A": [0, 0], "B": [1e-100, 0]}, seg("A", "B")), "", "moins d'un millième"),
    ("scale", lambda: plane({"A": [0, 0], "B": [5e-4, 5e-4]}, grid=True), "", "quatre décimales"),
    ("scale", lambda: refusal("number_line", intervals=[], marks=[{"x": 0}, {"x": 1e-100}]), "", "moins d'un millième"),
    ("scale", lambda: refusal("number_line", intervals=[], marks=[{"x": 1.4142}, {"x": 1.4143}]), "", "moins d'un millième"),
    ("scale", lambda: line(interval(0, 1e7, "both")), "", "dépasse un million"),
    ("blank", lambda: refusal("sets", sets=[{"id": "A", "label": " "}, {"id": "B", "label": "B"}]), "sets[0]", "le texte est vide"),
    ("blank", lambda: refusal("sets", elements=elements(("\u00a0", ["A"]))), "elements[0]", "le texte est vide"),
    ("blank", lambda: refusal("sets", universe="  "), "universe", "le texte est vide"),
]

# Coordinates and intervals written by hand, in every spelling the model's LaTeX
# may use: all refused, since the board writes them itself.
HAND_WRITTEN = [
    "$(2 ; 3)$",
    "(2 ; 3)",
    "$(-2;3)$",
    "(2,5 ; −1)",
    "$(2\\,;\\,3)$",
    "$(2{,}5 ; 1)$",
    "$(2{,}5\\;;\\;{-}1)$",
    "$\\left(2 ; 3\\right)$",
    "$\\bigl(2 ; 3\\bigr)$",
    "$A(\\frac{1}{2} ; 3)$",
    "$B(\\sqrt{2} ; -\\pi)$",
    "$[2 ; 5[$",
    "$]-\\infty ; 2]$",
    "$]{-}\\infty ; 2]$",
    "$[\\sqrt{2} ; 3]$",
    "$[\\frac{1}{2} ; 1[$",
    "$\\left[ 2 ; 5 \\right[$",
    "$\\lbrack 0 ; 1 \\rbrack$",
    "$[0{,}5 ; +\\infty[$",
    "S = ]−∞ ; 2]",
    "$[-3 ; 0]$",
    "$x \\in [2\\,;\\,5]$",
]

# What a course writes in a label or caption without coordinates or an interval.
NOT_HAND_WRITTEN = [
    "Le segment $[AB]$ et la demi-droite $[AB$",
    "Le triangle $ABC$ est rectangle en $A$ ; $[BC]$ est l'hypoténuse.",
    "Les points ]AB[ et le milieu",
    "Pour $x$ compris entre 2 et 5 ; on hachure le reste.",
    "Échelle : 1 cm pour 1 unité ; [OI] mesure 1.",
    "$[AB]$ 5 cm ; $[CD]$ 3 cm",
    "La droite $d$ ; le point $M_1$ (en rouge)",
    "Vecteurs $\\vec{AB}$ et $\\vec{CD}$ ; $[AB] \\parallel [CD]$",
    "Solution : les réels plus grands que 2 (2 ; exclu)",
    "Repère orthonormé $(O ; \\vec{i}, \\vec{j})$",
    "Le repère $(O ; I ; J)$",
    "Un point $M(x ; y)$ du plan",
    "Sur l'intervalle $[a ; b]$",
    "$\\left(AB\\right) \\perp \\left(CD\\right)$",
]


@pytest.mark.parametrize("label", HAND_WRITTEN)
def test_hand_written_notation_is_refused_whatever_its_latex(label: str) -> None:
    for found in (
        plane(TRIANGLE, seg("A", "B", label=label[:40])),
        line(interval(2, 5, "left", label[:40])),
        refusal("sets", caption=label),
    ):
        assert found is not None and found[0] == "label_notation", (label, found)


@pytest.mark.parametrize("caption", NOT_HAND_WRITTEN)
def test_a_course_caption_is_not_read_as_notation(caption: str) -> None:
    assert refusal("plane", caption=caption) is None


@pytest.mark.parametrize("rule,run,path,named", CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_each_rule_refuses_and_names_the_field(rule: str, run: Any, path: str, named: str) -> None:
    found = run()
    assert found is not None
    assert found[0] == rule, found
    assert found[1].startswith("La figure blocks[0]"), found[1]
    assert path in found[1]
    assert named in found[1], found[1]


def test_boundaries_are_accepted() -> None:
    # Within 1° of a right angle.
    assert plane({**TRIANGLE, "C": [0.05, 3]}, {"draw": "right_angle", "of": ["B", "A", "C"]}) is None
    # The same codage on 3 and 3,05: within 2 %.
    assert plane({"A": [0, 0], "B": [3, 0], "C": [0, 3.05]}, seg("A", "B", marks=1), seg("A", "C", marks=1)) is None
    # Degrees written in LaTeX, and lengths in the ratio of the drawing.
    assert plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$45^\\circ$")) is None
    assert plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$45^{\\circ}$")) is None
    assert plane(TRIANGLE, seg("A", "B", label="$4$ cm"), seg("B", "C", label="5 cm")) is None
    assert plane(TRIANGLE, seg("A", "B", label="40 mm"), seg("B", "C", label="5 cm")) is None
    assert plane(TRIANGLE, seg("A", "B", label="$4$"), seg("B", "C", label="5")) is None
    # A label that is not a measure is not read as one.
    assert plane(TRIANGLE, seg("A", "B", label="$a$"), seg("B", "C", label="6 cm")) is None
    # A point 2 % beyond a given range still fits.
    assert plane({"A": [0, 0], "B": [4, 0]}, x_range=[-1, 4.05]) is None
    assert plane({"A": [0, 0], "B": [4.1, 0]}, x_range=[-1, 4]) is None
    # Coincident points are one point with two names; only near ones are refused.
    assert plane({"A": [0, 0], "A'": [0, 0], "B": [3, 0]}, seg("A", "B")) is None
    # The whole line, and a union whose pieces meet at an excluded bound.
    assert line(interval(None, None, "neither")) is None
    assert line(interval(None, 2, "neither", "$S$"), interval(2, 5, "right", "$S$")) is None
    assert line(interval(None, 2, "right", "$S$"), interval(5, None, "left", "$S$")) is None
    # Pieces under different labels may overlap: they are different sets.
    assert line(interval(-2, 5, "both", "$A$"), interval(0, 3, "both", "$B$")) is None
    # Nested zones: Z∖N and N are two zones; 7 listed everywhere lands in N.
    assert refusal("nested", shade=[["Z"], ["N", "Z"]]) is None
    assert refusal("nested", shade=[["N", "Z", "D", "Q", "R"], ["R"]]) is None
    # A segment's name in a caption is not an interval.
    assert refusal("plane", caption="Le segment $[AB]$ et la demi-droite $[AB$") is None
    assert refusal("axes") is None
    assert refusal("plane", points={}, shapes=[], grid=True) is None
    # Five unmarked angles are told apart; a sixth, coded, is fine.
    five = [angle(a, "O", b) for a, b in zip("ABCDE", "BCDEF")]
    assert plane(_HEX, *five) is None
    assert plane(_HEX, *five, angle("F", "O", "A", marks=1)) is None


def _rotated(deg: float, r: float = 1.0, at: tuple[float, float] = (0.0, 0.0)) -> list[float]:
    t = math.radians(deg)
    return [at[0] + r * math.cos(t), at[1] + r * math.sin(t)]


# Each tolerance, from the accepting side: what the course draws must pass.
ACCEPTED: list[tuple[str, Any]] = [
    ("circle: centre and radius", lambda: plane({"O": [0, 0], "A": [3, 0]}, {"draw": "circle", "of": ["O"], "radius": 3})),
    ("circle: centre and a point", lambda: plane({"O": [0, 0], "A": [3, 0]}, {"draw": "circle", "of": ["O", "A"]})),
    ("arc_radius: 3 and 3,05 (1,7 %)", lambda: plane({"A": [3, 0], "O": [0, 0], "B": [0, 3.05]}, {"draw": "arc", "of": ["A", "O", "B"]})),
    ("degenerate: a radius just over 2 % of the span", lambda: plane({"A": [0, 0], "B": [10, 0]}, {"draw": "circle", "of": ["A"], "radius": 0.21})),
    ("degenerate: a triangle bent by 3 %", lambda: plane({"A": [0, 0], "B": [10, 0], "C": [5, 0.3]}, {"draw": "polygon", "of": ["A", "B", "C"]})),
    ("degenerate: an angle of 0,6°", lambda: plane({"A": [5, 0], "O": [0, 0], "B": _rotated(0.6, 2.5)}, angle("A", "O", "B"))),
    ("degenerate: an angle of 179,4°", lambda: plane({"A": [5, 0], "O": [0, 0], "B": _rotated(179.4, 5)}, angle("A", "O", "B"))),
    ("crossed: a concave arrowhead", lambda: plane({"A": [0, 0], "B": [4, 2], "C": [0, 4], "D": [1, 2]}, {"draw": "polygon", "of": ["A", "B", "C", "D"]})),
    (
        "crossed: a concave L hexagon",
        lambda: plane(
            {"A": [0, 0], "B": [4, 0], "C": [4, 1], "D": [1, 1], "E": [1, 4], "F": [0, 4]},
            {"draw": "polygon", "of": ["A", "B", "C", "D", "E", "F"]},
        ),
    ),
    (
        "codage: two angles 0,9° apart share one arc",
        lambda: plane(
            {"O": [0, 0], "A": [3, 0], "B": _rotated(40, 3), "P": [8, 0], "R": [11, 0], "Q": _rotated(40.9, 3, (8, 0))},
            angle("A", "O", "B", marks=1),
            angle("R", "P", "Q", marks=1),
        ),
    ),
    ("window: axes with 0 at the edge of x_range", lambda: plane({"A": [3, 1]}, axes=True, x_range=[0, 8], y_range=[0, 4])),
    ("window: axes with 0 at the top of y_range", lambda: plane({"A": [3, -1]}, axes=True, y_range=[-4, 0])),
    ("empty: a number line with marks only", lambda: refusal("number_line", intervals=[], marks=[{"x": 1.4}, {"x": 1.5}])),
    ("scale: a million, the largest number", lambda: plane({"A": [0, 0], "B": [1e6, 0], "C": [0, 1e6]}, {"draw": "polygon", "of": ["A", "B", "C"]})),
    ("scale: a thousandth, the smallest figure", lambda: plane({"A": [0, 0], "B": [1e-3, 0], "C": [0, 1e-3]}, {"draw": "polygon", "of": ["A", "B", "C"]})),
    ("scale: an encadrement au millième", lambda: refusal("number_line", intervals=[], marks=[{"x": 1.414}, {"x": 1.415}])),
    ("scale: a single point", lambda: plane({"A": [3, 3]})),
    ("close_points: 2,5 % of the window apart", lambda: plane({"A": [0, 0], "B": [0.5, 0]}, x_range=[-10, 10])),
    ("measure: a decimal comma in LaTeX, in proportion", lambda: plane({"A": [0, 0], "B": [3.5, 0], "C": [0, 7]}, seg("A", "B", label="$3{,}5$ cm"), seg("A", "C", label="$7$ cm"))),
    ("measure: a degree written \\degree, true", lambda: plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$45\\degree$"))),
    ("measure: « = » before a true amplitude", lambda: plane({"A": [1, 0], "B": [0, 0], "C": [1, 1]}, angle("A", "B", "C", label="$\\widehat{ABC} = 45^{\\circ}$"))),
    ("measure: an approximation is not checked", lambda: plane(TRIANGLE, seg("A", "B", label="$\\approx 4{,}5$ cm"), seg("B", "C", label="5 cm"))),
    ("blank: an interval's blank label is no label", lambda: line(interval(0, 1, "both", " "))),
    # Hatched, a lane hatches what none of its pieces holds (line.ts). Every piece has a
    # length (`order`), so no lane is hatched whole; and one hatched nowhere is how the
    # course draws ℝ, or ℝ privé de 2 with its brackets: true, so not refused.
    ("hatched: x ≤ 2 ou x ≥ 5, unlabelled", lambda: line(interval(None, 2, "right"), interval(5, None, "left"), convention="hatched")),
    ("hatched: S = ℝ, nothing hatched", lambda: line(interval(None, None, "neither", "$S$"), convention="hatched")),
    ("hatched: ℝ privé de 2", lambda: line(interval(None, 2, "neither", "$S$"), interval(2, None, "neither", "$S$"), convention="hatched")),
]


@pytest.mark.parametrize("why,run", ACCEPTED, ids=[a[0] for a in ACCEPTED])
def test_each_tolerance_accepts_what_the_course_draws(why: str, run: Any) -> None:
    assert run() is None, why


# A circle may overrun a given range by the same 2 % slack as a point: y_range
# [−2 ; 2] is 4 wide, so the circle may reach −2,08 and 2,08, and no further.
CIRCLE_IN_WINDOW: list[tuple[str, Any, bool]] = [
    ("radius 2,07", lambda: plane({"O": [0, 0]}, {"draw": "circle", "of": ["O"], "radius": 2.07}, y_range=[-2, 2]), True),
    ("radius 2,09", lambda: plane({"O": [0, 0]}, {"draw": "circle", "of": ["O"], "radius": 2.09}, y_range=[-2, 2]), False),
    # Through a point inside the window, the circle still overruns it on the other axis.
    ("through (2,07 ; 0)", lambda: plane({"O": [0, 0], "A": [2.07, 0]}, {"draw": "circle", "of": ["O", "A"]}, y_range=[-2, 2]), True),
    ("through (2,09 ; 0)", lambda: plane({"O": [0, 0], "A": [2.09, 0]}, {"draw": "circle", "of": ["O", "A"]}, y_range=[-2, 2]), False),
    # Off centre, on the upper edge: the centre at 1, the window's top at 3.
    ("centre (0 ; 1), up to 3,07", lambda: plane({"O": [0, 1]}, {"draw": "circle", "of": ["O"], "radius": 2.07}, y_range=[-2, 3]), True),
    ("centre (0 ; 1), up to 3,12", lambda: plane({"O": [0, 1]}, {"draw": "circle", "of": ["O"], "radius": 2.12}, y_range=[-2, 3]), False),
]


@pytest.mark.parametrize("why,run,inside", CIRCLE_IN_WINDOW, ids=[c[0] for c in CIRCLE_IN_WINDOW])
def test_a_circle_overruns_its_window_by_the_slack_at_most(why: str, run: Any, inside: bool) -> None:
    found = run()
    if inside:
        assert found is None, (why, found)
    else:
        assert found is not None and found[0] == "outside", (why, found)
        assert "shapes[0] (circle) : le cercle sort de y_range" in found[1]


def test_the_first_rule_in_order_wins() -> None:
    # Arity is read before the points: a three-point segment on an unknown point.
    found = plane(TRIANGLE, {"draw": "segment", "of": ["A", "B", "Z"]})
    assert found is not None and found[0] == "arity"
    # Shapes are checked before the codage.
    found = plane(TRIANGLE, seg("A", "B", marks=1), seg("A", "C", marks=1), seg("A", "D"))
    assert found is not None and found[0] == "unknown_point"


def _ctx() -> TurnContext:
    curriculum = Curriculum.model_validate(
        {
            "id": "cc",
            "title": "C",
            "sections": [{"id": "ss", "kind": "teach", "title": "S", "goal": "g", "beats": ["b"], "done_when": "d"}],
        }
    )
    return TurnContext.from_progress(curriculum, [], None)


def block(base: str, **changes: Any) -> FigureBlock:
    return FigureBlock.model_validate({"type": "figure", "figure": {**BASES[base], **changes}})


def explanation(*blocks: FigureBlock) -> ExplanationCard:
    return ExplanationCard.model_validate({"kind": "explanation", "title": "T", "blocks": [b.model_dump() for b in blocks]})


def exercise(drawing: FigureBlock) -> ExerciseCard:
    return ExerciseCard.model_validate({"kind": "exercise", "title": "T", "statement": "S", "drawing": drawing.model_dump()})


def test_an_exercise_figure_keeps_its_values() -> None:
    shown = block("number_line", show_values=True)
    found = figures_refusal([("drawing", shown)], exercise(shown), _ctx())
    assert found is not None and found[0] == "exercise_values"
    assert found[1].startswith("La figure drawing accompagne un exercice ouvert")
    card = explanation(shown)
    assert figures_refusal([("blocks[0]", shown)], card, _ctx()) is None
    worked = WorkedExampleCard.model_validate(
        {"kind": "worked_example", "title": "T", "statement": "S", "drawing": shown.model_dump(), "steps": [{"tex": "x"}]}
    )
    assert figures_refusal([("drawing", shown)], worked, _ctx()) is None
    plain = block("plane")
    assert figures_refusal([("drawing", plain)], exercise(plain), _ctx()) is None
    # Sets have no values to withhold.
    sets = block("sets")
    assert figures_refusal([("drawing", sets)], exercise(sets), _ctx()) is None


def test_a_card_holds_two_figures_and_the_first_refusal_wins() -> None:
    # How many drawings a card holds is display_board's rule, across families (test_registry).
    two = [block("plane"), block("number_line")]
    assert figures_refusal([(f"blocks[{i}]", b) for i, b in enumerate(two)], explanation(*two), _ctx()) is None
    bad_line = block("number_line", intervals=[interval(5, 2, "both")])
    bad_plane = block("plane", x_range=[5, 0])
    items = [("blocks[1]", bad_line), ("blocks[2]", bad_plane)]
    found = figures_refusal(items, explanation(block("sets"), bad_line, bad_plane), _ctx())
    assert found is not None and found[0] == "order" and "blocks[1]" in found[1]


def test_the_summary_holds_kinds_only() -> None:
    items = [("blocks[0]", block("plane")), ("blocks[1]", block("sets"))]
    summary = figures_summary(items)
    assert summary == {"kinds": ["plane", "sets"]}


# --- hatched unlabelled intervals are one set (lead fix after verification) -----


def test_touching_unlabelled_intervals_are_refused_under_hatching() -> None:
    found = line(interval(None, 2, "right"), interval(2, 5, "right"), convention="hatched")
    assert found is not None and found[0] == "union" and "sont hachurés sans étiquette" in found[1]


def test_apart_unlabelled_intervals_pass_under_hatching() -> None:
    assert line(interval(None, 2, "right"), interval(5, None, "left"), convention="hatched") is None


def test_touching_unlabelled_intervals_stay_separate_sets_without_hatching() -> None:
    # With brackets, two unlabelled intervals are two sets: they may meet.
    assert line(interval(None, 2, "right"), interval(2, 5, "right")) is None
