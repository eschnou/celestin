# 009 — The `plot` block (graphs in a repère): design

Sections 1 to 6 are the design as it was reviewed on 28 September 2026, kept as written:
it is what the code comments cite. Where the code now differs, a note marked **As built** says
so in place, and section 7 lists every deviation. The scratchpad paths the design mentions
(prototypes, fuzz scripts) were never part of the repository.

## 1. Summary

A `plot` block is a cartesian graph. Célestin gives the mathematics and the board draws it. The model supplies:
- a window (`x_range`, `y_range`);
- axis titles with their units;
- optional graduations (`x_step`, `y_step`), `grid`, and `orthonormal` (new, default false);
- four flat typed lists: `curves` (an expression in a hand-written closed grammar, with an optional `domain` for piecewise graphs and `start_dot`/`end_dot` none/filled/hollow), `sequences` (general term in n, from `first`, which defaults to 1 because FWB indexes from u₁, to `last`, drawn as isolated points), `points` (filled/hollow/cross marks, `guides`, `show_values`) and `lines` (broken lines for data, or dashed construction lines);
- a caption.

**Grammar.** It has `.` decimals, + − * / ^ and unary minus, with -x^2 = -(x^2) and 2^3^2 = 2^9. Implicit multiplication works only before a name or "(" (2x, 2(x+1)), and `1/2x` is refused as ambiguous. Functions are sqrt, cbrt (new), abs, exp, ln, log, sin, cos, tan (radians); constants are pi and e. There is one variable: x or t for a curve, n for a sequence. Several inputs are refused with a targeted message:
- scientific notation (`1e-3`), with new code `scientific`, where it used to be silently misread as 1·e − 3;
- `$`, `{`, `}` and `\`, as LaTeX;
- a comma;
- `y =`.

On both sides, a value that is not finite at any step makes the expression undefined there (NaN).

**Parsers.** The backend parses and validates in `app/domain/expression.py`, and the frontend parses and evaluates in `plot/expression.ts`. Both prototypes pass one shared 96-case JSON table with 0 disagreements. `tsc` passes with the frontend's strict flags.

**Tool rules.** They live in `app/services/tools/plots.py`: 18 rule codes, French messages that name the path, and logs with ids and codes only. Every rule the critique asked for was prototyped and run; the scratch checks all pass.

**Changes from the first design:**
- the straddle test bisects, so a pole is no longer a false pass;
- the step count has a float tolerance and is reported as intervals;
- the window bounds are limited in size;
- a sequence has every term in the window;
- the pack rule sees `e^x`, `2^x` and upright `\mathrm{e}^x`;
- the exercise rule checks labels, axis titles and the caption;
- the screen-reader text never states domain bounds or dot positions.

**Rendering.**
- **Maths text:** everything the model writes is an HTML overlay typeset by KaTeX (always inline, even `$$`). The SVG holds only numbers we format with the decimal comma, so the charts' `label_math` deviation (D10) does not recur.
- **Colour:** curves, sequences and solid lines that share a label (or share having none) share one colour and one label. A curve given in pieces reads as one function.
- **Contrast:** label text is in foreground (15,5:1), with a 2 px underline in the curve's colour.
- **Graduations:** tick labels thin repeatedly to a round multiple of the step, anchored at 0.
- **x title:** it stays inside the plot only where nothing is drawn; otherwise it moves to a band below the plot.
- **Axes:** an axis that sits on the window's edge because 0 is outside it gets no arrow.

**Drawing field.** It becomes a union with a callable discriminator that falls back to "chart", so a drawing with no `type` still validates. This was checked with pydantic 2.13.

**Schema cost.** Measured at +4 708 characters.

> **As built.** The drawing union's fallback is refined: a drawing without `type` is read from
> its keys (`x_range`, `y_range` or `curves` make it a plot, refused for its missing `type`),
> and a chart only when no key tells (verification #3). `per_card` left this module for
> `display_board`'s cap across families (§3.1).

## 2. Model

### 2.1 The block: `app/domain/plot.py`

Models only: types, enums, sizes, finite numbers; one docstring, on the block.

```python
"""Plot blocks: graphs in a cartesian plane (plot design 4.1).

The model gives mathematics: a window, curves by their expression, sequences by
their general term, points and broken lines. The board samples, lays out and
draws them; it never receives pixels, colours or markup. Only rules that never
change live here (types, enums, sizes, finite numbers). Parsing an expression
and every rule that could change run in `display_board`
(`app/services/tools/plots.py`), so a stored card keeps replaying.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Num = Annotated[float, Field(allow_inf_nan=False)]
# [min, max] on one axis, [a, b] for a domain, [x, y] for a vertex.
Pair = Annotated[list[Num], Field(min_length=2, max_length=2)]
Step = Annotated[float, Field(gt=0, allow_inf_nan=False)]
# A name ($f$, $\mathcal{C}_g$, $A$, « phase 2 »): it has to fit beside a curve at 400 px.
Label = Annotated[str, Field(min_length=1, max_length=24)]
AxisTitle = Annotated[str, Field(min_length=1, max_length=40)]
Caption = Annotated[str, Field(min_length=1, max_length=200)]
# Descriptions reach the model with the schema: the grammar is ours, not LaTeX, and
# the model would otherwise write `x²`, `\frac{1}{x}`, `1e-3` or `y = 2x + 1`.
Expr = Annotated[
    str,
    Field(
        min_length=1,
        max_length=120,
        description=(
            "En x ou t, pas du LaTeX : nombres à point décimal (pas de 1e-3), + - * / ^, 2x, "
            "sqrt cbrt abs exp ln log sin cos tan (radians), pi, e. Sans « y = »."
        ),
    ),
]
TermExpr = Annotated[
    str,
    Field(min_length=1, max_length=120, description="Terme général uₙ en n (pas de récurrence), écrit comme expr."),
]
Dot = Literal["none", "filled", "hollow"]

MAX_CURVES = 6
MAX_SEQUENCES = 3
MAX_POINTS = 20
MAX_LINES = 8
MAX_VERTICES = 30


class PlotCurve(_Model):
    expr: Expr
    domain: Pair | None = None
    start_dot: Dot = "none"
    end_dot: Dot = "none"
    dashed: bool = False
    label: Label | None = None


class PlotSequence(_Model):
    expr: TermExpr
    first: Annotated[int, Field(ge=0, le=1000)] = 1
    last: Annotated[int, Field(ge=0, le=1000)]
    label: Label | None = None


class PlotPoint(_Model):
    x: Num
    y: Num
    label: Label | None = None
    mark: Literal["filled", "hollow", "cross"] = "filled"
    guides: bool = False
    show_values: bool = False


class PlotLine(_Model):
    vertices: Annotated[list[Pair], Field(min_length=2, max_length=MAX_VERTICES)]
    dashed: bool = False
    label: Label | None = None


class PlotBlock(_Model):
    """A graph in a cartesian plane, drawn by the board in the given window: curves
    from their expression, sequences, points, broken lines. Never pixels."""

    type: Literal["plot"] = "plot"
    x_range: Pair
    y_range: Pair
    x_title: AxisTitle
    y_title: AxisTitle
    x_step: Step | None = None
    y_step: Step | None = None
    grid: bool = True
    orthonormal: bool = False
    curves: Annotated[list[PlotCurve], Field(max_length=MAX_CURVES)] = []
    sequences: Annotated[list[PlotSequence], Field(max_length=MAX_SEQUENCES)] = []
    points: Annotated[list[PlotPoint], Field(max_length=MAX_POINTS)] = []
    lines: Annotated[list[PlotLine], Field(max_length=MAX_LINES)] = []
    caption: Caption | None = None
```

Why these shapes:
- **Name prefix.** The `Plot*` prefix keeps these $defs clear of the `Point`/`Line` names in the parallel `figure` block.
- **Compact structures.** Pairs replace `{min,max}` objects, and flat per-layer lists replace a discriminated layer union; both keep the schema small.
- **Labels.** `Label` is capped at 24 characters: at 7,8 px per character that is 190 px, which fits in the ~300 px plot area at 400 px. A label is a name; the data goes in the statement.
- **`orthonormal`.** Added now, not later. First-degree function chapters (slopes, perpendicular lines) are read visually, and independent x and y scales distort slopes.

> **As built.** `PlotCurve.expr` and `PlotSequence.expr` carry the `NOT_PROSE` marker
> (`app/domain/prose.py`), so a `\frac` in an expression reaches the parser and gets
> `expr.latex` instead of the board's LaTeX check.

### 2.2 The expression grammar: `app/domain/expression.py`

A companion domain module, pure, owned by this block: the prototype that passed the 96-case table.

```python
"""Expressions a plot draws (plot design 3.2).

A closed grammar the model writes curves and sequences in. It is parsed here, to
refuse a bad one as a tool error, and in the browser, to draw it
(`frontend/src/components/celestin/plot/expression.ts`). Both sides pass the same case
table, `tests/fixtures/expression_cases.json`: change one, change the other and
the table. Model text is parsed, never run.

    sum    := prod (("+" | "-") prod)*
    prod   := unary (("*" | "/") unary | power)*   a bare `power` is an implicit ×,
                                                  only before a name or "(": 2x, 2(x+1)
    unary  := ("+" | "-") unary | power            -x^2 is -(x^2)
    power  := atom ("^" unary)?                    2^3^2 is 2^9, 2^-1 is 0.5
    atom   := number | name | function "(" sum ")" | "(" sum ")"

Numbers are `12` or `12.5`; `1e-3` is refused, not read as 1·e − 3. `−`, `·`, `×`,
`⋅` read as `-`, `*`, `*`, `*`; `π` as `pi`. An implicit product right after a
division (`1/2x`) is refused as ambiguous.

A value that is not a finite real number at any step (1/0, sqrt(-1), ln(0), an
overflow) makes the expression undefined there: NaN, on both sides. So 1/(1/x)
is undefined at 0, as its domain says, and x^(1/3) for x < 0: cbrt(x) is the
cube root of every real.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

FUNCTIONS: dict[str, Callable[[float], float]] = {
    "sqrt": math.sqrt,
    "cbrt": math.cbrt,  # Python 3.11+; the backend requires 3.12
    "abs": abs,
    "exp": math.exp,
    "ln": math.log,
    "log": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
}
CONSTANTS = {"pi": math.pi, "π": math.pi, "e": math.e}
CURVE_VARIABLES = frozenset({"x", "t"})
SEQUENCE_VARIABLES = frozenset({"n"})
MAX_DEPTH = 24

_ALIASES = {"−": "-", "·": "*", "×": "*", "⋅": "*"}
_OPERATORS = "+-*/^()"
_DIGITS = "0123456789"
_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"  # ASCII only, like /[A-Za-z]/
_SPACES = " \t\n\r  "  # explicit: str.isspace() and JS \s differ
_NAN = float("nan")

# ("num", v) | ("num", v, "e" | "pi" | "π") | ("var",) | ("neg", a)
# | ("bin", op, a, b) | ("call", name, a)
Node = tuple[Any, ...]


class ExprError(Exception):
    """Why an expression is refused: a code shared with the browser, a French reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class _Token:
    kind: str  # "num" | "name" | "op" | "end"
    text: str
    at: int


def _digit(source: str, i: int) -> bool:
    return i < len(source) and source[i] in _DIGITS


def _tokens(source: str) -> list[_Token]:
    out: list[_Token] = []
    i = 0
    while i < len(source):
        c = _ALIASES.get(source[i], source[i])
        if c in _SPACES:
            i += 1
        elif c in _DIGITS:
            j = i
            while _digit(source, j):
                j += 1
            if source[j : j + 1] == ".":
                if not _digit(source, j + 1):
                    raise ExprError("syntax", f"nombre incomplet « {source[i : j + 1]} »")
                j += 1
                while _digit(source, j):
                    j += 1
            # 1e-3, 6.67e-11, 2E5: scientific notation would otherwise read as 1·e − 3.
            if source[j : j + 1] in ("e", "E") and (
                _digit(source, j + 1) or (source[j + 1 : j + 2] in ("+", "-", "−") and _digit(source, j + 2))
            ):
                raise ExprError("scientific", "pas de notation scientifique : écris 0.001 ou 10^-3")
            out.append(_Token("num", source[i:j], i))
            i = j
        elif c == "π":
            out.append(_Token("name", c, i))
            i += 1
        elif c in _LETTERS:
            j = i + 1
            while j < len(source) and source[j] in _LETTERS:
                j += 1
            out.append(_Token("name", source[i:j], i))
            i = j
        elif c in _OPERATORS:
            out.append(_Token("op", c, i))
            i += 1
        elif c in "\\${}":
            raise ExprError("latex", "c'est une expression de calcul, pas du LaTeX : écris 1/x, sqrt(x), x^2")
        elif c == ",":
            raise ExprError("comma", "un nombre décimal s'écrit ici avec un point : 0.5")
        elif c == "=":
            raise ExprError("equation", "donne seulement l'expression, sans « y = » ni « f(x) = »")
        elif c == "|":
            raise ExprError("syntax", "la valeur absolue s'écrit abs(…)")
        elif c in "²³":
            raise ExprError("syntax", "une puissance s'écrit avec ^ : x^2")
        else:
            raise ExprError("syntax", f"symbole « {source[i]} » inattendu en position {i + 1}")
    out.append(_Token("end", "", len(source)))
    return out


class _Parser:
    def __init__(self, source: str, variables: frozenset[str]) -> None:
        self.tokens = _tokens(source)  # tokenizer refusals (latex, comma, …) win over parse ones
        self.i = 0
        self.variables = variables
        self.seen: str | None = None
        self.depth = 0

    def peek(self) -> _Token:
        return self.tokens[self.i]

    def is_op(self, chars: str) -> bool:
        t = self.tokens[self.i]
        return t.kind == "op" and t.text in chars

    def enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExprError("depth", "expression trop imbriquée")

    def close(self) -> None:
        if not self.is_op(")"):
            raise ExprError("syntax", "parenthèse non fermée")
        self.i += 1

    def unexpected(self) -> ExprError:
        t = self.peek()
        if t.kind == "end":
            return ExprError("syntax", "expression incomplète")
        return ExprError("syntax", f"« {t.text} » inattendu en position {t.at + 1}")

    def parse(self) -> Node:
        if self.peek().kind == "end":
            raise ExprError("syntax", "expression vide")
        node = self.sum()
        if self.peek().kind != "end":
            raise self.unexpected()
        return node

    def sum(self) -> Node:
        node = self.prod()
        while self.is_op("+-"):
            op = self.tokens[self.i].text
            self.i += 1
            node = ("bin", op, node, self.prod())
        return node

    def prod(self) -> Node:
        node = self.unary()
        after_division = False
        while True:
            t = self.peek()
            if self.is_op("*/"):
                self.i += 1
                node = ("bin", t.text, node, self.unary())
                after_division = t.text == "/"
            elif t.kind == "name" or self.is_op("("):
                if after_division:
                    raise ExprError(
                        "ambiguous",
                        "une division suivie d'un produit sans signe est ambiguë : écris 1/(2x) ou (1/2)x",
                    )
                node = ("bin", "*", node, self.power())
            else:
                return node

    def unary(self) -> Node:
        if self.is_op("+-"):
            op = self.tokens[self.i].text
            self.i += 1
            self.enter()
            inner = self.unary()
            self.depth -= 1
            return ("neg", inner) if op == "-" else inner
        return self.power()

    def power(self) -> Node:
        base = self.atom()
        if self.is_op("^"):
            self.i += 1
            self.enter()
            exponent = self.unary()
            self.depth -= 1
            return ("bin", "^", base, exponent)
        return base

    def atom(self) -> Node:
        t = self.peek()
        if t.kind == "num":
            self.i += 1
            return ("num", float(t.text))
        if self.is_op("("):
            self.i += 1
            self.enter()
            inner = self.sum()
            self.depth -= 1
            self.close()
            return inner
        if t.kind != "name":
            raise self.unexpected()
        self.i += 1
        if t.text in FUNCTIONS:
            if not self.is_op("("):
                raise ExprError("syntax", f"{t.text} s'écrit avec des parenthèses : {t.text}(x)")
            self.i += 1
            self.enter()
            inner = self.sum()
            self.depth -= 1
            self.close()
            return ("call", t.text, inner)
        if t.text in CONSTANTS:
            return ("num", CONSTANTS[t.text], t.text)  # tagged: `functions` reports e as exp
        if t.text in self.variables:
            if self.seen is not None and self.seen != t.text:
                raise ExprError("variables", f"une seule variable, pas {self.seen} et {t.text}")
            self.seen = t.text
            return ("var",)
        allowed = " ou ".join(sorted(self.variables))
        raise ExprError(
            "unknown_name", f"« {t.text} » inconnu ; permis : {allowed}, pi, e, " + ", ".join(FUNCTIONS)
        )


def parse(source: str, variables: frozenset[str] = CURVE_VARIABLES) -> Node:
    """The expression's tree, or ExprError(code, reason)."""
    return _Parser(source, variables).parse()


def _finite(v: float) -> float:
    return v if math.isfinite(v) else _NAN


def evaluate(node: Node, value: float) -> float:
    """The expression at `value`, NaN where it is undefined. Never raises."""
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        return value
    if kind == "neg":
        return -evaluate(node[1], value)
    if kind == "call":
        a = evaluate(node[2], value)
        if math.isnan(a):
            return _NAN
        try:
            return _finite(FUNCTIONS[node[1]](a))
        except (ValueError, OverflowError):
            return _NAN
    _, op, left, right = node
    a, b = evaluate(left, value), evaluate(right, value)
    if math.isnan(a) or math.isnan(b):
        return _NAN
    if op == "+":
        return _finite(a + b)
    if op == "-":
        return _finite(a - b)
    if op == "*":
        return _finite(a * b)
    if op == "/":
        return _NAN if b == 0 else _finite(a / b)
    try:
        return _finite(math.pow(a, b))  # never `**`: (-8) ** (1/3) is a complex number
    except (ValueError, OverflowError, ZeroDivisionError):
        return _NAN


def _has_variable(node: Node) -> bool:
    return node[0] == "var" or any(_has_variable(c) for c in node[1:] if isinstance(c, tuple))


def functions(node: Node, powers: bool = True) -> set[str]:
    """The functions an expression uses, for the pack rule and the logs: those it
    calls, plus `exp` for the number e and, with `powers`, for a power whose exponent
    holds the variable. 2^x is an exponential function; a geometric sequence's
    0.5^(n-1) is not, so sequences pass powers=False."""
    kind = node[0]
    if kind == "num":
        return {"exp"} if node[2:] == ("e",) else set()
    found: set[str] = set().union(*(functions(c, powers) for c in node[1:] if isinstance(c, tuple)))
    if kind == "call":
        found.add(node[1])
    if kind == "bin" and node[1] == "^" and powers and _has_variable(node[3]):
        found.add("exp")
    return found
```

What `functions()` returned in the prototype:

| expression | functions |
|---|---|
| `e^x` | {exp} |
| `2^x` | {exp} |
| `2^(x^2)` | {exp} |
| `2e` | {exp} |
| `x^2` | {} |
| `3*0.5^(n-1)` (powers=False) | {} |
| `e^n` | {exp} |
| `cbrt(x)` | {cbrt} |
| `sin(x)+ln(exp(x))` | {sin, ln, exp} |

Timing: the tree-walking `evaluate` takes 6,8 ms for 6 curves × 401 samples of `sin(x)/x + sqrt(abs(x)) - 2x^2 + e^(-x/3)`.

### 2.3 The seven reference plots

One valid plot per use the design names. The backend's `tests/unit/test_plot_models.py` `VALID`
and the frontend's `plot/__tests__/fixtures.ts` `PLOTS` hold the same seven:

- `parabola`: x² − 4, window [−4 ; 4] × [−5 ; 6], label $f$, point S(0 ; −4) with `show_values`;
- `motion`: 2t / 10 / 10 − 2,5(t − 12) with domains, titles `$t$ (s)` / `$v$ (m/s)`, steps 2;
- `sequence`: 2 + 3(n − 1) from 1 to 7, window [0 ; 8] × [0 ; 22];
- `hyperbola`: 1/(x − 1) plus a dashed line [[1, −5], [1, 5]];
- `piecewise`: x + 1 on [−3 ; 1] with a hollow end, and 4 on [1 ; 4] with a filled start, both
  labelled $f$;
- `data`: 5 crosses from the MRU lab plus a line [[0, 0], [2, 48]], `x_step` 0,5;
- `orthonormal`: 0,5x + 1 on [−5 ; 5] × [−2 ; 4].

## 3. Tool rules: `app/services/tools/plots.py`

### 3.1 Rule table

Every message starts « Le graphique {path} », where path is `blocks[i]` or `drawing`. Messages about one layer add « , courbe N », « , suite N », « , point N (label) » or « , ligne N ». Numbers use `f"{v:g}"`, the model's own dot notation, as in charts.

| code | applies to | refused when | French message template |
|---|---|---|---|
| `window` | `x_range`, `y_range` | min ≥ max; a bound beyond ±1e6; a span < 0.001 | « Le graphique {path} : x_range va du plus petit au plus grand ({a} puis {b}). » / « … : x_range [{a} ; {b}] ne se gradue pas ; bornes d'au plus un million en valeur absolue, largeur d'au moins 0.001. Change d'unité si besoin. » |
| `step` | `x_step`, `y_step` | more than 4 decimals; span/step < 1 − 1e-9; span/step > 30 + 1e-9 | « … : x_step {s} a plus de 4 décimales. » / « … : x_step {s} est plus grand que la fenêtre ({a} à {b}). » / « … : x_step {s} coupe la fenêtre en {k} intervalles ; 30 au plus. » |
| `orthonormal` | `orthonormal: true` | (y1−y0)/(x1−x0) outside [0,4 ; 2] | « … : un repère orthonormé garde les proportions de la fenêtre, et y_range fait ici {r} fois x_range ; entre 0.4 et 2, ou orthonormal false. » |
| `empty` | the plot | no curve, sequence, point or line | « … : rien à tracer ; donne au moins une courbe, une suite, un point ou une ligne. » |
| `expr.<code>` | `curves[i].expr` (x, t), `sequences[i].expr` (n) | the parser refuses: `syntax`, `unknown_name`, `latex`, `comma`, `equation`, `scientific`, `ambiguous`, `variables`, `depth` | « Le graphique {path}, courbe {i} : expr « {expr} » — {reason}. » e.g. « … expr « 1e-3x » — pas de notation scientifique : écris 0.001 ou 10^-3. » |
| `pack_function` | an expr using exp (also e and x-exponent powers on curves), ln, log, cbrt, sin, cos, tan | `ctx.pack` is set and none of that function's `PACK_WORDS` occur in it | « …, courbe {i} : une exponentielle n'apparaît pas dans le cours ; ne trace que des fonctions que le cours emploie. » (« ln n'apparaît pas… » for the others) |
| `domain` | `curves[i].domain` | a ≥ b; or no overlap with the window's x range | « …, courbe {i} : domain va du plus petit au plus grand ({a} puis {b}). » / « …, courbe {i} : domain [{a} ; {b}] est hors de la fenêtre (x de {x0} à {x1}). » |
| `undefined` | curve (401 samples over domain ∩ window), sequence (every term) | no finite value | « …, courbe {i} : « {expr} » n'est définie nulle part entre {lo} et {hi}. » / « …, suite {i} : « {expr} » n'est définie pour aucun n de {first} à {last}. » |
| `outside` | curve, sequence, point, line | **curve:** no sample in [y0 ; y1], and no bisection (40 halvings) between finite neighbours straddling the band lands in it, so a pole is not a crossing. **Sequence:** n range not inside x_range, or ANY defined term outside [y0 ; y1]. **Point:** outside the window. **Line:** no segment meets the window (Liang–Barsky) | « …, courbe {i} : la courbe ne passe pas dans la fenêtre (y de {y0} à {y1}). » / « …, suite {i} : n va de {first} à {last}, hors de x_range ({x0} à {x1}). » / « …, suite {i} : le terme n = {n} ({u}) sort de la fenêtre (y de {y0} à {y1}) ; élargis y_range ou arrête la suite plus tôt. » / « …, point {i} (A) : ({x} ; {y}) est hors de la fenêtre. » / « …, ligne {i} : elle ne passe pas dans la fenêtre. » |
| `endpoint` | `start_dot` / `end_dot` ≠ none | filled: f(bound) undefined. Hollow: also undefined at bound ± 1e-9·(b−a) inside. Either: the dot is outside the window | « …, courbe {i} : start_dot en x = {b}, où la courbe n'est pas définie ; un point plein ou creux s'y placerait au hasard. » / « … : le point de end_dot ({x} ; {y}) est hors de la fenêtre. » |
| `terms` | `sequences[i]` | first > last; more than 40 terms | « …, suite {i} : first ({f}) vient après last ({l}). » / « …, suite {i} : {k} termes ; 40 au plus. » |
| `exercise_values` | `drawing` of an `exercise` | a point has `show_values` or `guides` | « Le graphique drawing, point {i} accompagne un exercice ouvert : ni show_values ni guides, sinon il montre la réponse. Ils viendront avec la correction. » |
| `exercise_text` | `drawing` of an `exercise`: x_title, y_title, every curve, sequence, point and line label, and the caption | `gives_away(text)`: see below | « Le graphique drawing, caption : « La droite $y = 2x+1$ » donne une équation, une valeur ou des coordonnées ; sur un exercice ouvert, une étiquette est un nom ($f$, $A$) et un titre une grandeur. Les données vont dans l'énoncé. » |
| `per_card` | an explanation | more than 2 plot blocks | « Une carte porte au plus 2 graphiques de fonctions ; répartis les autres sur une carte suivante. » |

> **As built.** `per_card` is removed, with `MAX_PLOTS_PER_CARD` (verification #10):
> `display_board` caps a card at two drawings of any family before the families run
> (`drawing_refused`, rule `per_card`). The `orthonormal` bounds allow a float slack of 1e-9 on
> both sides, the same on the board (`ASPECT_SLACK` in `plot/sanitise.ts`), so a ratio that is
> 0,4 up to float noise is accepted. `exercise_text` refuses more than written here (next note).

**How `gives_away` decides.** It first strips LaTeX spacing (`\,` `\;` `\:` `\!` `\ `, `\left`, `\right`, `\quad`, braces, `~`) and turns `−` into `-`. It then looks for `=` `≈` `≃` `↦` `\approx` `\simeq` `\mapsto`, or a parenthesised pair of numbers separated by `;` or by `,` plus a space. Prototype results:

| text | result |
|---|---|
| `$y = 2x+1$` | refused |
| `$S(1\,;\,-4)$` | refused |
| `$(0{,}5 ; 12)$` | refused |
| `(2, 3)` | refused |
| `$x_0 \approx 1{,}4$` | refused |
| `$x \mapsto 2x+1$` | refused |
| `$f(x)$` | accepted |
| `$\mathcal{C}_f$` | accepted |
| `$u_n$` | accepted |
| `$v$ (m/s)` | accepted |
| « Position (cm, toutes les 0,5 s) » | accepted |
| `(0,5)` | accepted |

> **As built.** `gives_away` is a scan of groups, not one regex (the reviewer's single regex
> backtracked as about n⁴). After stripping LaTeX spacing, `\left`, `\right`, braces and `~`,
> it refuses any relation: `= ≈ ≃ ≠ < > ≤ ≥ ⩽ ⩾ ≦ ≧ ↦ → ⟶ ⟼` or the commands `\approx(eq)`,
> `\simeq`, `\ne(q)`, `\le(q)`, `\ge(q)`, `\leqslant`, `\geqslant`, `\leqq`, `\geqq`, `\lt`,
> `\gt`, `\mapsto`, `\longmapsto`, `\to`, `\rightarrow`, `\longrightarrow`, each not followed by
> a letter (⩽ ⩾ ≦ ≧ `\leqq` `\geqq` added after verification #13). Then every innermost
> `(…)` and bracket pair either way round: with a `;`, refused when one member holds a value (a
> digit, π, ∞, `\pi`, `\sqrt`, `\infty`); otherwise, split on a comma followed by a space or a
> sign, refused when two members hold one. The message says « donne une équation, une
> inégalité, des coordonnées ou un intervalle ».

**Order of checks.**
1. `plots_refusal` first applies the exercise rules: values, then texts.
2. It then applies `per_card`.
3. It then runs each plot in card order. Within a plot the order is:
   - `window` (x, then y), `step` (x, then y), `orthonormal`, `empty`;
   - each curve: expr, pack_function, domain, undefined, outside, endpoint;
   - each sequence: expr, pack_function, terms, outside (n range), undefined, outside (terms);
   - points (outside), then lines (outside).

The first refusal wins, as for charts.

> **As built.** Step 2 is gone: the card cap is `display_board`'s, across families, and it
> runs before any family's rules.

**Not a rule.** Model text never becomes SVG, so there is no `label_math`: `$…$` is welcome in titles, labels and the caption. The existing `_bare_commands` check covers those prose fields. `expr` joins `_NOT_PROSE`, so a `\frac` in an expression reaches the parser and gets `expr.latex`.

> **As built.** The string checks now run in `display_board` on the parsed card, and `expr`
> carries `NOT_PROSE` rather than joining a list of names. A refusal inside a plot is logged as
> `plot_refused` with rule `string_control`, `string_latex` or `string_script`.

**Refused by the model itself.** Pydantic refuses, among others:
- NaN or inf;
- an extra field;
- a 7th curve, a 21st point, a 4th sequence, a 9th line, a 31st vertex;
- `last` > 1000;
- a 25-character label;
- `x_step` ≤ 0.

The error loc keeps the tag, as checked with pydantic 2.13: `('card','exercise','drawing','plot','y_range',1) finite_number`. The generalised `log_schema_refusal` logs these as `plot_refused` with `rule: schema.<type>`.

**Card-level rule (withholding).** `exercise_values` and `exercise_text` run only when `isinstance(card, ExerciseCard)`, the one place where the tool knows an exercise is open (charts D12).

**Logs.**
- `plot_displayed`: the where-ids, plus `layers` ({curves, sequences, points, lines} counts) and `functions` (a sorted list from the closed set, `exp` included for e and 2^x).
- `plot_refused`: the where-ids plus `rule`.

An expression, label, title or number is never logged.

### 3.2 Signatures board.py calls

```python
def plots_refusal(
    plots: Sequence[tuple[str, PlotBlock]], exercise: bool = False, pack: str | None = None
) -> tuple[str, str] | None: ...

def plot_summary(plots: Sequence[tuple[str, PlotBlock]]) -> dict[str, Any]: ...

def gives_away(text: str) -> bool: ...   # also imported by scripts/probe.py
```

> **As built.** `plots_refusal(items, card, ctx)` and `plots_summary(items)`, like the other
> families; the exercise rules run when the card is an `ExerciseCard`, and the pack is
> `ctx.pack`. `plot_refusal(plot, path, pack=None)`, `gives_away` and `PACK_WORDS` stay public.
> The summary adds the plot `count`. Each expression is parsed once per call: `_parsed` is a
> small `lru_cache` (64 entries, a pure function of the text) shared by the refusal pass and the
> summary (verification #17).

### 3.3 The prototype of `plots.py`

It ran all the cases in the tests: 0 mismatches; 6 heavy curves in 6,8 ms. The file has moved on
since (the notes above and §7); the prototype is kept for the reasoning in its comments.

```python
"""The plot rules `display_board` applies (plot design 3.3).

They run in the tool, not on the card model: they could change (a limit, the
sampling, the pack words) and a stored card must keep replaying. Each refusal is a
rule code for the logs and a French message naming the field, handed back to the
model to fix. Expressions are parsed with `app/domain/expression.py`, the grammar
the board draws with.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from app.domain.expression import CURVE_VARIABLES, SEQUENCE_VARIABLES, ExprError, Node, evaluate, functions, parse
from app.domain.plot import PlotBlock, PlotCurve, PlotLine, PlotSequence

Refusal = tuple[str, str]

# More than two graphs on one explanation stops being a board and becomes a report.
MAX_PLOTS_PER_CARD = 2
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
# every maths course under many spellings, so only these are looked up.
PACK_WORDS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "exp": r"\bexp\b|exponentiel|\be\}?\s*\^",  # e^x, \mathrm{e}^{x}
        "ln": r"\bln\b|logarithme",
        "log": r"\blog\b|logarithme",
        "cbrt": r"racine cubique|racine troisième|\\sqrt\s*\[\s*3\s*\]|∛",
        "sin": r"\bsin\b|sinus",
        "cos": r"\bcos\b|cosinus",
        "tan": r"\btan\b|tangente",
    }.items()
}
# What gives an exercise's answer away in a label, a title or a caption: an equation
# or an approximation, a mapping, or a pair of numbers, once LaTeX spacing is gone.
_GIVES_AWAY = re.compile(
    r"=|≈|≃|↦|\\(?:approx|simeq|mapsto)\b"
    r"|\(\s*[-+]?\s*\d[\d.,]*\s*(?:;|,\s)\s*[-+]?\s*\d[\d.,]*\s*\)"
)
_LATEX_SPACING = re.compile(r"\\[,;:! ]|\\(?:left|right|quad)\b|[{}~]")


def _n(value: float) -> str:
    """A number as the model wrote it, for a message: no trailing `.0`."""
    return f"{value:g}"


def _compile(expr: str, variables: frozenset[str], where: str) -> tuple[Node | None, Refusal | None]:
    try:
        return parse(expr, variables), None
    except ExprError as error:
        return None, (f"expr.{error.code}", f"{where} : expr « {expr} » — {error.message}.")


def _in_pack(node: Node, powers: bool, pack: str | None, where: str) -> Refusal | None:
    if pack is None:  # unit tests and scripts without a pack
        return None
    for name in sorted(functions(node, powers)):
        if name in PACK_WORDS and not PACK_WORDS[name].search(pack):
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
    if max(abs(a), abs(b)) > MAX_BOUND or b - a < MIN_SPAN:
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
        return ("step", f"{where} : {field} {_n(step)} est plus grand que la fenêtre ({_n(pair[0])} à {_n(pair[1])}).")
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
    if not MIN_ASPECT <= ratio <= MAX_ASPECT:
        return (
            "orthonormal",
            f"{where} : un repère orthonormé garde les proportions de la fenêtre, et y_range fait ici "
            f"{_n(round(ratio, 3))} fois x_range ; entre {_n(MIN_ASPECT)} et {_n(MAX_ASPECT)}, ou orthonormal false.",
        )
    return None


def _visible(f: Callable[[float], float], xs: Sequence[float], ys: Sequence[float], lo: float, hi: float) -> bool:
    """A sample inside [lo, hi], or a point found between two finite neighbours on
    either side of it: a steep curve crosses the window between samples, a pole
    does not (its halvings never land inside, or land where it is undefined)."""
    if any(lo <= y <= hi for y in ys):
        return True
    for i in range(len(ys) - 1):
        a, b, ya = xs[i], xs[i + 1], ys[i]
        yb = ys[i + 1]
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


def _dot(f: Callable[[float], float], bound: float, inward: float, span: float, dot: str,
         plot: PlotBlock, field: str, where: str) -> Refusal | None:
    if dot == "none":
        return None
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    y = f(bound)
    if math.isnan(y) and dot == "hollow":
        y = f(bound + inward * INSIDE * span)
    if math.isnan(y):
        return ("endpoint", f"{where} : {field} en x = {_n(bound)}, où la courbe n'est pas définie ; "
                            "un point plein ou creux s'y placerait au hasard.")
    if not (x0 <= bound <= x1 and y0 <= y <= y1):
        return ("endpoint", f"{where} : le point de {field} ({_n(bound)} ; {_n(y)}) est hors de la fenêtre.")
    return None


def _curve(curve: PlotCurve, plot: PlotBlock, where: str, pack: str | None) -> Refusal | None:
    node, refused = _compile(curve.expr, CURVE_VARIABLES, where)
    if node is None:
        return refused
    if refusal := _in_pack(node, True, pack, where):
        return refusal
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    a, b = curve.domain if curve.domain is not None else (x0, x1)
    if a >= b:
        return ("domain", f"{where} : domain va du plus petit au plus grand ({_n(a)} puis {_n(b)}).")
    lo, hi = max(a, x0), min(b, x1)
    if lo >= hi:
        return ("domain", f"{where} : domain [{_n(a)} ; {_n(b)}] est hors de la fenêtre (x de {_n(x0)} à {_n(x1)}).")

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


def _sequence(seq: PlotSequence, plot: PlotBlock, where: str, pack: str | None) -> Refusal | None:
    node, refused = _compile(seq.expr, SEQUENCE_VARIABLES, where)
    if node is None:
        return refused
    if refusal := _in_pack(node, False, pack, where):
        return refusal
    if seq.first > seq.last:
        return ("terms", f"{where} : first ({seq.first}) vient après last ({seq.last}).")
    if seq.last - seq.first + 1 > MAX_TERMS:
        return ("terms", f"{where} : {seq.last - seq.first + 1} termes ; {MAX_TERMS} au plus.")
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    if seq.first < x0 or seq.last > x1:
        return ("outside", f"{where} : n va de {seq.first} à {seq.last}, hors de x_range ({_n(x0)} à {_n(x1)}).")
    terms = [(n, evaluate(node, n)) for n in range(seq.first, seq.last + 1)]
    if all(math.isnan(u) for _, u in terms):
        return ("undefined", f"{where} : « {seq.expr} » n'est définie pour aucun n de {seq.first} à {seq.last}.")
    for n, u in terms:
        if not math.isnan(u) and not y0 <= u <= y1:
            return ("outside", f"{where} : le terme n = {n} ({_n(u)}) sort de la fenêtre (y de {_n(y0)} à {_n(y1)}) ; "
                               "élargis y_range ou arrête la suite plus tôt.")
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


def plot_refusal(plot: PlotBlock, path: str, pack: str | None = None) -> Refusal | None:
    """The first rule the plot breaks, as (rule, message), or None."""
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
        return ("empty", f"{where} : rien à tracer ; donne au moins une courbe, une suite, un point ou une ligne.")
    for i, curve in enumerate(plot.curves):
        if refusal := _curve(curve, plot, f"{where}, courbe {i + 1}", pack):
            return refusal
    for i, seq in enumerate(plot.sequences):
        if refusal := _sequence(seq, plot, f"{where}, suite {i + 1}", pack):
            return refusal
    (x0, x1), (y0, y1) = plot.x_range, plot.y_range
    for i, point in enumerate(plot.points):
        if not (x0 <= point.x <= x1 and y0 <= point.y <= y1):
            name = f" ({point.label})" if point.label else ""
            return ("outside", f"{where}, point {i + 1}{name} : ({_n(point.x)} ; {_n(point.y)}) est hors de la fenêtre.")
    for i, line in enumerate(plot.lines):
        if not _meets_window(line, plot):
            return ("outside", f"{where}, ligne {i + 1} : elle ne passe pas dans la fenêtre.")
    return None


def _texts(plot: PlotBlock) -> list[tuple[str, str]]:
    """Every text the model wrote on the plot, with where it sits, for the exercise rule."""
    layers: list[tuple[str, Sequence[Any]]] = [
        ("courbe", plot.curves), ("suite", plot.sequences), ("point", plot.points), ("ligne", plot.lines)]
    found = [("x_title", plot.x_title), ("y_title", plot.y_title)]
    found += [(f"{name} {i + 1}", item.label) for name, items in layers for i, item in enumerate(items) if item.label]
    if plot.caption:
        found.append(("caption", plot.caption))
    return found


def gives_away(text: str) -> bool:
    """An equation, an approximation, a mapping or a pair of numbers: what a text on
    an open exercise's drawing may not hold. Shared with scripts/probe.py."""
    return _GIVES_AWAY.search(_LATEX_SPACING.sub("", text).replace("−", "-")) is not None


def plots_refusal(plots: Sequence[tuple[str, PlotBlock]], exercise: bool = False,
                  pack: str | None = None) -> Refusal | None:
    """The first rule a card's plots break, the per-card limit included.

    An exercise's drawing is on the board while the exercise is open, so it may not
    write coordinates, draw reading guides, or give an equation or coordinates in any
    of its texts: the one place the tool can tell (R5.1 of spec 008, for plots).
    Elsewhere the prompt carries the rule."""
    if exercise:
        for path, plot in plots:
            for i, point in enumerate(plot.points):
                if point.show_values or point.guides:
                    return ("exercise_values",
                            f"Le graphique {path}, point {i + 1} accompagne un exercice ouvert : ni show_values ni "
                            "guides, sinon il montre la réponse. Ils viendront avec la correction.")
            for field, text in _texts(plot):
                if gives_away(text):
                    return ("exercise_text",
                            f"Le graphique {path}, {field} : « {text} » donne une équation, une valeur ou des "
                            "coordonnées ; sur un exercice ouvert, une étiquette est un nom ($f$, $A$) et un titre "
                            "une grandeur. Les données vont dans l'énoncé.")
    if len(plots) > MAX_PLOTS_PER_CARD:
        return ("per_card", f"Une carte porte au plus {MAX_PLOTS_PER_CARD} graphiques de fonctions ; "
                            "répartis les autres sur une carte suivante.")
    for path, plot in plots:
        if refusal := plot_refusal(plot, path, pack):
            return refusal
    return None


def plot_summary(plots: Sequence[tuple[str, PlotBlock]]) -> dict[str, Any]:
    """What `plot_displayed` logs: layer counts and function names from the closed
    set, never an expression, a label or a number. Runs after plots_refusal passed,
    so every expression parses."""
    layers = {"curves": 0, "sequences": 0, "points": 0, "lines": 0}
    names: set[str] = set()
    for _, plot in plots:
        for layer in layers:
            layers[layer] += len(getattr(plot, layer))
        names |= {n for c in plot.curves for n in functions(parse(c.expr, CURVE_VARIABLES))}
        names |= {n for s in plot.sequences for n in functions(parse(s.expr, SEQUENCE_VARIABLES), powers=False)}
    return {"layers": layers, "functions": sorted(names)}
```

Checked in the prototype against the critique's cases:
- **Pole windows:** `1/x` in [−1,1 ; 1]×[−0,5 ; 0,5] is now `outside`, as is `tan(x)` in [1,4 ; 1,8]×[−0,1 ; 0,1]. The steep lines 1000(x−0,0123) and 100000(x−0,01234) in y ∈ [−1 ; 1] are accepted.
- **Graduation float noise:** step 0,01 on [−4,9 ; −4,6] (30,000000000000007 intervals) is accepted; 31 intervals are refused.
- **Graduation decimals:** steps of 0,00005 and 1/3 are refused (`step`).
- **Window size:** [0 ; 1e-200] and [0 ; 1e7] are refused (`window`).
- **Sequence out of window:** 2 + 3(n − 1) up to n = 7 in y ∈ [0 ; 15] is refused, and the message names n = 6.
- **Hidden exponentials:** `e^x` and `2^x` are refused against the chapter 1 pack, while `3*0.5^(n-1)` as a sequence passes. `exp(x)` with `$\mathrm{e}^{x}$` or `{e}^{x}` in the pack passes.
- **Exercise caption:** « La droite $y = 2x+1$ » on an exercise caption is refused (`exercise_text`).

The per-curve bisection costs at most 400 × 40 evaluations, about 45 ms, and only on pathological inputs.

## 4. Rendering: `frontend/src/components/celestin/plot/`

### 4.1 Files

| File | Contents |
|---|---|
| `expression.ts` | `parseExpression(source, variables): Parsed` (never throws), `evaluate(node, v)` (NaN where undefined), `compileExpression(source: unknown, variables)` → `((v) => number) \| null`, `CURVE_VARIABLES`, `SEQUENCE_VARIABLES`, `ExprErrorCode`. It mirrors `app/domain/expression.py` (source below). It does not tag constants, because the browser only draws. |
| `sanitise.ts` | `sanitise(block): CleanPlot`. It is total over any JSON and runs once at the edge; everything after it assumes clean data. |
| `ticks.ts` | `axisAt`, `decimalsOf`, `autoStep`, `stepTicks`, `labelEvery`. |
| `sample.ts` | `sampleCurve`, `clipBand`, `clipLine`, `sequenceDots`, `endpointValue`. Pure, in data units. |
| `groups.ts` | `colourGroups(plot)`: the colour key for piecewise curves. |
| `labels.ts` | `plainText`, `labelSize`, `coordinates(x, y)`, `Occupancy` (grid), `placeLabels`. |
| `layout.ts` | `layout(plot: CleanPlot, width): Scene`. Every geometric decision lives here, so it is tested without a DOM. |
| `describe.ts` | `ariaLabel(plot)`, `describe(plot, scene)`. |
| `plot-view.tsx` | `PlotView({ block })` (memo), `InlineRich`. |
| `__tests__/` | `expression_cases.json` (copy of the backend fixture), `expression.test.ts`, `ticks.test.ts`, `sample.test.ts`, `groups.test.ts`, `labels.test.ts`, `layout.test.ts`, `describe.test.ts`, `plot-view.test.tsx`, `fixtures.ts` (`PLOTS … satisfies Record<string, PlotBlock>`). |

> **As built.** `coordinates` is gone from `labels.ts`: a point's coordinates are written by
> `formatPair` in `charts/format.ts`, shared with figures (verification #17). `expression.ts`
> exports `MAX_DEPTH` (24) and `MAX_EXPRESSION` (120).

Reused read-only:
- from `../charts/`: `formatNumber` (decimal comma, true minus, a space from five digits, at most 4 decimals, which the tool rules guarantee is enough), `niceTicks` and `linear`, `useWidth`, `FONT` and `textWidth`;
- from `../board-blocks`: `RichText` (caption only) and `splitInlineMath`, a circular import that is safe at render time, as in chart-view;
- `Math` from `../math`.

### 4.2 `expression.ts`

The prototype: 96 cases, 0 disagreements with Python; passes `tsc` with the repo's strict flags.

```ts
export type ExprNode =
  | { k: "num"; v: number }
  | { k: "var" }
  | { k: "neg"; a: ExprNode }
  | { k: "bin"; op: "+" | "-" | "*" | "/" | "^"; a: ExprNode; b: ExprNode }
  | { k: "call"; f: FunctionName; a: ExprNode };
export type ExprErrorCode = "syntax" | "unknown_name" | "latex" | "comma" | "equation"
  | "scientific" | "ambiguous" | "variables" | "depth";
export type Parsed = { ok: true; node: ExprNode } | { ok: false; code: ExprErrorCode };

const FUNCTIONS = { sqrt: Math.sqrt, cbrt: Math.cbrt, abs: Math.abs, exp: Math.exp, ln: Math.log,
  log: Math.log10, sin: Math.sin, cos: Math.cos, tan: Math.tan } as const;
type FunctionName = keyof typeof FUNCTIONS;
const CONSTANTS: Record<string, number> = { pi: Math.PI, "π": Math.PI, e: Math.E };
export const CURVE_VARIABLES: readonly string[] = ["x", "t"];
export const SEQUENCE_VARIABLES: readonly string[] = ["n"];
const MAX_DEPTH = 24;
const ALIASES: Record<string, string> = { "−": "-", "·": "*", "×": "*", "⋅": "*" };
const SPACES = " \t\n\r  ";
const isDigit = (c: string | undefined) => c !== undefined && c.length === 1 && c >= "0" && c <= "9";
const isLetter = (c: string | undefined) => c !== undefined && /^[A-Za-z]$/.test(c);
// Own properties only: `"toString" in FUNCTIONS` is true through the prototype.
const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);

class Refused extends Error {
  code: ExprErrorCode;
  constructor(code: ExprErrorCode) { super(code); this.code = code; } // erasable syntax only
}
type Token = { kind: "num" | "name" | "op" | "end"; text: string };

function tokens(src: string): Token[] {
  const out: Token[] = [];
  let i = 0;
  while (i < src.length) {
    const raw = src[i] as string;
    const c = own(ALIASES, raw) ? (ALIASES[raw] as string) : raw;
    if (SPACES.includes(c)) i += 1;
    else if (isDigit(c)) {
      let j = i;
      while (isDigit(src[j])) j += 1;
      if (src[j] === ".") {
        if (!isDigit(src[j + 1])) throw new Refused("syntax");
        j += 1;
        while (isDigit(src[j])) j += 1;
      }
      // 1e-3, 6.67e-11, 2E5: scientific notation would otherwise read as 1·e − 3.
      if ((src[j] === "e" || src[j] === "E") &&
          (isDigit(src[j + 1]) || (["+", "-", "−"].includes(src[j + 1] ?? "") && isDigit(src[j + 2]))))
        throw new Refused("scientific");
      out.push({ kind: "num", text: src.slice(i, j) });
      i = j;
    } else if (c === "π") { out.push({ kind: "name", text: c }); i += 1; }
    else if (isLetter(c)) {
      let j = i + 1;
      while (isLetter(src[j])) j += 1;
      out.push({ kind: "name", text: src.slice(i, j) });
      i = j;
    } else if ("+-*/^()".includes(c)) { out.push({ kind: "op", text: c }); i += 1; }
    else if ("\\${}".includes(c)) throw new Refused("latex");
    else if (c === ",") throw new Refused("comma");
    else if (c === "=") throw new Refused("equation");
    else throw new Refused("syntax"); // |, ², ³, anything else
  }
  out.push({ kind: "end", text: "" });
  return out;
}

export function parseExpression(source: string, variables: readonly string[]): Parsed {
  try {
    const ts = tokens(source);
    let i = 0, depth = 0;
    let seen: string | null = null;
    const peek = () => ts[i] as Token;
    const isOp = (s: string) => peek().kind === "op" && s.includes(peek().text);
    const enter = () => { depth += 1; if (depth > MAX_DEPTH) throw new Refused("depth"); };
    const close = () => { if (!isOp(")")) throw new Refused("syntax"); i += 1; };
    const sum = (): ExprNode => {
      let node = prod();
      while (isOp("+-")) { const op = (ts[i++] as Token).text as "+" | "-"; node = { k: "bin", op, a: node, b: prod() }; }
      return node;
    };
    const prod = (): ExprNode => {
      let node = unary(); let afterDivision = false;
      for (;;) {
        const t = peek();
        if (isOp("*/")) { i += 1; node = { k: "bin", op: t.text as "*" | "/", a: node, b: unary() }; afterDivision = t.text === "/"; }
        else if (t.kind === "name" || isOp("(")) {
          if (afterDivision) throw new Refused("ambiguous");
          node = { k: "bin", op: "*", a: node, b: power() };
        } else return node;
      }
    };
    const unary = (): ExprNode => {
      if (!isOp("+-")) return power();
      const op = (ts[i++] as Token).text; enter(); const a = unary(); depth -= 1;
      return op === "-" ? { k: "neg", a } : a;
    };
    const power = (): ExprNode => {
      const base = atom();
      if (!isOp("^")) return base;
      i += 1; enter(); const b = unary(); depth -= 1;
      return { k: "bin", op: "^", a: base, b };
    };
    const atom = (): ExprNode => {
      const t = peek();
      if (t.kind === "num") { i += 1; return { k: "num", v: Number(t.text) }; }
      if (isOp("(")) { i += 1; enter(); const a = sum(); depth -= 1; close(); return a; }
      if (t.kind !== "name") throw new Refused("syntax");
      i += 1;
      if (own(FUNCTIONS, t.text)) {
        if (!isOp("(")) throw new Refused("syntax");
        i += 1; enter(); const a = sum(); depth -= 1; close();
        return { k: "call", f: t.text as FunctionName, a };
      }
      if (own(CONSTANTS, t.text)) return { k: "num", v: CONSTANTS[t.text] as number };
      if (variables.includes(t.text)) {
        if (seen !== null && seen !== t.text) throw new Refused("variables");
        seen = t.text; return { k: "var" };
      }
      throw new Refused("unknown_name");
    };
    if (peek().kind === "end") throw new Refused("syntax");
    const node = sum();
    if (peek().kind !== "end") throw new Refused("syntax");
    return { ok: true, node };
  } catch (error) {
    if (error instanceof Refused) return { ok: false, code: error.code };
    return { ok: false, code: "syntax" }; // never throw into React
  }
}

const fin = (v: number) => (Number.isFinite(v) ? v : NaN);
export function evaluate(node: ExprNode, v: number): number {
  switch (node.k) {
    case "num": return node.v;
    case "var": return v;
    case "neg": return -evaluate(node.a, v);
    case "call": { const a = evaluate(node.a, v); return Number.isNaN(a) ? NaN : fin(FUNCTIONS[node.f](a)); }
    case "bin": {
      const a = evaluate(node.a, v), b = evaluate(node.b, v);
      if (Number.isNaN(a) || Number.isNaN(b)) return NaN;
      switch (node.op) {
        case "+": return fin(a + b);
        case "-": return fin(a - b);
        case "*": return fin(a * b);
        case "/": return b === 0 ? NaN : fin(a / b);
        case "^": return fin(Math.pow(a, b));
      }
    }
  }
}

export function compileExpression(source: unknown, variables: readonly string[]) {
  if (typeof source !== "string") return null;
  const parsed = parseExpression(source, variables);
  return parsed.ok ? (v: number) => evaluate(parsed.node, v) : null;
}
```

### 4.3 `sanitise.ts`

Malformed stored data; never throws.

- **Ranges.** `x_range` and `y_range` must be arrays of 2 finite numbers. They are sorted; the pair falls back to [−10 ; 10] when a bound exceeds 1e6 or the span is < 1e-3. These are the tool's `window` limits, so niceTicks never sees a 1e-200 span and `toFixed` never throws.
- **Steps.** `x_step` and `y_step` are kept when finite, > 0, with at most 4 decimals (the same test as the tool) and span/step ≤ 60. Otherwise they become null, which means automatic ticks.
- **`orthonormal`.** Kept only when `=== true` and the aspect is within [0,4 ; 2]; otherwise false.
- **`curves`.** Keep the first 6 and compile each with `CURVE_VARIABLES`. A curve that fails to compile is dropped. `domain` must be a finite pair, sorted, otherwise null. Dots outside the enum become "none". `dashed` is `=== true`.
- **`sequences`.** Keep the first 3 and compile each with `SEQUENCE_VARIABLES`. `first` and `last` are truncated with `Math.trunc` and must be finite and ≥ 0 (`first` defaults to 1). A sequence with last < first is dropped, and `last` is capped at first + 59.
- **`points`.** Keep the first 20. A point needs finite x and y. `mark` outside the enum becomes "filled".
- **`lines`.** Keep the first 8. Keep only finite pair vertices, at most 30; a line with fewer than 2 is dropped.
- **Labels, titles, caption.** Strings, trimmed; a label is cut to 40 characters (stored data may predate the 24 limit), and an empty label becomes null.
- **`CleanPlot`.** The same shape with every field present, plus `f` on each curve and sequence.

### 4.4 `ticks.ts`

Prototyped at 280 px.

- **`axisAt(min, max)`.** Returns `{ at, arrow }`. When min ≤ 0 ≤ max, it is `{ at: 0, arrow: true }`. Otherwise `at` is the bound nearest 0, with `arrow: false`: an axis on an edge because 0 is outside the window is drawn as a graduated frame edge, with no arrow and no origin « 0 ».
  - Physics windows starting at 0 keep their arrowed axes on the left and bottom edges, through the origin.
- **`autoStep(min, max, lengthPx, integer)`.** Gives `niceTicks(min, max, clamp(round(lengthPx/56), 2, 10))`'s step, cleaned with `Number(step.toPrecision(12))`. When `integer` is set (the plot has sequences and x is n), the result is max(1, step); niceTicks steps ≥ 1 are already integers.
- **`decimalsOf(step)`.** The smallest d ≤ 10 with |round(step·10ᵈ) − step·10ᵈ| < 1e-9·max(1, step·10ᵈ).
- **`stepTicks(min, max, step)`.** For k from ⌈min/step − 1e-9⌉ to ⌊max/step + 1e-9⌋, gives `Number((k*step).toFixed(decimalsOf(step)))`.
- **`labelEvery(step, spacingPx, needPx)`.** Critique fix: labels thin repeatedly, not just once.
  1. need = ceil(needPx / spacingPx).
  2. If need is 1, the result is 1.
  3. Otherwise, return the first k in [need ; 2·need] such that k·step is a whole multiple 1, 2 or 5 × 10ᵐ.
  4. If none, return need.
  - A tick gets a label iff round(t/step) % k === 0, so labels are anchored at 0.
  - Every tick keeps its tick mark and grid line.
  - needPx is widest label + 6 on x and 16 on y (12 px text).

Prototype output at 280 px:

| window and step | labels written |
|---|---|
| [−1,5 ; 1,5] step 0,1 (31 ticks, 9,3 px apart) | every 5th: −1,5 −1 −0,5 0 0,5 1 1,5 |
| [−10 ; 10] step 1 | every 2nd |
| [−4,9 ; −4,6] step 0,01 | every 5th: −4,9 −4,85 … |
| [0 ; 12500] step 2000 | 0 4000 8000 12 000 |
| [−5 ; 5] step 0,3 | every 4th: −4,8 … 4,8 |

- **Labels** are `formatNumber(t)`.

### 4.5 `sample.ts`

The TS prototype was run; results below.

`sampleCurve(f, from, to, win, plotW, plotH, budget = 20_000): { runs: Run[]; calls: number }`

1. a = max(from, x0), b = min(to, x1). If !(b > a), return [].
2. n = clamp(⌈(b−a)/(x1−x0)·plotW/2⌉, 8, 800). xᵢ = a + (b−a)i/n, with xₙ = b exactly.
3. For each pair of neighbouring samples, run `refine(xa, ya, xb, yb, depth)`, with pyScale = plotH/(y1−y0):
   - both NaN → break the current piece;
   - both finite and beyond the same edge → break;
   - both finite and |Δy|·pyScale ≤ 3 px, or the budget is spent → segment;
   - both finite at depth 12 → keep the segment only if |Δ|·pyScale ≤ plotH and f(mid) is finite and between ya and yb; otherwise break (a pole or a jump);
   - exactly one finite, at depth 12 or with the budget spent → break;
   - otherwise → bisect.
   - `segment` pushes its first end when the piece is empty.
4. `clipBand(piece, y0, y1)`: for each segment, compute parametric t0/t1 against y0/y1. The run continues only when the previous segment ended unclipped (t1 = 1) and this one starts at t0 = 0; the test compares t values, never coordinates. Runs with fewer than 2 vertices are dropped.

Prototype results at 280×210 px:

| curve and window | runs | calls |
|---|---|---|
| 1/x on [−5 ; 5]² | 2, (−5 ; −0,2)→(−0,2 ; −5) and (0,2 ; 5)→(5 ; 0,2) | 229 |
| x²−4, y ≤ 8 | 1, from x = −3,4641 to 3,4641 | 251 |
| sqrt | 1, starts at (0 ; 0) | 161 |
| ln | 1, starts on the bottom edge at x = 0,0498 | 185 |
| tan | 5 | 435 |
| steep line 1000(x−0,0123) | 1 | 266 |
| sin(1/x) | 174 | 8 911 (under budget) |
| abs(x)/x | 2 | 165 |
| v(t) pieces 2t / 10 / 10−2,5(t−12) | 1 each: (0;0)→(5;10), (5;10)→(12;10), (12;10)→(16;0) | 89 / 63 / 71 |
| 1/x in [−1,1 ; 1]×[−0,5 ; 0,5] | 0 (the tool refuses it too) | 154 |
| cbrt on [−8 ; 8] | 1 | 163 |

Other helpers:
- **`endpointValue(f, bound, inward, span, dot)`**: "filled" gives f(bound) or null. "hollow" gives f(bound), or else f(bound + inward·1e-9·span), or null (the tool's `INSIDE`). The dot is drawn only if it lies inside the window.
- **`sequenceDots(f, first, last, win)`**: isolated points (n ; u) with u finite and inside the window; never joined.
- **`clipLine(vertices, win)`**: Liang–Barsky per segment; consecutive visible segments that share an unclipped end stay one run.

### 4.6 `groups.ts`: the colour key

A critique fix for piecewise graphs.

`colourGroups(plot)` walks solid curves, then sequences, then solid lines, in declared order. Group key: `label.trim()`, or "" when there is no label.
- Groups are numbered in order of first appearance, and group g gets `SERIES[g % 6]`, with `SERIES = [1, 4, 2, 5, 6, 8].map(i => \`var(--chart-${i})\`)`. chart-3 and chart-7 are left out: they are below 3:1 on white.
- Dashed curves and lines get `var(--muted-foreground)` and are not grouped.
- Result: the three unlabelled v(t) pieces share one colour, and pieces all labelled `$f$` share one colour and one label box. Two unlabelled distinct functions also share a colour; the prompt tells Célestin to label them.
- Contrast on white: foreground 15,5:1, muted-foreground 5,27:1, the series 3,54 to 5,72:1. All clear the 3:1 needed for graphics.

### 4.7 `layout.ts`: sizing at 400 px

- **Width.** W is the measured content width from `useWidth` (fallback 560 in jsdom); on a 400 px board it is about 300 to 330 px.
- **Height.** When not orthonormal, H = round(clamp(0,75·W, 240, 420)).
- **Frame, pass 1.** top = 24 (the band for the y title and the arrow tip), right = W − 16, left = 10, bottom = H − 10. Axis positions come from `axisAt`, ticks from `x_step ?? autoStep(…, plotW, sequences present)` and `y_step ?? autoStep(…, plotH, false)`.
- **Frame, pass 2.**
  - When the y axis is on the left edge, left = widest y label + 10.
  - When the x axis is on the bottom edge, the frame bottom is raised by 18 px for the x labels.
  - An axis inside the plot keeps its labels inside, with a halo (`stroke-card`, width 3, `paint-order: stroke`).
- **Orthonormal.**
  1. unit = min(plotW/xspan, 480/yspan).
  2. plotH = unit·yspan and plotW' = unit·xspan, with the frame centred horizontally.
  3. H = top + plotH + bottom margins, with plotH at least 100.
  - The tool's aspect rule [0,4 ; 2] keeps this between 110 and 480 px tall at 400 px.
- **Tick labels.**
  - x labels sit 12 px below the x axis; y labels are right-aligned 6 px left of the y axis.

    > **As built.** The x labels' baseline sits 16 px under the axis (`X_LABEL_DY`), not 12
    > (§7, item 15).

  - Thinning follows `labelEvery`.
  - When both axes pass through 0 with arrows, the 0 labels are skipped and a single « 0 » goes below-left of the origin.
- **Tick marks and grid.** Every tick gets a 4 px tick mark across its axis (`stroke-muted-foreground`), whether or not `grid` is set. With `grid`, lines at every tick in `stroke-border`, 1 px.
- **Axes.**
  - `stroke-muted-foreground`, 1,25 px.
  - With `arrow`, the axis extends 10 px past the frame and ends in a 6×4 filled triangle drawn as a plain path. There are no `<marker>`, `clipPath` or ids, so plots never collide on one page.

    > **As built.** The head is a 7 × 7 px triangle (7 long, ±3,5 across), not 6 × 4 (§7, item 14).

- **Marks.**
  - Curves: 2,25 px, round joins, in their group colour.
  - Dashed layers: 1,5 px `stroke-muted-foreground`, dasharray "6 4".
  - Sequence dots: r 3,5.
  - Endpoint dots: r 4, either filled in the group colour or hollow (`fill-card`, 2 px group stroke).
  - Points, in `foreground`: filled r 4, hollow r 4, or a cross of two ±4,5 px lines.
  - Guides: dashed "3 3" muted lines from the point to each axis.
  - Feet values (`guides` and `show_values` together): `formatNumber` of x below the x axis and of y left of the y axis, 12 px semibold with a halo. Tick labels within 16 px of a foot are dropped.
  - `show_values` without guides appends `coordinates(x, y)` = « (2 ; −1,5) » to the point's label.
- **Occupancy.** A `Uint8Array` grid of 4 px cells marks:
  - every curve and line vertex, with lines densified every 6 px;
  - dots and points;
  - both axis lines;
  - tick label boxes and feet boxes.
- **Titles (critique fix).**
  - **y title.** In the top band, outside the frame: left = yAxisX + 8 when it fits, otherwise right-aligned at yAxisX − 8, and clamped to [0, W].
  - **x title, candidate A.** Right-aligned at the arrow tip, its bottom 4 px above the x axis, inside the plot. It is used only if the x axis is not on the top edge and the box covers no occupied cell.
  - **x title, candidate B.** A band below the frame: right-aligned at frame.right, 4 px below the x tick labels when the axis is on the bottom edge, or 6 px below frame.bottom otherwise. H grows by 22 px. This candidate is always free.
  - The motion fixture, whose last piece ends at (16 ; 0) under candidate A, takes candidate B.
  - Both titles then mark the occupancy grid.
- **Labels.** `placeLabels` places point labels first, then one label per labelled colour group (curves, lines and sequences together), then dashed layers.
  - Candidates:
    - a point: its own position;
    - a group: its visible vertices in x order at 85, 70, 55, 40, 25 and 95 % of the list, then a sequence's last and first dots.
  - Each candidate is tried with the anchors ne, nw, se, sw, at a 6 px gap.
  - A box is accepted if it lies inside [0, W]×[0, H], overlaps no taken box (2 px padding) and covers no occupied cell.
  - The fallback is the first candidate's ne box, clamped into the area.
  - `labelSize`: height 20; width 4 + prose characters × 7,8 + `plainText` maths characters × 9,5 + coordinate characters × 7,8. With 24-character labels the widest is about 230 px, which fits at 300.
- **`drawable`.** True when at least one curve run, sequence dot, point or line run is visible.

`Scene` = { width, height, frame, xAxis {y, arrow, ticks: {at, label|null}[]}, yAxis {x, arrow, ticks}, origin, grid, runs: {points: string, colour, dashed}[], dots, endpoints, marks, guides, feet, titles, labels: {left, top, text, coords?, swatch: string|null, dashed: boolean}[], drawable }. Pixel coordinates are rounded to 0,1.

### 4.8 Maths labels: an HTML overlay over the SVG (no foreignObject)

Every string the model writes (titles, labels, caption) is typeset by KaTeX with `trust: false`. Labels and titles are absolutely positioned spans in a `position: relative` wrapper; the SVG holds only numbers we format.

Why not foreignObject:
1. Plots draw at the measured pixel width, not in a scaled viewBox, so a span aligns exactly.
2. KaTeX inside `<foreignObject>` needs a box size before rendering, and WebKit misplaces positioned or transformed content inside it.
3. It reuses the board's single path for model text.
4. Charts' D10 does not recur.

`InlineRich({ text })` maps `splitInlineMath(text)` to `<Math tex block={false} />` for maths parts and `<span>` for prose, so `$$…$$` in a label renders inline, never as a display block (critique fix).

Label span classes: `absolute whitespace-nowrap rounded-sm bg-card/85 px-0.5 text-sm leading-5 text-foreground`, with `style={{ left, top, maxWidth: width }}` and, for a group label, `borderBottom: 2px solid <group colour>` (dashed layers: `2px dashed var(--muted-foreground)`).

> **As built.** Label and title spans carry no `maxWidth`: their box is computed from
> `labelSize`, and a right-anchored one is positioned with CSS `right` (§7, item 16).

- The text is always foreground; only the underline carries the series colour (critique fix for contrast).
- Titles use `text-xs font-semibold text-muted-foreground`.
- All style values are ours: computed boxes and palette variables.

### 4.9 `plot-view.tsx`

```tsx
export const PlotView = memo(function PlotView({ block }: { block: PlotBlock }) {
  const ref = useRef<HTMLDivElement>(null);
  const width = useWidth(ref);
  const plot = useMemo(() => sanitise(block), [block]);
  const scene = useMemo(() => layout(plot, width), [plot, width]);
  return (
    <figure className="rounded-lg border border-border bg-card px-5 py-4">
      <div ref={ref} role="img" aria-label={ariaLabel(plot)} className="relative">
        <svg width={width} height={scene.height} aria-hidden="true" className="block overflow-visible">
          {/* grid, tick marks, axes (+ arrows), tick labels, dashed layers, solid runs, dots, marks, guides, feet */}
        </svg>
        <div aria-hidden="true">{/* scene.titles + scene.labels → <span …><InlineRich text=… />{coords}</span> */}</div>
      </div>
      {!scene.drawable && <p className="mt-2 text-center text-sm text-muted-foreground">Graphique vide</p>}
      {plot.caption && (
        <figcaption className="mt-3 text-center text-xs text-muted-foreground"><RichText text={plot.caption} /></figcaption>
      )}
      <p className="sr-only">{describe(plot, scene)}</p>
    </figure>
  );
});
```

There are no pointer handlers, no `<title>`, no tooltips and no hover states. Sampling reruns only when the block or the width changes.

### 4.10 Accessibility

A critique fix: no hidden answers in DOM text.

- **aria-label:** « Graphique : {plain(y_title)} en fonction de {plain(x_title)} ».
- **`plainText`:** strips `$`, turns `_a` / `_{ab}` into « indice a », `^a` into « exposant a », and drops the other `\commands` and braces. So `$u_n$` becomes « u indice n », `$\mathcal{C}_f$` becomes « C indice f », and `$v$ (m/s)` becomes « v (m/s) ».
- **`describe`:** only what is drawn as visible text or shape. Example:
  - « Repère orthonormé. » when set;
  - « Axe horizontal t (s), de 0 à 16, gradué de 2 en 2. Axe vertical v (m/s), de 0 à 12, gradué de 2 en 2. »;
  - per colour group: « Courbe f. », « Courbe f, en 2 morceaux. » or « Une courbe en 3 morceaux. »;
  - « Suite u indice n, en points isolés. »;
  - « Point S. », or « Point S (0 ; −4). » only with show_values;
  - « Ligne brisée. »;
  - « 1 tracé en pointillés. »
- **Never in the description:** an expression, a domain or its brackets, the position or kind of an endpoint dot, a sequence's n range, a line's vertices, or a point's coordinates without `show_values`. `PlotView` cannot tell whether it sits on an open exercise, so it assumes it might.

### 4.11 Animation

Each solid run is its own `<polyline pathLength={1} className="chart-trace">`: the existing utility, off under `prefers-reduced-motion`. Dashed layers, dots, marks and labels are static. No new CSS.

### 4.12 Defensive handling

- `sanitise` is total, `parseExpression` and `evaluate` never throw, and `layout` sees only finite numbers inside the tool's limits.
- A stored plot with a bad expression, a reversed or absurd range, a NaN point, a one-vertex line or a non-array `curves` draws what is valid. When nothing is left it shows « Graphique vide ».
- No error boundary is needed for the plot. The general one for drawings stays charts' deferred #13.

## 5. Withholding and the pack

### 5.1 What the tool enforces

It enforces only on an `exercise` card's `drawing`, the one place the tool knows an exercise is open (the charts precedent, D12):

1. **`exercise_values`**: no point with `show_values` (written coordinates) or `guides` (reading lines to the axes). Both are what a « lis sur le graphique » exercise asks for, so they belong to the correction.
2. **`exercise_text`**: no text holding an equation (`=`), an approximation (≈, `\approx`), a mapping (↦, `\mapsto`) or a pair of numbers `(a ; b)` / `(a, b)`. This covers the axis titles, every curve, sequence, point and line label, and the caption, after LaTeX spacing is stripped. It catches:
   - `$y = 2x+1$` in the caption of « détermine l'équation de la droite »;
   - `$x = 1$` on an asymptote question;
   - `$S(1\,;\,-4)$` on « trouve le sommet »;
   - `$x_0 \approx 1{,}4$` on « lis la racine ».

   The fix costs one rewrite: the data goes in the statement.
3. **By construction, in the frontend.** The expression, domains, endpoint kinds and positions, the sequence's n range and line vertices never become DOM text. Coordinates appear only with `show_values`. The data still reaches the browser inside `board.set`, as charts' data and a check question's `correct_option_id` already do (D6).

### 5.2 What stays prompt text (measured by the probe)

- No point on the sought root, vertex, intersection or read value.
- No plot of the function the student must draw while the exercise is open (the existing « Un graphique ne donne pas la réponse… » bullet).
- No new explanation carrying the answer while an exercise is open (the general rule).
- Worked examples and explanations may show everything.

### 5.3 Pack restriction: mechanical vs prompt

**Tool, `pack_function`.** A curve or sequence using exp, ln, log, cbrt, sin, cos or tan is refused when `ctx.pack` contains none of that function's `PACK_WORDS` (case-insensitive; LaTeX `\ln`, `\sin`, `\mathrm{e}^x`, `{e}^{x}` and `\sqrt[3]{x}` all match).
- Evasion is closed: `e` is a tagged constant, and a power whose exponent holds the variable counts as `exp` on a curve. So `e^x` and `2^x` are refused like `exp(x)`, while a geometric sequence's `0.5^(n-1)` is not.
- A false acceptance (« tangente » in a derivatives pack) is harmless.

> **As built (verification #4).** Not harmless after all: a chapter that merely mentioned a
> tangent line let Célestin plot `tan(x)`, and « une croissance exponentielle » let him plot `e^x`.
> Each `PACK_WORDS` entry now matches the course naming the *function*: `\tan`, `tg`,
> « fonction tangente », the tangent of an angle, « sinus, cosinus et tangente », never the
> tangent line; `\exp`, `exp(`, « fonction exponentielle », « exponentielle de base … », the
> noun, and e raised to a power (lower-case e only, not the electron `e^-`), never the
> adjective; `\ln` or « logarithme népérien / naturel / de base e », never a bare
> « logarithme »; `\log` or « logarithme décimal / de base 10 »; « racine cubique »,
> `\sqrt[3]`, ∛; `\sin`, `\cos`, « sinus », « cosinus » (the sine of an angle is the function,
> and « sinusoïdal » names its graph), with a word boundary so « cosinus » does not name sin.
> A table of 44 pack sentences pins every entry both ways.
>
> **Known limit (verification #16).** `pack_function` reads expressions only. A function the
> pack never names can still be drawn from values computed elsewhere, as points or a broken
> line through them; nothing mechanical can tell those from measurements. Only the prompt's
> general rule covers it, and the plot probe measures it (`_traced` in `scripts/probe.py`).

- sqrt and abs are not checked.
- The precedent is the definition check that already reads `ctx.pack`. The check is skipped without a pack.

**Prompt plus probe.** These cannot be checked mechanically without refusing legitimate plots:
- a sequence drawn as isolated points rather than a continuous curve;
- the course's own graphs (x(t), v(t)), axis units, curve names and orthonormal use;
- the filled or hollow dot conventions;
- one label per function across its pieces.

### 5.4 Probe set `scripts/probe.py --plots`

The lead owns probe.py.

A `PlotProbe` extends `ChartProbe` with a `chapter` path; each probe runs in both modes. Probes 1 to 5 use chapter 1 (`courses/chapitre_1`, section ids from its curriculum). Probes 6 and 7 use the new `tests/fixtures/chapters/mru/` (hand-written from `tests/fixtures/material/physics_mru.txt`, which carries the lab table t = 0…2 s, x = 0…48 cm and exercise 4 « Lis la vitesse de la bille sur le graphique », answer 24 cm/s).

1. **« Graphique d'une SA »**, section `sa-proprietes`: « Montre-moi le graphique de la suite arithmétique de premier terme 2 et de raison 3. » Flag `sequence` when:
   - there is no plot;
   - there is no `sequences` layer;
   - `first` = 0;
   - a solid curve's expr equals the term with n replaced by x.
2. **« Lecture d'un terme »**, section `sa-applications`: « Pose-moi un exercice où je lis un terme d'une suite sur son graphique. » Flag `reading` when the open exercise has:
   - a point with show_values or guides;
   - any text where `gives_away(text)` is true (imported from `services/tools/plots.py`);
   - a `PlotPoint` on one of the drawn sequence's dots.
3. **« Construis le graphique »**, section `sa-applications`: « Donne-moi un exercice où je dois représenter les 5 premiers termes de uₙ = 2n − 1. » Flag `build`: the exercise's drawing carries a sequence, curve or points while open.
4. **« Fonction hors du cours »**, section `sa-proprietes`: « Trace-moi le graphique de ln(x) pour voir. » Flag `pack`: a plot on the final cards uses a function whose `PACK_WORDS` are absent (via `functions()`). It measures what the model does after the refusal.
5. **« Suite en vagues »**, section `sg-definition`: « Montre-moi le graphique de la suite de premier terme 1 et de raison −2. » Flag `sequence`, plus at least 3 terms drawn.
6. **Physics, « Graphique de l'expérience »**: « Montre-moi le graphique x(t) de l'expérience de la bille. » Flag `data` when:
   - no points or line vertices equal the course's data (0 ; 0) … (2 ; 48) within 1e-6;
   - or `x_title` lacks « s » or `y_title` lacks « cm ».
7. **Physics, « Lecture de la vitesse »**: « Pose-moi un exercice où je lis la vitesse de la bille sur son graphique x(t). » Flag `reading`, as in 2, plus « 24 » in any plot text.

`plot_flags(cards, flag, pack)` reads plots through `card_blocks(card)` and `isinstance(block, PlotBlock)`, as `chart_flags` does. It returns French flag strings; an empty list is a pass. Results go under « Probe runs » with rates per mode.

> **As built.** Probes 6 and 7 run on `tests/fixtures/chapters/mru/`. The runs are recorded
> in `README.md`.

## 6. Risks and decisions

### 6.1 Decisions the lead must confirm

1. **Callable discriminator on `drawing`.** It keeps today's behaviour, where a chart drawing without `type` validates, and it shrinks the schema by 232 characters. The cost is a small function in board.py. Flowchart and figure must use the same `Drawing` definition, so the lead picks one pattern for all four blocks.

   > **As built.** Adopted for all four blocks (`Drawing` and `_drawing_type` in
   > `app/domain/board.py`); a missing `type` is read from the drawing's keys first.

2. **Implicit multiplication is on**, before a name or "(" only. `1/2x` is refused as ambiguous, and scientific notation is refused rather than guessed. The alternative, explicit `*` only, costs many correction round trips.
3. **Decimals use a dot in `expr` only.** A comma is refused with a targeted message. The expression is never displayed; every displayed number goes through `formatNumber`.
4. **Undefined anywhere means undefined everywhere, on both sides.** So 1/(1/x) is undefined at 0, x^(1/3) is NaN for x < 0 (use `cbrt`, now in the grammar), and 0^0 = 1.
5. **Trigonometry is in radians** (stated in the schema). There are no π-graduated axes and no degree-based trig graphs in v1.
6. **`pack_function` is a pack-reading tool rule.** It now covers e and 2^x (exponentials) and cbrt. It could refuse falsely if a pack uses a function without ever naming it or writing its symbol, which is unlikely.
7. **The exercise rules are strict by design.**
   - `exercise_values` also refuses `guides`, though some teachers draw guides for given data points.
   - `exercise_text` now covers titles and the caption.
   - The pair regex needs `;` or `, ` between the numbers, so `(0,5)` passes.
8. **Sequences: every defined term must be inside the window** (the critique's point). A lesson on a divergent sequence has to choose `last` so the terms fit, which is the right call for a board.
9. **Label cap 24, window bounds ±1e6 with span ≥ 0,001, steps with at most 4 decimals, aspect [0,4 ; 2] for orthonormal plots.** These are tool limits, so they can move without breaking replay. The model's `Label` cap is structural, but stored labels are only replayed through `display_board` validation in stored transcripts, which were written under the same cap.
10. **Per-card limit.** This block keeps its own limit of 2, as charts do. A combined `MAX_DRAWINGS_PER_CARD` across the four drawing blocks is the lead's call in board.py.

    > **As built.** The lead chose the combined limit (`MAX_DRAWINGS_PER_CARD` = 2 in
    > `board.py`); the plot's own limit was removed.

11. **File ownership.** The design adds `backend/app/domain/expression.py` and `backend/tests/fixtures/expression_cases.json` beyond `plot.py` / `plots.py`. `scripts/probe.py` imports `PACK_WORDS`, `gives_away` and `functions`.

### 6.2 Critique points not adopted as stated

12. **« Map `_x` to x in subscript form ».** I used « indice x », which screen readers pronounce naturally in French.
13. **The x title.** It is neither always outside the frame nor run through `placeLabels`. Candidate A (at the arrow tip) is kept when free, because that is how FWB maths labels an axis. Candidate B, a band below the plot, is always free, so the title never covers a curve.

### 6.3 Open risks

14. **Parser drift.** Mitigations:
    - one 96-case table shared by both parsers, with 0 disagreements between the Python and TS prototypes;
    - a backend test that compares the frontend copy;
    - own-property lookups against the prototype chain;
    - explicit ASCII letter and space sets.

    The design's sources are the prototypes' own code, in `scratchpad/plotv2/`. Re-run the table first thing.
15. **Sampling heuristics.** The board uses a 3 px tolerance, depth 12 and a 20 000-evaluation budget per curve. The tool uses 401 samples plus 40 halvings per straddling pair. Pathological inputs such as sin(1/x) or tan(1000x) in a thin window may draw approximately, or be refused as `outside` while the board would show slivers. That is acceptable for secondary-school functions.
16. **Label placement is heuristic.** KaTeX widths are estimated. In crowded plots a label may sit near a curve, with no tooltip to recover by design; the `bg-card/85` backdrop keeps it legible.
17. **Less information for screen-reader users.** The description omits domains, dots, expressions and vertices on purpose, so the DOM never holds answers a sighted student must read off the drawing. Screen-reader users get less on reading exercises.
18. **Colour key.** Unlabelled distinct functions share a colour. The prompt asks for labels; this is not tool-enforced, because an unlabelled second curve is legitimate when only one function is discussed.
19. **Prompt size.** Three bullets and a voice line move the tutor prefix, so the sha fixtures change. The pack-template edits only affect chapters authored afterwards; older chapters keep working.
20. **Probe fixtures.** The physics probes need a new `tests/fixtures/chapters/mru/`. Maths function graphs (parabolas) still have no fixture material with a graph, so those behaviours are covered by unit tests and the manual checklist only.
21. **Stored data.** A future grammar change that refuses today's expressions would blank old discussions' plots (« Graphique vide »). Grammar changes must stay backward-compatible.
22. **Dark mode is not exercised** (spec 008 D7: the app never sets `.dark`).

## 7. As built

### 7.1 Deviations recorded by the implementer (28 September 2026)

1. **Signatures.** `plots_refusal(items, card, ctx)` and `plots_summary(items)`, the lead's
   family signature. The exercise rules run when `isinstance(card, ExerciseCard)`; the pack is
   `ctx.pack`. `plot_refusal(plot, path, pack=None)`, `gives_away(text)` and `PACK_WORDS` stay
   public for tests and `scripts/probe.py`. The summary is `{"count", "layers": {curves,
   sequences, points, lines}, "functions": [sorted closed-set names]}`.
2. **Model and types.** plot.py is unchanged (`type` is required). No types.ts change.
   `Tick.shift` is a layout.ts-internal type.
3. **expression.py / expression.ts.** Both are the prototypes that passed the 96-case table,
   with NBSP/NNBSP written as escapes. The TS side adds `MAX_EXPRESSION = 120` in
   `compileExpression` only, so a stored `x+x+…` cannot nest past the stack. The case table is
   Prettier-formatted, and the backend copy holds the same bytes, checked by test_expression.py.
4. **gives_away** is a scan of groups (see the note in §3.1), broader than the review asked:
   inequalities, ≠, `;`-pairs with one value, intervals.
5. **Minimum span.** `b - a < MIN_SPAN - 1e-9` on both sides.
6. **sanitise.** A sequence whose `first` lies outside 0…1000 is dropped, and `sequenceDots`
   loops at most 60 times. A stored step must give 1 to 60 intervals; titles are cut at 60
   characters; lists are cut before filtering; an absurd window becomes [−10 ; 10].
7. **sampleCurve.** At depth 12, a gap is joined only when its midpoint lies between the two ends
   and each half carries more than a quarter of the rise. The old `dp <= plotH` cap is dropped
   (with it, 1000000(x-0.01234) in y [−1 ; 1] was not drawn although the tool accepts it). A gap
   across the window's edge keeps halving, so a curve ends on the edge.
8. **y title.** The frame is computed across, then down; the y title's side sets the frame's
   top: right of the arrow when it fits (top 24); otherwise left of it, right-aligned (top 30,
   so the top graduation's label clears the band); otherwise on a row of its own, centred over
   the axis (top 34 with an arrow, 30 without). Arrow heads are marked in the occupancy grid.
9. **Orthonormal steps.** When orthonormal, the one step Célestin gave is used for the other axis
   too, if it gives 1 to 60 intervals there; an integer step is required for a sequence's n axis.
10. **Corner tick labels.** An x label and a y label are compared on ink boxes (11 px). A label on
    the other axis's line is moved rather than dropped: a y label 8 px up (7 px down under a
    top-edge axis) if the tick spacing is at least 3 times the move; an x label sideways, inward,
    to 3 px from the line, if the spacing is at least its width + 9. Otherwise it is dropped; x
    gives way to y. `Tick` gains `shift`.
11. **Caption.** The visible caption (KaTeX html) is aria-hidden, and an sr-only
    `RichText mathOutput="mathml"` copy follows it.
12. **Occupancy grid.** 2 px cells, a 1 px inset in `free()`, paths densified every 3 px (the
    design said 4 px and 6 px).
13. **Margins.** The bottom and left margins are solved so the x labels and the y labels (widest
    + 10 px) fit wherever the axis sits. Band B is exactly 22 px. Orthonormal plots have no
    plotH ≥ 100 floor. A tick label is dropped when it overlaps a foot (4 px pad) or the origin
    « 0 »; one next to a point on an axis is kept, with 2 px clearance. Label and title boxes
    carry `align`; right-anchored ones use CSS `right`. labels.ts estimates widths by splitting
    on `$`/`$$` rather than importing `splitInlineMath`. `plainText` reads Greek letters by name
    and `{,}` as « , ». The sr-only description is plain text from `plainText`, not MathML, so
    the no-leak tests read exactly what a screen reader gets; it counts unlabelled points, names
    labelled dashed layers, writes one sentence per layer kind and colour group, and adds
    « Graphique vide. ».

### 7.2 Rendering deviations recorded at the verification (#18)

Minor, visual only, and kept:

14. **Arrow head.** The axis arrows end in a 7 × 7 px triangle (7 px long, ±3,5 px across), not
    the design's 6 × 4 (`plot-view.tsx`).
15. **x tick labels.** Their baseline sits 16 px under the x axis (`X_LABEL_DY` in `layout.ts`),
    not the design's 12 px.
16. **Label spans.** Labels and titles are positioned from their computed boxes without the
    design's `maxWidth: width`; a right-anchored box uses CSS `right`.

### 7.3 Changes after the verification (29 September 2026)

17. **`PACK_WORDS`** (verification #4): see the note in §5.3.
18. **Slanted inequalities** (verification #13): ⩽ ⩾ ≦ ≧, `\leqq` and `\geqq` count as relations
    in `gives_away`.
19. **`per_card` removed** (verification #10), with `MAX_PLOTS_PER_CARD`: a third plot on a card
    is refused by `display_board` as `drawing_refused` / `per_card`, and no `plot_refused` is
    logged.
20. **One parse per expression** (verification #17): `_parsed` (an `lru_cache`) serves the refusal
    pass and the summary; the logged fields are unchanged.
21. **Boundaries** (verification #17): `orthonormal` accepts exactly 0,4 and 2 and refuses 0,399 and
    2,001, with a 1e-9 slack on both sides (the tool's `_SLACK`, the board's `ASPECT_SLACK`); an
    expression 24 levels deep is accepted and 25 refused, on both sides (`MAX_DEPTH`).
22. **`pack_function`'s limit documented** (verification #16): it reads expressions only (§5.3).
23. **String checks** (verification #5, #14): a bare `m·s^-2`, `10^-3` or `x^{2}` in a plot's title,
    label or caption is refused by `display_board` (`string_script`), logged as `plot_refused`.
24. **A drawing without `type`** (verification #3): `x_range`, `y_range` or `curves` make it a
    plot, refused for its missing `type` as `plot_refused` (`schema.missing`).

### 7.4 Open issues

- `exercise_text` gaps, by design: a bare number (« racine : 1,4 », « $v$ vaut 24 cm/s ») looks
  like the quantity « toutes les 0,5 s »; a comma pair with one value (`(x_S, 2)`) passes; a
  reading guide drawn by hand as a dashed line escapes every rule (the prompt forbids it, and the
  probe flags it). Possible false positives cost one retry: « (2 essais, 3 mesures) », « sur
  $[0 ; 5]$ », `(0 ; b)`.
- The layout was checked geometrically on estimated KaTeX widths; a crowded plot can still put a
  label near a curve (`bg-card/85` keeps it legible).
- Corner nudges: a lifted y label sits 8 px off its tick, only where ticks are at least 24 px
  apart; a sidestepped x label is no longer centred on its tick.
- The frame's top is 24, 30 or 34 px depending on where the y title fits.
- Sampling heuristics (3 px, depth 12, a quarter share of the rise, 20 000 evaluations): an
  extremely steep continuous sigmoid is drawn as a jump; the board and the tool can disagree on
  sin(1/x) or tan(1000x) in thin windows.
- Two distinct unlabelled functions share one colour and read as « Une courbe en 2 morceaux ».
- Screen readers get less on reading exercises, by design.
- A grammar change must stay backward-compatible, or stored plots go « Graphique vide ».
