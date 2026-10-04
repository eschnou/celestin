r"""The figure rules `display_board` applies.

Structural rules live on the card model (`app/domain/figure.py`); the rules that
could change run here, so a stored card keeps replaying. Each refusal is a rule
code for the logs and a French message naming the field, handed back to the model.

Three families of rule:

- the figure must be drawable: every name refers to a point, each shape has the
  points it takes, nothing collapses to nothing, the window holds what it shows,
  its numbers stay within what the board scales and writes (`scale`), and no text
  is blank;
- the figure must not teach something false: a right-angle mark on an angle that
  is not right, a shared codage on unequal lengths or amplitudes, a measure the
  drawing contradicts, a union of intervals that is really one interval;
- the figure must fit the board: a diagram of sets is laid out in fixed zones at
  the smallest board, and `crowded` refuses what those zones cannot hold. The
  capacity numbers are a contract with the board's layout
  (`frontend/src/components/celestin/figure/venn.ts`), pinned on both sides by
  `tests/fixtures/figure/capacity.json`.

Coordinates and intervals are never written by the model: the board writes them
itself, in the course's notation, when `show_values` is set. A label that writes
them by hand is refused (`label_notation`), whichever way its LaTeX spells them
(`0{,}5`, `\,;\,`, `\left(`, `\frac`), so an exercise's figure cannot carry the
answer in that shape either.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from itertools import combinations
from typing import Any

from app.domain.board import BoardCard, ExerciseCard
from app.domain.figure import (
    Figure,
    FigureBlock,
    FigureShape,
    LineInterval,
    NumberLine,
    PlaneFigure,
    SetDiagram,
)
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.services.tools.charts import Refusal
from app.services.tools.context import TurnContext
from app.services.tools.text import JS_SPACE, MATH

Pt = tuple[float, float]

# Tolerances: what the board can draw without the eye catching it out.
_RIGHT_SLACK_DEG = 1.0
_ANGLE_SLACK_DEG = 1.0
_LENGTH_SLACK = 0.02
_WINDOW_SLACK = 0.02
# Of the figure's span: distinct points closer than this, a circle smaller than
# this, or a polygon flatter than this are unreadable (about 5 px on a 400 px board).
_MIN_GAP = 0.02
# Coincident, within float noise, relative to the span.
_SAME = 1e-9
_MIN_ANGLE_DEG = 0.5
# Unmarked angles are told apart by colour; the board has five tints for them.
_MAX_UNMARKED_ANGLES = 5
# In the figure's own units. A school figure never needs a number beyond a million;
# and the board writes four decimals at most, so a figure smaller than a thousandth
# would have graduations that all read the same. The board's scale and ticks stay
# exact inside both (sanitise.ts drops what lies beyond, for a stored card).
_MAX_MAGNITUDE = 1e6
_MIN_EXTENT = 1e-3

# How many points each shape takes, and how a message says it.
_ARITY: dict[str, tuple[int, int, str]] = {
    "segment": (2, 2, "2 points"),
    "line": (2, 2, "2 points"),
    "ray": (2, 2, "2 points (l'origine, puis un point)"),
    "vector": (2, 2, "2 points (l'origine, puis l'extrémité)"),
    "polygon": (3, 12, "de 3 à 12 sommets"),
    "circle": (1, 2, "le centre, ou le centre puis un point du cercle"),
    "arc": (3, 3, "3 points (une extrémité, le centre, l'autre extrémité)"),
    "angle": (3, 3, "3 points (A, B, C pour l'angle en B)"),
    "right_angle": (3, 3, "3 points (A, B, C pour l'angle en B)"),
}

# Both families of pattern read a label as `_bare` leaves it: no `$`, no spaces,
# the LaTeX spellings the subject prompt teaches (`0{,}45`, `\,`, `\left(`) undone.
#
# Coordinates or an interval written by hand: the board writes both itself. Each
# bound starts like a number (a sign, a digit, ∞, or `\frac`, `\sqrt`, `\pi`,
# `\infty`), so `[AB]`, `]AB)`, `(O ; \vec{i}, \vec{j})` and « (2 ; exclu) » pass.
_BOUND = r"[+−-]?(?:\d|∞|\\(?:[dt]?frac|sqrt|pi|infty)(?![A-Za-z]))"
_INTERVAL = re.compile(rf"[\[\]]{_BOUND}[^;\[\]]*;{_BOUND}[^;\[\]]*[\[\]]")
_COORDS = re.compile(rf"\({_BOUND}[^;()]*;{_BOUND}[^;()]*\)")
# An English course writes `(2, 3)`, `[2, 5)`, `(−∞, 2]` and `(2, −1.5)` (spec 011 §4.6): the
# members are split by a comma (or by the French `;`, which is no better by hand), any
# bracket opens and any closes. A frame `(O, \vec{i}, \vec{j})` still passes: its first
# member is no bound, and a third member keeps `[^,;…]*` from reaching the closing bracket.
_INTERVAL_EN = re.compile(rf"[\[\](]{_BOUND}[^,;\[\]()]*[,;]{_BOUND}[^,;\[\]()]*[\[\])]")
_COORDS_EN = re.compile(rf"\({_BOUND}[^,;()]*[,;]{_BOUND}[^,;()]*\)")
INTERVAL = by_language(fr=_INTERVAL, en=_INTERVAL_EN)
COORDS = by_language(fr=_COORDS, en=_COORDS_EN)
# A measure: the whole label, or what follows its « = » (`\widehat{B} = 40°`, `|AB| = 5 cm`).
_DEGREES = re.compile(r"^(?:[^=]*=)?(\d+(?:[.,]\d+)?)°$")
_LENGTH = re.compile(r"^(?:[^=]*=)?(\d+(?:[.,]\d+)?)(mm|cm|dm|m|km)?$")
# English: a point for the decimal, a comma only for thousands (« 1,500 m » is 1500).
_NUMBER_EN = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_DEGREES_EN = re.compile(rf"^(?:[^=]*=)?{_NUMBER_EN}°$")
_LENGTH_EN = re.compile(rf"^(?:[^=]*=)?{_NUMBER_EN}(mm|cm|dm|m|km)?$")
DEGREES = by_language(fr=_DEGREES, en=_DEGREES_EN)
LENGTH = by_language(fr=_LENGTH, en=_LENGTH_EN)
_MM = {"mm": 1.0, "cm": 10.0, "dm": 100.0, "m": 1000.0, "km": 1e6}
# LaTeX that changes how a label looks, not what it says.
_TEX_SIZING = re.compile(
    r"\\(?:left|right|[bB]igg?[lr]?|mathopen|mathclose|quad|qquad|thinspace|medspace|thickspace|enspace)"
    r"(?![A-Za-z])|\\[,;:! ]|~"
)
_TEX_TEXT = re.compile(r"\\(?:text|textrm|mathrm|mathit|mbox|operatorname)\{([^{}]*)\}")
_TEX_DEGREE = re.compile(r"\^\{?\\circ\}?|\\(?:text)?degree(?![A-Za-z])")
_TEX_DELIMITER = {r"\lbrack": "[", r"\rbrack": "]", r"\lparen": "(", r"\rparen": ")"}


def _n(value: float) -> str:
    """A number for a message: two decimals at most, no trailing `.0`."""
    return f"{round(value, 2):g}"


def _deg(value: float) -> str:
    """An amplitude for a message, in whole degrees."""
    return f"{round(value)}°"


def _bare(label: str) -> str:
    r"""A label as it reads, whichever way its LaTeX spells it: no `$`, no spaces
    or sizing (`\,`, `~`, `\left`, `\big`), `{,}` a comma and `{-}` a minus,
    `^\circ` and `\degree` a °, `\text{…}` unwrapped, `\lbrack` a bracket.
    So `$\left(2{,}5\,;\,{-}1\right)$` reads `(2,5;-1)` and `$37{,}5^\circ$` `37,5°`."""
    text = label.replace("$", "")
    for command, delimiter in _TEX_DELIMITER.items():
        text = re.sub(re.escape(command) + r"(?![A-Za-z])", delimiter, text)
    text = _TEX_DEGREE.sub("°", text)
    text = _TEX_SIZING.sub("", text)
    text = _TEX_TEXT.sub(r"\1", text)
    text = re.sub(r"\{([,.;+−\-\[\]()])\}", r"\1", text)
    return re.sub(r"[\s\ufeff]+", "", text)


def _number(text: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> float:
    """A number as the course writes it: a decimal comma in French, thousands commas in English."""
    return float(text.replace(",", "") if language == "en" else text.replace(",", "."))


def _dist(p: Pt, q: Pt) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _amplitude(a: Pt, b: Pt, c: Pt) -> float:
    """The angle ABC at B, in degrees, between 0 and 180."""
    ux, uy, vx, vy = a[0] - b[0], a[1] - b[1], c[0] - b[0], c[1] - b[1]
    cos = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _cross(o: Pt, a: Pt, b: Pt) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1: Pt, p2: Pt, q1: Pt, q2: Pt) -> bool:
    """Whether two segments properly intersect (touching ends do not count)."""
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def _point(fig: PlaneFigure, name: str) -> Pt:
    x, y = fig.points[name]
    return (x, y)


def _extent(fig: PlaneFigure) -> float:
    """The figure's larger extent as the board draws it: its points, its circles,
    the origin of a repère and the ranges given (the board's window only grows).
    0 when all of it sits at one place."""
    xs = [p[0] for p in fig.points.values()]
    ys = [p[1] for p in fig.points.values()]
    for shape in fig.shapes:
        if shape.draw != "circle" or not shape.of or shape.of[0] not in fig.points:
            continue
        centre = _point(fig, shape.of[0])
        if shape.radius is not None:
            radius = shape.radius
        elif len(shape.of) > 1 and shape.of[1] in fig.points:
            radius = _dist(centre, _point(fig, shape.of[1]))
        else:
            continue
        xs += [centre[0] - radius, centre[0] + radius]
        ys += [centre[1] - radius, centre[1] + radius]
    if fig.axes and xs:
        xs.append(0.0)
        ys.append(0.0)
    extent = max(max(xs) - min(xs), max(ys) - min(ys)) if xs else 0.0
    for window in (fig.x_range, fig.y_range):
        if window is not None:
            extent = max(extent, window[1] - window[0])
    return extent


def _span(fig: PlaneFigure) -> float:
    """The extent tolerances are relative to: 1 for a figure at one place."""
    return _extent(fig) or 1.0


def _scale(numbers: Sequence[float], extent: float, where: str) -> Refusal | None:
    """Numbers a school figure can hold, on a figure large enough to see."""
    if any(abs(v) > _MAX_MAGNITUDE for v in numbers):
        return (
            "scale",
            f"{where} : un nombre de la figure dépasse un million en valeur absolue ; change d'unité "
            "(des km plutôt que des m, par exemple).",
        )
    if 0 < extent < _MIN_EXTENT:
        return (
            "scale",
            f"{where} : la figure mesure moins d'un millième d'unité ; le tableau écrit quatre décimales au plus "
            "et ses graduations se confondraient. Change d'unité.",
        )
    return None


def _in_order(first: tuple[int, str], second: tuple[int, str]) -> tuple[tuple[int, str], tuple[int, str]]:
    """Two named shapes, lower index first."""
    return (first, second) if first[0] <= second[0] else (second, first)


def _notation(
    labels: Sequence[str | None], where: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    for label in labels:
        if label and (INTERVAL[language].search(text := _bare(label)) or COORDS[language].search(text)):
            return (
                "label_notation",
                f"{where} : « {label} » écrit des coordonnées ou un intervalle à la main ; le tableau les "
                "écrit lui-même dans la notation du cours avec show_values (hors exercice). "
                "Retire-les de l'étiquette.",
            )
    return None


# ----------------------------------------------------------------- plane


def _window(fig: PlaneFigure, where: str) -> Refusal | None:
    for name, window in (("x_range", fig.x_range), ("y_range", fig.y_range)):
        if window is None:
            continue
        lo, hi = window
        if lo >= hi:
            return ("window", f"{where} : {name} va du plus petit au plus grand ({_n(lo)} puis {_n(hi)}).")
        if fig.axes and not lo <= 0 <= hi:
            return (
                "window",
                f"{where} : avec axes, {name} contient 0, l'origine du repère ({_n(lo)} à {_n(hi)}).",
            )
    return None


def _close_points(fig: PlaneFigure, where: str) -> Refusal | None:
    span = _span(fig)
    for (na, a), (nb, b) in combinations(fig.points.items(), 2):
        if _SAME * span < _dist((a[0], a[1]), (b[0], b[1])) < _MIN_GAP * span:
            return (
                "close_points",
                f"{where} : {na} et {nb} sont presque au même endroit et se confondraient au tableau ; "
                "donne-leur les mêmes coordonnées ou écarte-les.",
            )
    return None


def _shape_refusal(fig: PlaneFigure, i: int, shape: FigureShape, span: float, where: str) -> Refusal | None:
    at = f"{where}, shapes[{i}] ({shape.draw})"
    lo, hi, wording = _ARITY[shape.draw]
    if not lo <= len(shape.of) <= hi:
        return ("arity", f"{at} : of attend {wording}, il y en a {len(shape.of)}.")
    for name in shape.of:
        if shape.of.count(name) > 1:
            return ("repeated", f"{at} : « {name} » apparaît deux fois dans of.")
    for name in shape.of:
        if name not in fig.points:
            return ("unknown_point", f"{at} : le point « {name} » n'est pas dans points.")
    if shape.radius is not None and shape.draw != "circle":
        return ("field", f"{at} : radius ne sert qu'à un cercle.")
    if shape.marks and shape.draw not in ("segment", "angle"):
        return ("field", f"{at} : marks (le codage) ne sert qu'à un segment ou un angle.")
    if shape.draw == "circle" and (len(shape.of) == 1) == (shape.radius is None):
        return (
            "circle",
            f"{at} : un cercle se donne par son centre et radius, ou par son centre et un point du cercle ; "
            "pas les deux, ni aucun.",
        )
    pts = [_point(fig, name) for name in shape.of]
    for (na, a), (nb, b) in combinations(zip(shape.of, pts), 2):
        if _dist(a, b) <= _SAME * span:
            return ("degenerate", f"{at} : {na} et {nb} sont au même endroit, le tracé est vide.")
    if shape.draw == "circle" and shape.radius is not None and shape.radius < _MIN_GAP * span:
        return ("degenerate", f"{at} : le cercle est trop petit pour se voir.")
    if shape.draw == "polygon":
        far = max(combinations(pts, 2), key=lambda pq: _dist(*pq))
        if all(abs(_cross(far[0], far[1], p)) / _dist(*far) <= _MIN_GAP * span for p in pts):
            return ("degenerate", f"{at} : les sommets sont alignés, le polygone est plat.")
        n = len(pts)
        for j, k in combinations(range(n), 2):
            if k - j in (1, n - 1):
                continue
            if _segments_cross(pts[j], pts[(j + 1) % n], pts[k], pts[(k + 1) % n]):
                return ("crossed", f"{at} : des côtés se croisent ; donne les sommets dans l'ordre du tour.")
    if shape.draw in ("angle", "right_angle"):
        amplitude = _amplitude(pts[0], pts[1], pts[2])
        if amplitude < _MIN_ANGLE_DEG or amplitude > 180 - _MIN_ANGLE_DEG:
            return ("degenerate", f"{at} : l'angle en {shape.of[1]} est nul ou plat, il n'y a rien à marquer.")
        if shape.draw == "right_angle" and abs(amplitude - 90) > _RIGHT_SLACK_DEG:
            return (
                "not_right",
                f"{at} : l'angle en {shape.of[1]} mesure {_deg(amplitude)} ; le codage d'angle droit serait "
                "faux. Corrige les coordonnées ou retire ce codage.",
            )
    if shape.draw == "arc":
        ra, rb = _dist(pts[0], pts[1]), _dist(pts[2], pts[1])
        if abs(ra - rb) > _LENGTH_SLACK * max(ra, rb):
            return (
                "arc_radius",
                f"{at} : {shape.of[0]} et {shape.of[2]} doivent être à la même distance du centre "
                f"{shape.of[1]} ({_n(ra)} et {_n(rb)}).",
            )
    return None


def _length(fig: PlaneFigure, shape: FigureShape) -> float:
    return _dist(_point(fig, shape.of[0]), _point(fig, shape.of[1]))


def _angle_of(fig: PlaneFigure, shape: FigureShape) -> float:
    a, b, c = (_point(fig, name) for name in shape.of)
    return _amplitude(a, b, c)


def _codage(fig: PlaneFigure, where: str) -> Refusal | None:
    """The same ticks say the same length, the same arcs the same amplitude."""
    for marks in (1, 2, 3):
        lengths = [
            (i, _length(fig, s)) for i, s in enumerate(fig.shapes) if s.draw == "segment" and s.marks == marks
        ]
        if len(lengths) > 1:
            short, long = min(lengths, key=lambda t: t[1]), max(lengths, key=lambda t: t[1])
            if long[1] - short[1] > _LENGTH_SLACK * long[1]:
                first, second = _in_order((short[0], _n(short[1])), (long[0], _n(long[1])))
                return (
                    "codage",
                    f"{where} : shapes[{first[0]}] et shapes[{second[0]}] portent le même codage mais "
                    f"mesurent {first[1]} et {second[1]} ; un même codage dit « de même longueur ».",
                )
        amplitudes = [
            (i, _angle_of(fig, s)) for i, s in enumerate(fig.shapes) if s.draw == "angle" and s.marks == marks
        ]
        if len(amplitudes) > 1:
            small, big = min(amplitudes, key=lambda t: t[1]), max(amplitudes, key=lambda t: t[1])
            if big[1] - small[1] > _ANGLE_SLACK_DEG:
                first, second = _in_order((small[0], _deg(small[1])), (big[0], _deg(big[1])))
                return (
                    "codage",
                    f"{where} : shapes[{first[0]}] et shapes[{second[0]}] portent le même codage mais "
                    f"mesurent {first[1]} et {second[1]} ; un même codage dit « de même amplitude ».",
                )
    unmarked = sum(1 for s in fig.shapes if s.draw == "angle" and s.marks == 0)
    if unmarked > _MAX_UNMARKED_ANGLES:
        return (
            "codage",
            f"{where} : {unmarked} angles sans codage ; le tableau en distingue {_MAX_UNMARKED_ANGLES} au "
            "plus. Code les angles égaux avec marks, ou répartis la figure.",
        )
    return None


def _measures(
    fig: PlaneFigure, where: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    """A measure written on the figure agrees with what the board draws to scale."""
    by_unit: dict[str, list[tuple[int, float]]] = {}
    for i, shape in enumerate(fig.shapes):
        if not shape.label:
            continue
        text = _bare(shape.label)
        if shape.draw in ("angle", "right_angle") and (found := DEGREES[language].match(text)):
            amplitude = _angle_of(fig, shape)
            if abs(_number(found.group(1), language) - amplitude) > _ANGLE_SLACK_DEG:
                return (
                    "measure",
                    f"{where}, shapes[{i}] ({shape.draw}) : l'étiquette dit {found.group(1)}° mais l'angle en "
                    f"{shape.of[1]} mesure {_deg(amplitude)} au tableau ; corrige les coordonnées ou l'étiquette.",
                )
        if shape.draw == "segment" and (found := LENGTH[language].match(text)):
            unit = found.group(2)
            value = _number(found.group(1), language) * (_MM[unit] if unit else 1.0)
            by_unit.setdefault("mm" if unit else "", []).append((i, value / _length(fig, shape)))
    for ratios in by_unit.values():
        if len(ratios) < 2:
            continue
        lo, hi = min(ratios, key=lambda t: t[1]), max(ratios, key=lambda t: t[1])
        if hi[1] - lo[1] > _LENGTH_SLACK * hi[1]:
            first, second = sorted((lo[0], hi[0]))
            return (
                "measure",
                f"{where} : les longueurs écrites sur shapes[{first}] et shapes[{second}] ne sont pas dans le "
                "rapport des longueurs tracées ; le tableau trace à l'échelle, corrige les coordonnées ou les "
                "étiquettes.",
            )
    return None


def _outside(fig: PlaneFigure, where: str) -> Refusal | None:
    for axis, name, window in ((0, "x_range", fig.x_range), (1, "y_range", fig.y_range)):
        if window is None:
            continue
        lo, hi = window
        slack = _WINDOW_SLACK * (hi - lo)
        for point, (x, y) in fig.points.items():
            if not lo - slack <= (x, y)[axis] <= hi + slack:
                return (
                    "outside",
                    f"{where} : le point {point} ({_n(x)} ; {_n(y)}) sort de {name} ({_n(lo)} à {_n(hi)}) ; "
                    "agrandis la fenêtre ou ne la donne pas.",
                )
        for i, shape in enumerate(fig.shapes):
            if shape.draw != "circle":
                continue
            centre = _point(fig, shape.of[0])
            radius = shape.radius if shape.radius is not None else _dist(centre, _point(fig, shape.of[1]))
            if centre[axis] - radius < lo - slack or centre[axis] + radius > hi + slack:
                return (
                    "outside",
                    f"{where}, shapes[{i}] (circle) : le cercle sort de {name} ; agrandis la fenêtre ou ne la "
                    "donne pas.",
                )
    return None


def _plane(
    fig: PlaneFigure, where: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    if not fig.points and not (fig.axes or fig.grid):
        return ("empty", f"{where} : la figure est vide ; donne des points, ou axes ou grid pour un repère.")
    numbers = [v for p in fig.points.values() for v in p]
    numbers += [v for w in (fig.x_range, fig.y_range) if w is not None for v in w]
    numbers += [s.radius for s in fig.shapes if s.radius is not None]
    if refusal := _window(fig, where) or _scale(numbers, _extent(fig), where) or _close_points(fig, where):
        return refusal
    span = _span(fig)
    for i, shape in enumerate(fig.shapes):
        if refusal := _shape_refusal(fig, i, shape, span, where):
            return refusal
    return (
        _codage(fig, where)
        or _measures(fig, where, language)
        or _outside(fig, where)
        or _notation([s.label for s in fig.shapes] + [fig.caption], where, language)
    )


# ------------------------------------------------------------ number line


def _meet(a: LineInterval, b: LineInterval) -> bool:
    """Whether two pieces of one set, `a` starting first, overlap or touch at a
    bound either includes: ]−∞ ; 2[ ∪ ]2 ; 5] is a union, ]−∞ ; 2] ∪ ]2 ; 5] is not."""
    a_end = math.inf if a.end is None else a.end
    b_start = -math.inf if b.start is None else b.start
    if a_end > b_start:
        return True
    return a_end == b_start and (a.closed in ("both", "right") or b.closed in ("both", "left"))


def _number_line(
    fig: NumberLine, where: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    if not fig.intervals and not fig.marks:
        return ("empty", f"{where} : la droite graduée est vide ; donne des intervals ou des marks.")
    numbers = [v for i in fig.intervals for v in (i.start, i.end) if v is not None] + [m.x for m in fig.marks]
    if refusal := _scale(numbers, max(numbers) - min(numbers) if numbers else 0.0, where):
        return refusal
    for i, interval in enumerate(fig.intervals):
        at = f"{where}, intervals[{i}]"
        start, end = interval.start, interval.end
        if start is not None and end is not None:
            if start == end:
                return ("order", f"{at} : [{_n(start)} ; {_n(end)}] est un seul nombre ; place-le dans marks.")
            if start > end:
                return ("order", f"{at} : start ({_n(start)}) doit être plus petit que end ({_n(end)}).")
        if start is None and interval.closed in ("both", "left"):
            return ("infinite_bound", f"{at} : −∞ n'est jamais compris ; closed vaut « right » ou « neither ».")
        if end is None and interval.closed in ("both", "right"):
            return ("infinite_bound", f"{at} : +∞ n'est jamais compris ; closed vaut « left » ou « neither ».")
    # Intervals sharing a label are one set, written as one union. Under hatching the
    # unlabelled intervals are one set too (the board draws them as one solution), so
    # they must not meet either.
    by_label: dict[str, list[tuple[int, LineInterval]]] = {}
    for i, interval in enumerate(fig.intervals):
        if interval.label and interval.label.strip():
            by_label.setdefault(interval.label.strip(), []).append((i, interval))
        elif fig.convention == "hatched":
            by_label.setdefault("", []).append((i, interval))
    for label, pieces in by_label.items():
        pieces.sort(key=lambda t: -math.inf if t[1].start is None else t[1].start)
        for (i, a), (j, b) in zip(pieces, pieces[1:]):
            if _meet(a, b):
                first, second = sorted((i, j))
                named = f"portent l'étiquette « {label} »" if label else "sont hachurés sans étiquette"
                return (
                    "union",
                    f"{where} : intervals[{first}] et intervals[{second}] {named} et se touchent ou se "
                    "chevauchent ; ils forment un seul intervalle, donne-le d'un seul tenant.",
                )
    xs = [mark.x for mark in fig.marks]
    for x in xs:
        if xs.count(x) > 1:
            return ("repeated", f"{where}, marks : {_n(x)} apparaît deux fois.")
    return _notation(
        [interval.label for interval in fig.intervals] + [mark.label for mark in fig.marks] + [fig.caption],
        where,
        language,
    )


# ------------------------------------------------------------------- sets

# What a diagram of sets holds at the smallest board: a 400 px board draws at
# 294 px, and the layout (venn.ts) is built at that width, then only grows. The
# same numbers are in tests/fixtures/figure/capacity.json, which both sides read.
BOARD_PX = 294
MARGIN_PX = 14
ROW_PX = 18
GAP_PX = 6
# A generous width for 12 px text: a prose character, a glyph of maths.
CHAR_PX = 7
GLYPH_PX = 9
MAX_PER_ZONE = 6
NESTED = {"label_row": 20, "gap": 6, "band_min": 20, "band_pad": 12, "inner_min": 40, "label_pad": 16}
# Each zone's slot, by layout and set count: its width in px and its rows. A
# zone is the sorted indices of the sets it lies in; () is outside them all.
SLOTS: dict[str, dict[tuple[int, ...], tuple[int, int]]] = {
    "overlap2": {(0,): (70, 4), (1,): (70, 4), (0, 1): (70, 4)},
    "overlap3": {
        (0,): (77, 2),
        (1,): (77, 2),
        (2,): (141, 2),
        (0, 1): (53, 2),
        (0, 2): (46, 2),
        (1, 2): (46, 2),
        (0, 1, 2): (70, 2),
    },
    "separate2": {(0,): (84, 5), (1,): (84, 5)},
    "separate3": {(0,): (54, 3), (1,): (54, 3), (2,): (54, 3)},
    "outside": {(): (260, 2)},
}

# Maths is found as the board's RichText and labels.ts find it (`text.MATH`), with
# JavaScript's whitespace: a label's width must be the same number on both sides.
_TEX_COMMAND = re.compile(r"\\[A-Za-z]+")
_TEX_SILENT = re.compile(r"[{}^_\\" + JS_SPACE + "]")


def text_px(text: str) -> int:
    """A generous width for 12 px text on the board: 7 px a prose character, 9 px
    a glyph of maths, where a `\\command` is one glyph and braces, `^`, `_` and
    spaces are none. « Diviseurs de 12 » is 105, `$\\frac{1}{3}$` is 27."""
    width, last = 0, 0
    for part in MATH.finditer(text):
        width += CHAR_PX * len(text[last : part.start()])
        tex = _TEX_COMMAND.sub("#", part.group().strip("$"))
        width += GLYPH_PX * len(_TEX_SILENT.sub("", tex))
        last = part.end()
    return width + CHAR_PX * len(text[last:])


def flow_rows(widths: Sequence[int], slot: int) -> int | None:
    """The rows a greedy left-to-right flow of `widths` takes in `slot` px, as the
    board's flex-wrap packs them, or None when one is wider than the slot."""
    rows, used = 0, slot + 1
    for width in widths:
        if width > slot:
            return None
        if used + GAP_PX + width > slot:
            rows, used = rows + 1, width
        else:
            used += GAP_PX + width
    return rows


def _zone(fig: SetDiagram, within: Sequence[str]) -> tuple[int, ...]:
    """Where a `within` lands: the sorted set indices, or, nested, the ring of the
    deepest listed set (the sets containing it count without being listed)."""
    ids = [s.id for s in fig.sets]
    indices = sorted({ids.index(sid) for sid in within if sid in ids})
    if fig.layout == "nested":
        return (indices[-1],) if indices else ()
    return tuple(indices)


def _zone_name(fig: SetDiagram, zone: tuple[int, ...]) -> str:
    return "[" + ", ".join(fig.sets[i].id for i in zone) + "]"


def _crowded(where: str, what: str) -> Refusal:
    return (
        "crowded",
        f"{where} : {what} ne tient pas au tableau ; raccourcis les textes, un élément par entrée, "
        "ou mets le détail dans caption.",
    )


def _fits(fig: SetDiagram, where: str) -> Refusal | None:
    """The layout's capacity at the smallest board, zone by zone."""
    n = len(fig.sets)
    width = BOARD_PX - 2 * MARGIN_PX
    by_zone: dict[tuple[int, ...], list[int]] = {}
    for element in fig.elements:
        by_zone.setdefault(_zone(fig, element.within), []).append(text_px(element.text))
    for zone, widths in by_zone.items():
        if len(widths) > MAX_PER_ZONE:
            return _crowded(where, f"la zone {_zone_name(fig, zone)} (plus de {MAX_PER_ZONE} éléments)")
    if fig.universe and text_px(fig.universe) > width:
        return _crowded(where, "universe")
    if () in by_zone:
        slot, rows = SLOTS["outside"][()]
        if (used := flow_rows(by_zone[()], slot)) is None or used > rows:
            return _crowded(where, "la zone hors des ensembles")
    labels = [text_px(s.label) for s in fig.sets]
    if fig.layout == "nested":
        # Each ring's elements stand in a column on its right, one per row.
        bands = [
            max(NESTED["band_min"], max(by_zone.get((i,), [0])) + NESTED["band_pad"]) for i in range(n - 1)
        ]
        inner = max(
            labels[-1] + NESTED["label_pad"],
            max(by_zone.get((n - 1,), [0])) + NESTED["band_pad"],
            NESTED["inner_min"],
        )
        if sum(bands) + (n - 1) * NESTED["gap"] + inner > width:
            return _crowded(where, "l'emboîtement (des éléments trop longs dans les anneaux)")
        for i in range(n):
            if labels[i] + NESTED["label_pad"] > width - sum(bands[:i]) - i * NESTED["gap"]:
                return _crowded(where, f"l'étiquette de « {fig.sets[i].id} »")
        return None
    # The labels stand in a row above the diagram; a third overlapping set's goes below it.
    top = labels[:2] if n == 3 and fig.layout == "overlap" else labels
    if sum(top) + 2 * GAP_PX * (len(top) - 1) > width or max(labels) > width:
        return _crowded(where, "la ligne des noms d'ensembles")
    slots = SLOTS[f"{fig.layout}{n}"]
    for zone, widths in by_zone.items():
        if zone == ():
            continue
        slot, rows = slots[zone]
        if (used := flow_rows(widths, slot)) is None or used > rows:
            return _crowded(where, f"la zone {_zone_name(fig, zone)}")
    return None


def _blank(fig: SetDiagram, where: str) -> Refusal | None:
    """A set's name, an element or the universe that would show nothing."""
    texts = [(f"sets[{i}]", s.label) for i, s in enumerate(fig.sets)]
    texts += [(f"elements[{i}]", e.text) for i, e in enumerate(fig.elements)]
    texts += [("universe", fig.universe)] if fig.universe is not None else []
    for at, text in texts:
        if not text.strip():
            return ("blank", f"{where}, {at} : le texte est vide ; écris ce que le tableau doit montrer.")
    return None


def _sets(fig: SetDiagram, where: str) -> Refusal | None:
    ids = [s.id for s in fig.sets]
    for sid in ids:
        if ids.count(sid) > 1:
            return ("repeated", f"{where}, sets : l'ensemble « {sid} » apparaît deux fois.")
    if refusal := _blank(fig, where):
        return refusal
    n = len(fig.sets)
    if fig.layout != "nested" and n not in (2, 3):
        return (
            "set_count",
            f"{where} : layout « {fig.layout} » dessine 2 ou 3 ensembles, il y en a {n} ; des ensembles "
            "inclus l'un dans l'autre sont « nested ».",
        )
    zones = [(f"elements[{i}]", e.within) for i, e in enumerate(fig.elements)] + [
        (f"shade[{k}]", zone) for k, zone in enumerate(fig.shade)
    ]
    for at, zone in zones:
        for sid in zone:
            if sid not in ids:
                return ("unknown_set", f"{where}, {at} : l'ensemble « {sid} » n'est pas dans sets.")
            if zone.count(sid) > 1:
                return ("repeated", f"{where}, {at} : « {sid} » apparaît deux fois.")
        if fig.layout == "separate" and len(zone) > 1:
            return (
                "region",
                f"{where}, {at} : en layout « separate », les ensembles sont disjoints ; une zone est dans un seul.",
            )
        if not zone and fig.universe is None:
            return (
                "universe",
                f"{where}, {at} : [] est hors de tous les ensembles ; donne universe, le cadre qui les contient.",
            )
    shaded = [_zone(fig, zone) for zone in fig.shade]
    for k, zone in enumerate(shaded):
        if shaded.index(zone) != k:
            return ("repeated", f"{where}, shade[{k}] : cette zone est déjà hachurée.")
    return _fits(fig, where)


# ----------------------------------------------------------------- entry


def figure_refusal(
    figure: Figure, path: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    """The first rule the figure breaks, as (rule, message), or None."""
    where = f"La figure {path}"
    match figure:
        case PlaneFigure():
            return _plane(figure, where, language)
        case NumberLine():
            return _number_line(figure, where, language)
        case SetDiagram():
            return _sets(figure, where) or _notation([figure.caption], where, language)
    return None


def figures_refusal(items: Sequence[tuple[str, FigureBlock]], card: BoardCard, ctx: TurnContext) -> Refusal | None:
    """The first rule the card's figures break, as (rule, message), or None.

    An exercise's figure is on the board while the exercise is open, so it may not
    write coordinates or intervals: they are what a reading exercise asks for.
    The one place the tool can tell; elsewhere the prompt carries the rule. How
    many drawings a card holds is `display_board`'s rule, across every family."""
    if isinstance(card, ExerciseCard):
        for path, block in items:
            if getattr(block.figure, "show_values", False):
                return (
                    "exercise_values",
                    f"La figure {path} accompagne un exercice ouvert : show_values reste à false, sinon le "
                    "tableau écrit la réponse (coordonnées, intervalles). Elles viendront avec la correction.",
                )
    for path, block in items:
        if refusal := figure_refusal(block.figure, path, ctx.language):
            return refusal
    return None


def figures_summary(items: Sequence[tuple[str, FigureBlock]]) -> dict[str, Any]:
    """What `figure_displayed` logs besides the ids: the kinds, never content."""
    return {"kinds": [block.figure.kind for _, block in items]}
