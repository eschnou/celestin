"""The plot rules `display_board` applies (specs/009-board-drawings/plot.md §3).

Structural rules live on the card model (`app/domain/plot.py`); the rules that
could change (a limit, the sampling, the pack words) run here, so a stored card
keeps replaying. Each refusal is a rule code for the logs and a French message
naming the field, handed back to the model to fix. Expressions are parsed with
`app/domain/expression.py`, the grammar the board draws with.

The pack rule (`pack_function`) reads expressions only: the functions a curve or
a sequence calls, the number e, a power of the variable. A function the pack
never names can still be drawn from values computed elsewhere, as points or as
a broken line through them; nothing here can tell those from measurements, so
this is not checked mechanically. Only the prompt's general rule (draw only what
the course uses) covers it, and the plot probe measures it (`_traced` in
`scripts/probe.py`).

How many drawings a card holds is `display_board`'s rule, across every family
(`MAX_DRAWINGS_PER_CARD` in `board.py`): it runs before this module is called.
"""

from __future__ import annotations

import functools
import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from app.domain.board import BoardCard, ExerciseCard
from app.domain.expression import (
    CURVE_VARIABLES,
    SEQUENCE_VARIABLES,
    ExprError,
    Node,
    evaluate,
    functions,
    parse,
)
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.plot import PlotBlock, PlotCurve, PlotLine, PlotPoint, PlotSequence
from app.services.tools.charts import Refusal
from app.services.tools.context import TurnContext

MAX_TERMS = 40
# Graduations: at most this many steps across a window, each with at most 4 decimals
# (the board writes ticks with formatNumber, which keeps 4).
MAX_INTERVALS = 30
STEP_DECIMALS = 4
# A window the board can graduate: no bound beyond a million, no span under a thousandth.
MAX_BOUND = 1e6
MIN_SPAN = 1e-3
# An orthonormal plot keeps the window's proportions, so y_range / x_range must stay
# drawable on a 400 px board: under 2 (not a strip), over 0.4 (not a ribbon).
MAX_ASPECT = 2.0
MIN_ASPECT = 0.4
# Samples over a curve's visible domain, to tell that it is defined and in the window.
SAMPLES = 400
# Halvings that look for the window between two samples on either side of it.
BISECTIONS = 40
# Where a hollow dot finds its value when the bound is excluded: this share of the
# domain inside it. The board uses the same (plot/sample.ts, endpointValue).
INSIDE = 1e-9
# Float slack on a count of steps: (−4.6 − −4.9) / 0.01 is 30.000000000000007.
_SLACK = 1e-9

# A function the pack never names is outside the course. sqrt and abs appear in
# every maths course under many spellings, so only these are looked up. Each entry
# matches the course naming the *function*, not an everyday word that shares its
# root (case-insensitive, except the letter e):
# - exp: `\exp`, `exp(`, « fonction exponentielle », « exponentielle de base … »,
#   the noun (« l'exponentielle », « une exponentielle »), and e raised to a power
#   however LaTeX spells it (`e^x`, `\mathrm{e}^{x}`, `{e}^{-t}`). Not the adjective
#   (« une croissance exponentielle »), not an electron or a positron (`e^-`,
#   `\mathrm{e}^{+}`), not a capital E (`E^{\circ}`).
# - ln: `\ln`, `ln(`, « logarithme népérien / naturel / de base e ». Not a bare
#   « logarithme » (the decimal one is log), not « échelle logarithmique ».
# - log: `\log` (with `\log_{10}` and `\log_a`: base 10 is one of a course's bases),
#   `log(`, « logarithme décimal / de base 10 ». Not « logarithmique ».
# - cbrt: « racine cubique / troisième », `\sqrt[3]`, ∛: nothing else says them.
# - sin, cos: `\sin`, `\cos`, « sinus », « cosinus ». The sine of an angle IS the
#   function sin (FWB trigonometry teaches one, then the other), so « le sinus d'un
#   angle » names it; « sinusoïdal » too, a sinusoid being its graph. A word
#   boundary keeps « cosinus » from naming sin, and `\sinh`, `\arcsin` name neither.
# - tan: `\tan`, `tg` (the Belgian notation, `\operatorname{tg}`), « fonction
#   tangente », the tangent of an angle (« tangente d'un angle », « tangente de
#   l'angle », « tangente de $\alpha$ / $\hat{A}$ »), « sinus, cosinus et tangente ».
#   Not the tangent line (« l'équation de la tangente en A », « tangente à la courbe »,
#   « tangente de la courbe »), which a derivatives or geometry course names often.
PACK_WORDS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "exp": (
            r"\\exp(?![A-Za-z])|\bexp\s*\(|\bfonctions?\s+(?:exp\b|exponentielles?\b)"
            r"|\bexponentielles?\s+(?:de|en)\s+base\b"
            r"|\b(?:l['’]\s*|une\s+|les\s+|des\s+)exponentielles?\b"
            # e^…, e}^… ; not when the sign after ^ stands alone (e^-, e^{+}).
            r"|(?-i:\be\}?\s*\^)(?!\s*\{?\s*[-+−](?!\s*[\w\\({]))"
        ),
        "ln": (
            r"\bln\b|\blogarithmes?\s+(?:népériens?|naturels?)\b"
            r"|\blogarithmes?\s+(?:de|en)\s+base\s+\$?\s*(?:\\mathrm\{e\}|\{e\}|e)(?!\w)"
        ),
        "log": (
            r"\blog(?![A-Za-z])|\blogarithmes?\s+décima(?:l|ux)\b"
            r"|\blogarithmes?\s+(?:de|en)\s+base\s+\$?\s*10\b"
        ),
        "cbrt": r"\bracines?\s+(?:cubiques?|troisièmes?)\b|\\sqrt\s*\[\s*3\s*\]|∛",
        "sin": r"\bsin\b|\bsinus",
        "cos": r"\bcos\b|\bcosinus",
        "tan": (
            r"\btan\b|\btg\b|\bfonctions?\s+tangentes?\b"
            r"|\btangentes?\s+(?:d['’]\s*un\s+angle|de\s+l['’]\s*angle"
            r"|de\s+\$?\s*(?:\\(?:alpha|beta|gamma|theta|varphi|phi|hat|widehat)(?![A-Za-z])|[αβγθφ]))"
            r"|\b(?:sinus|cosinus)\s*(?:,|et|ou)\s*(?:la\s+|de\s+la\s+)?tangente\b"
        ),
    }.items()
}
# The same, for an English course (spec 011 §4.6): the pack must name the function in
# English. Same shape, same exclusions: the adjective is not the function (« exponential
# growth »), the tangent line is not the tangent function (« tangent to the curve »),
# and an electron (`e^-`) or a capital E is not the number e.
_PACK_WORDS_EN: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "exp": (
            r"\\exp(?![A-Za-z])|\bexp\s*\(|\bexponential\s+functions?\b"
            r"|\bexponentials?\s+(?:with|to|in)\s+base\b"
            r"|\b(?:the|an?)\s+exponential\b(?!\s+(?:growth|decay|model|curve|rate|notation|form|behaviou?r|expression))"
            r"|(?-i:\be\}?\s*\^)(?!\s*\{?\s*[-+−](?!\s*[\w\\({]))"
        ),
        "ln": (
            r"\bln\b|\bnatural\s+log(?:arithm)?s?\b|\bn[ae]pierian\s+log(?:arithm)?s?\b"
            r"|\blog(?:arithm)?s?\s+(?:to|in|with)\s+base\s+\$?\s*(?:\\mathrm\{e\}|\{e\}|e)(?!\w)"
        ),
        "log": (
            r"\blog(?![A-Za-z])|\b(?:common|decimal)\s+log(?:arithm)?s?\b"
            r"|\blog(?:arithm)?s?\s+(?:to|in|with)\s+base\s+\$?\s*10\b"
        ),
        "cbrt": r"\b(?:cube|third)\s+roots?\b|\\sqrt\s*\[\s*3\s*\]|∛",
        "sin": r"\bsin\b|\bsine\b|\bsinusoid",
        "cos": r"\bcos\b|\bcosine\b",
        "tan": (
            r"\btan\b|\btangent\s+(?:functions?|ratio)\b"
            r"|\btangent\s+of\s+(?:(?:(?:an?|the)\s+(?:[a-z-]+\s+)?)?angle|\$?\s*(?:\\(?:alpha|beta|gamma|theta|varphi|phi|hat|widehat)(?![A-Za-z])|[αβγθφ]))"
            r"|\b(?:sine|cosine)\s*(?:,|and|or)\s*(?:the\s+)?tangent\b"
        ),
    }.items()
}
# The same, for a Dutch course (spec 017 §4.6). *Tangens* is always the function: the line is the *raaklijn*,
# so no exclusion is needed. « exponentiële groei » is a phenomenon, not the function.
_PACK_WORDS_NL: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "exp": (
            r"\\exp(?![A-Za-z])|\bexp\s*\(|\bexponenti[eë]le\s+functies?\b"
            r"|\bexponenti[eë]le\s+met\s+grondtal\b"
            r"|\b(?:de|een)\s+exponenti[eë]le\b(?!\s+(?:groei|afname|model|kromme|vorm|notatie|schrijfwijze|uitdrukking))"
            r"|(?-i:\be\}?\s*\^)(?!\s*\{?\s*[-+−](?!\s*[\w\\({]))"
        ),
        "ln": (
            r"\bln\b|\bnatuurlijke\s+logaritmes?\b|\bneperiaanse\s+logaritmes?\b"
            r"|\blogaritmes?\s+met\s+grondtal\s+\$?\s*(?:\\mathrm\{e\}|\{e\}|e)(?!\w)"
        ),
        "log": (
            r"\blog(?![A-Za-z])|\b(?:tientallige|decimale|briggse)\s+logaritmes?\b|\b10-logaritmes?\b"
            r"|\blogaritmes?\s+met\s+grondtal\s+\$?\s*10\b"
        ),
        "cbrt": r"\b(?:derdemachts|kubieke)\s*wortels?\b|\\sqrt\s*\[\s*3\s*\]|∛",
        "sin": r"\bsin\b|\bsinus",
        "cos": r"\bcos\b|\bcosinus",
        "tan": r"\btan\b|\btg\b|\btangens\b",
    }.items()
}
PACK_WORDS_BY_LANGUAGE = by_language(fr=PACK_WORDS, en=_PACK_WORDS_EN, nl=_PACK_WORDS_NL)

# What gives an exercise's answer away in a label, a title or a caption, once LaTeX
# spacing, `\left`, `\right` and braces are gone (`gives_away`). First a relation: an
# equation, an approximation, an inequality (the slanted ⩽ ⩾ FWB courses print, and
# the ≦ ≧ some fonts give) or a mapping, as a sign or a command.
_RELATION = re.compile(
    r"[=≈≃≠<>≤≥⩽⩾≦≧↦→⟶⟼]"
    r"|\\(?:approx(?:eq)?|simeq|neq?|leq?|geq?|leqslant|geqslant|leqq|geqq|lt|gt"
    r"|mapsto|longmapsto|to|rightarrow|longrightarrow)(?![A-Za-z])"
)
# Then values grouped in parentheses (coordinates) or brackets (an interval, either
# way round): the content of every group, innermost, found at each opening.
_GROUPS = re.compile(r"(?=\(([^()]*)\))|(?=[\[\]]([^\[\]]*)[\[\]])")
# English writes half-open intervals with one of each: `(2, 3]`, `[2, 5)`.
_GROUPS_EN = re.compile(_GROUPS.pattern + r"|(?=[\[(]([^\[\]()]*)[\])])")
# Dutch (Flemish): the board's outward brackets, and the mixed ones a teacher writes by hand (`(2, 5]`, `[2, 5)`).
_GROUPS_NL = _GROUPS_EN
GROUPS = by_language(fr=_GROUPS, en=_GROUPS_EN, nl=_GROUPS_NL)
# A value: a digit, π, a root or infinity, however it is written (`\frac{9}{4}`
# keeps its digits). A name (`x_S`, `a`) is not one.
_VALUE = re.compile(r"\d|π|∞|\\(?:pi|sqrt|infty)(?![A-Za-z])")
# Between two members: a comma followed by a space or a sign. A comma between digits
# is a decimal comma: `(0,5)` is one value.
_COMMA = re.compile(r",(?=\s|[-+])")
# In English every comma separates members: `(1,4)` and `(3,100)` are pairs. A thousands comma
# is not told apart on purpose: a refused « (1,500 m) » costs the model one rewrite, a missed
# `(3,100)` would put the answer on an open exercise.
_COMMA_EN = re.compile(",")
# Dutch: a decimal comma, as French (`(0,5)` is one value, `(1, 4)` a pair).
_COMMA_NL = _COMMA
COMMA = by_language(fr=_COMMA, en=_COMMA_EN, nl=_COMMA_NL)
_LATEX_SPACING = re.compile(r"\\[,;:! ]|\\(?:left|right|quad)\b|[{}~]")


def _n(value: float) -> str:
    """A number as the model wrote it, for a message: no trailing `.0`."""
    return f"{value:g}"


@functools.lru_cache(maxsize=64)
def _parsed(expr: str, variables: frozenset[str]) -> Node:
    """One parse per expression text: `display_board` checks a card, then logs its
    summary from the same trees. The tree is an immutable tuple and a pure function
    of the text, so sharing it is safe; a refusal raises and is not cached."""
    return parse(expr, variables)


def _compile(expr: str, variables: frozenset[str], where: str) -> tuple[Node | None, Refusal | None]:
    try:
        return _parsed(expr, variables), None
    except ExprError as error:
        return None, (f"expr.{error.code}", f"{where} : expr « {expr} » — {error.message}.")


def _in_pack(
    node: Node, powers: bool, pack: str | None, where: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    """A function the chapter never names is outside the course (the pack restriction)."""
    if pack is None:  # unit tests and scripts without a pack
        return None
    words = PACK_WORDS_BY_LANGUAGE[language]
    for name in sorted(functions(node, powers)):
        if name in words and not words[name].search(pack):
            shown = "une exponentielle" if name == "exp" else name
            return (
                "pack_function",
                f"{where} : {shown} n'apparaît pas dans le cours ; ne trace que des fonctions que le cours emploie.",
            )
    return None


def _window(pair: Sequence[float], field: str, where: str) -> Refusal | None:
    a, b = pair
    if a >= b:
        return ("window", f"{where} : {field} va du plus petit au plus grand ({_n(a)} puis {_n(b)}).")
    if max(abs(a), abs(b)) > MAX_BOUND or b - a < MIN_SPAN - _SLACK:
        return (
            "window",
            f"{where} : {field} [{_n(a)} ; {_n(b)}] ne se gradue pas ; bornes d'au plus un million en valeur "
            f"absolue, largeur d'au moins {_n(MIN_SPAN)}. Change d'unité si besoin.",
        )
    return None


def _step(step: float | None, pair: Sequence[float], field: str, where: str) -> Refusal | None:
    if step is None:
        return None
    scaled = step * 10**STEP_DECIMALS
    if abs(scaled - round(scaled)) > 1e-6 * max(1.0, scaled):
        return ("step", f"{where} : {field} {_n(step)} a plus de {STEP_DECIMALS} décimales.")
    count = (pair[1] - pair[0]) / step
    if count < 1 - _SLACK:
        return (
            "step",
            f"{where} : {field} {_n(step)} est plus grand que la fenêtre ({_n(pair[0])} à {_n(pair[1])}).",
        )
    if count > MAX_INTERVALS + _SLACK:
        return (
            "step",
            f"{where} : {field} {_n(step)} coupe la fenêtre en {math.floor(count + _SLACK)} intervalles ; "
            f"{MAX_INTERVALS} au plus.",
        )
    return None


def _aspect(plot: PlotBlock, where: str) -> Refusal | None:
    if not plot.orthonormal:
        return None
    ratio = (plot.y_range[1] - plot.y_range[0]) / (plot.x_range[1] - plot.x_range[0])
    # With the slack, [0.3 ; 0.7] over [0 ; 1] is the 0.4 the model wrote, not 0.39999999999999997.
    if not MIN_ASPECT - _SLACK <= ratio <= MAX_ASPECT + _SLACK:
        return (
            "orthonormal",
            f"{where} : un repère orthonormé garde les proportions de la fenêtre, et y_range fait ici "
            f"{_n(round(ratio, 3))} fois x_range ; entre {_n(MIN_ASPECT)} et {_n(MAX_ASPECT)}, "
            "ou orthonormal false.",
        )
    return None


def _visible(f: Callable[[float], float], xs: Sequence[float], ys: Sequence[float], lo: float, hi: float) -> bool:
    """A sample inside [lo, hi], or a point found between two finite neighbours on
    either side of it: a steep curve crosses the window between samples, a pole
    does not (its halvings never land inside, or land where it is undefined)."""
    if any(lo <= y <= hi for y in ys):
        return True
    for i in range(len(ys) - 1):
        a, b, ya, yb = xs[i], xs[i + 1], ys[i], ys[i + 1]
        if math.isnan(ya) or math.isnan(yb) or not (min(ya, yb) < lo and max(ya, yb) > hi):
            continue
        for _ in range(BISECTIONS):
            m = (a + b) / 2
            ym = f(m)
            if math.isnan(ym):
                break
            if lo <= ym <= hi:
                return True
            if (ym < lo) == (ya < lo):
                a, ya = m, ym
            else:
                b = m
    return False


def _dot(
    f: Callable[[float], float],
    bound: float,
    inward: float,
    span: float,
    dot: str,
    plot: PlotBlock,
    field: str,
    where: str,
) -> Refusal | None:
    """A filled dot sits on f(bound); a hollow one on the limit just inside, where
    the curve arrives. Either must be defined there and inside the window."""
    if dot == "none":
        return None
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    y = f(bound)
    if math.isnan(y) and dot == "hollow":
        y = f(bound + inward * INSIDE * span)
    if math.isnan(y):
        return (
            "endpoint",
            f"{where} : {field} en x = {_n(bound)}, où la courbe n'est pas définie ; "
            "un point plein ou creux s'y placerait au hasard.",
        )
    if not (x0 <= bound <= x1 and y0 <= y <= y1):
        return ("endpoint", f"{where} : le point de {field} ({_n(bound)} ; {_n(y)}) est hors de la fenêtre.")
    return None


def _curve(
    curve: PlotCurve, plot: PlotBlock, where: str, pack: str | None, language: CourseLanguage
) -> Refusal | None:
    node, refused = _compile(curve.expr, CURVE_VARIABLES, where)
    if node is None:
        return refused
    if refusal := _in_pack(node, True, pack, where, language):
        return refusal
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    a, b = curve.domain if curve.domain is not None else (x0, x1)
    if a >= b:
        return ("domain", f"{where} : domain va du plus petit au plus grand ({_n(a)} puis {_n(b)}).")
    lo, hi = max(a, x0), min(b, x1)
    if lo >= hi:
        return (
            "domain",
            f"{where} : domain [{_n(a)} ; {_n(b)}] est hors de la fenêtre (x de {_n(x0)} à {_n(x1)}).",
        )

    def f(v: float) -> float:
        return evaluate(node, v)

    xs = [lo + (hi - lo) * i / SAMPLES for i in range(SAMPLES + 1)]
    ys = [f(x) for x in xs]
    if all(math.isnan(y) for y in ys):
        return ("undefined", f"{where} : « {curve.expr} » n'est définie nulle part entre {_n(lo)} et {_n(hi)}.")
    if not _visible(f, xs, ys, y0, y1):
        return ("outside", f"{where} : la courbe ne passe pas dans la fenêtre (y de {_n(y0)} à {_n(y1)}).")
    return _dot(f, a, 1, b - a, curve.start_dot, plot, "start_dot", where) or _dot(
        f, b, -1, b - a, curve.end_dot, plot, "end_dot", where
    )


def _sequence(
    seq: PlotSequence, plot: PlotBlock, where: str, pack: str | None, language: CourseLanguage
) -> Refusal | None:
    node, refused = _compile(seq.expr, SEQUENCE_VARIABLES, where)
    if node is None:
        return refused
    # A geometric sequence's 0.5^(n-1) is a power, not an exponential function.
    if refusal := _in_pack(node, False, pack, where, language):
        return refusal
    if seq.first > seq.last:
        return ("terms", f"{where} : first ({seq.first}) vient après last ({seq.last}).")
    if seq.last - seq.first + 1 > MAX_TERMS:
        return ("terms", f"{where} : {seq.last - seq.first + 1} termes ; {MAX_TERMS} au plus.")
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    if seq.first < x0 or seq.last > x1:
        return (
            "outside",
            f"{where} : n va de {seq.first} à {seq.last}, hors de x_range ({_n(x0)} à {_n(x1)}).",
        )
    terms = [(n, evaluate(node, n)) for n in range(seq.first, seq.last + 1)]
    if all(math.isnan(u) for _, u in terms):
        return (
            "undefined",
            f"{where} : « {seq.expr} » n'est définie pour aucun n de {seq.first} à {seq.last}.",
        )
    for n, u in terms:
        if not math.isnan(u) and not y0 <= u <= y1:
            return (
                "outside",
                f"{where} : le terme n = {n} ({_n(u)}) sort de la fenêtre (y de {_n(y0)} à {_n(y1)}) ; "
                "élargis y_range ou arrête la suite plus tôt.",
            )
    return None


def _meets_window(line: PlotLine, plot: PlotBlock) -> bool:
    """Liang–Barsky: does any segment of the line meet the window?"""
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    for (ax, ay), (bx, by) in zip(line.vertices, line.vertices[1:]):
        t0, t1, inside = 0.0, 1.0, True
        for p, q in ((ax - bx, ax - x0), (bx - ax, x1 - ax), (ay - by, ay - y0), (by - ay, y1 - ay)):
            if p == 0:
                if q < 0:
                    inside = False
                    break
                continue
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
        if inside and t0 <= t1:
            return True
    return False


def plot_refusal(
    plot: PlotBlock, path: str, pack: str | None = None, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    """The first rule one plot breaks, as (rule, message), or None."""
    where = f"Le graphique {path}"
    if refusal := (
        _window(plot.x_range, "x_range", where)
        or _window(plot.y_range, "y_range", where)
        or _step(plot.x_step, plot.x_range, "x_step", where)
        or _step(plot.y_step, plot.y_range, "y_step", where)
        or _aspect(plot, where)
    ):
        return refusal
    if not (plot.curves or plot.sequences or plot.points or plot.lines):
        return (
            "empty",
            f"{where} : rien à tracer ; donne au moins une courbe, une suite, un point ou une ligne. "
            "Si ton élève doit construire le graphique, n'affiche pas de repère : l'énoncé suffit.",
        )
    for i, curve in enumerate(plot.curves):
        if refusal := _curve(curve, plot, f"{where}, courbe {i + 1}", pack, language):
            return refusal
    for i, seq in enumerate(plot.sequences):
        if refusal := _sequence(seq, plot, f"{where}, suite {i + 1}", pack, language):
            return refusal
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    for i, point in enumerate(plot.points):
        if not (x0 <= point.x <= x1 and y0 <= point.y <= y1):
            name = f" ({point.label})" if point.label else ""
            return (
                "outside",
                f"{where}, point {i + 1}{name} : ({_n(point.x)} ; {_n(point.y)}) est hors de la fenêtre.",
            )
    for i, line in enumerate(plot.lines):
        if not _meets_window(line, plot):
            return ("outside", f"{where}, ligne {i + 1} : elle ne passe pas dans la fenêtre.")
    return None


def _texts(plot: PlotBlock) -> list[tuple[str, str]]:
    """Every text the model wrote on the plot, with where it sits, for the exercise rule."""
    layers: list[tuple[str, Sequence[PlotCurve | PlotSequence | PlotPoint | PlotLine]]] = [
        ("courbe", plot.curves),
        ("suite", plot.sequences),
        ("point", plot.points),
        ("ligne", plot.lines),
    ]
    found = [("x_title", plot.x_title), ("y_title", plot.y_title)]
    found += [(f"{name} {i + 1}", item.label) for name, items in layers for i, item in enumerate(items) if item.label]
    if plot.caption:
        found.append(("caption", plot.caption))
    return found


def _gives_values(group: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> bool:
    """Coordinates or an interval: members split by `;` (the course's separator, never
    prose's), one of them a value, as in `(x_S ; 2)`; or split by a comma, two of
    them values, so « (cm, toutes les 0,5 s) » stays a unit."""
    if ";" in group:
        return any(_VALUE.search(member) for member in group.split(";"))
    return sum(1 for member in COMMA[language].split(group) if _VALUE.search(member)) >= 2


def gives_away(text: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> bool:
    """A relation (=, ≈, ≠, <, ↦, → and their commands), or values in parentheses or
    brackets (`(1/2 ; -9/4)`, `(1,-4)`, `]-1 ; 2[`): what a text on an open exercise's
    drawing may not hold. A bare number is not caught (« toutes les 0,5 s » is a
    quantity). No backtracking pattern: a 200-character caption takes well under a
    millisecond. Shared with scripts/probe.py."""
    flat = _LATEX_SPACING.sub("", text).replace("−", "-")
    if _RELATION.search(flat):
        return True
    return any(
        _gives_values(next(g for g in m.groups() if g is not None), language)
        for m in GROUPS[language].finditer(flat)
    )


def _exercise_refusal(
    plots: Sequence[tuple[str, PlotBlock]], language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    """An exercise's drawing is on the board while the exercise is open: it may not
    write coordinates, draw reading guides, or give a relation, coordinates or an
    interval in any of its texts (R5.1 of spec 008, for plots). Elsewhere the prompt
    carries the rule."""
    for path, plot in plots:
        for i, point in enumerate(plot.points):
            if point.show_values or point.guides:
                return (
                    "exercise_values",
                    f"Le graphique {path}, point {i + 1} accompagne un exercice ouvert : ni show_values ni "
                    "guides, sinon il montre la réponse. Ils viendront avec la correction.",
                )
        for field, text in _texts(plot):
            if gives_away(text, language):
                return (
                    "exercise_text",
                    f"Le graphique {path}, {field} : « {text} » donne une équation, une inégalité, des "
                    "coordonnées ou un intervalle ; sur un exercice ouvert, une étiquette est un nom ($f$, $A$) "
                    "et un titre une grandeur. Les données vont dans l'énoncé.",
                )
    return None


def plots_refusal(items: Sequence[tuple[str, PlotBlock]], card: BoardCard, ctx: TurnContext) -> Refusal | None:
    """The first rule the card's plots break, as (rule, message), or None: the
    exercise rules first (the one place the tool knows an exercise is open), then
    each plot in card order, against the chapter's pack. How many drawings a card
    holds was checked before, by `display_board`, across every family."""
    if isinstance(card, ExerciseCard) and (refusal := _exercise_refusal(items, ctx.language)):
        return refusal
    for path, plot in items:
        if refusal := plot_refusal(plot, path, ctx.pack, ctx.language):
            return refusal
    return None


def _functions(expr: str, variables: frozenset[str], powers: bool) -> set[str]:
    try:
        return functions(_parsed(expr, variables), powers)  # the tree plots_refusal parsed
    except ExprError:  # never after plots_refusal passed; a log line must not raise
        return set()


def plots_summary(items: Sequence[tuple[str, PlotBlock]]) -> dict[str, Any]:
    """What `plot_displayed` logs besides the ids: layer counts and function names
    from the closed set, never an expression, a label or a number. The trees come
    from `_parsed`, which `plots_refusal` filled: nothing is parsed twice."""
    layers = {"curves": 0, "sequences": 0, "points": 0, "lines": 0}
    names: set[str] = set()
    for _, plot in items:
        layers["curves"] += len(plot.curves)
        layers["sequences"] += len(plot.sequences)
        layers["points"] += len(plot.points)
        layers["lines"] += len(plot.lines)
        for curve in plot.curves:
            names |= _functions(curve.expr, CURVE_VARIABLES, True)
        for seq in plot.sequences:
            names |= _functions(seq.expr, SEQUENCE_VARIABLES, False)
    return {"count": len(items), "layers": layers, "functions": sorted(names)}
