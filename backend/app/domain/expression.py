"""Expressions a plot draws (specs/009-board-drawings/plot.md §2.2).

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
_SPACES = " \t\n\r\u00a0\u202f"  # explicit: str.isspace() and JS \s differ
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
        raise ExprError("unknown_name", f"« {t.text} » inconnu ; permis : {allowed}, pi, e, " + ", ".join(FUNCTIONS))


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
