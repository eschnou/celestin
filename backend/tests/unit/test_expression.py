from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.domain.expression import (
    CURVE_VARIABLES,
    MAX_DEPTH,
    SEQUENCE_VARIABLES,
    ExprError,
    evaluate,
    functions,
    parse,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "expression_cases.json"
# The browser's copy: plot/expression.ts passes the same table (expression.test.ts).
FRONTEND_COPY = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "components"
    / "celestin"
    / "plot"
    / "__tests__"
    / "expression_cases.json"
)
CASES: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def _id(case: dict[str, Any]) -> str:
    return f"{case['src']!r}/{''.join(case['vars'])}"


@pytest.mark.parametrize("case", CASES, ids=[_id(c) for c in CASES])
def test_case_table(case: dict[str, Any]) -> None:
    variables = frozenset(case["vars"])
    if "error" in case:
        with pytest.raises(ExprError) as refused:
            parse(case["src"], variables)
        assert refused.value.code == case["error"]
        return
    node = parse(case["src"], variables)
    for value, expected in case["at"]:
        got = evaluate(node, value)
        if expected is None:
            assert not math.isfinite(got), (case["src"], value, got)
        else:
            assert abs(got - expected) <= 1e-9 * max(1.0, abs(expected)), (case["src"], value, got)


def test_the_table_covers_every_refusal_code() -> None:
    codes = {c["error"] for c in CASES if "error" in c}
    assert codes == {
        "syntax",
        "unknown_name",
        "latex",
        "comma",
        "equation",
        "scientific",
        "ambiguous",
        "variables",
        "depth",
    }
    assert len(CASES) >= 96


def test_frontend_copy_is_byte_identical() -> None:
    """Two parsers, one table: the copies must not drift (path_cases.json once did)."""
    if not FRONTEND_COPY.exists():
        pytest.skip("frontend tree absent")
    assert FRONTEND_COPY.read_bytes() == FIXTURE.read_bytes()


def _refusal(source: str, variables: frozenset[str] = CURVE_VARIABLES) -> ExprError:
    with pytest.raises(ExprError) as refused:
        parse(source, variables)
    return refused.value


def test_messages_tell_the_model_what_to_write() -> None:
    assert "10^-3" in _refusal("1e-3").message
    assert "1/(2x)" in _refusal("1/2x").message
    assert "t ou x" in _refusal("sen(x)").message
    assert "permis : n," in _refusal("2x-1", SEQUENCE_VARIABLES).message
    assert "incomplète" in _refusal("2x^").message
    assert "position 4" in _refusal("x +* 2").message
    assert "abs(" in _refusal("|x|").message
    assert "x^2" in _refusal("x²").message
    assert "pas du LaTeX" in _refusal("\\frac{1}{x}").message
    assert "point" in _refusal("2,5x").message
    assert "y =" in _refusal("y = 2x").message


@pytest.mark.parametrize(
    "nest",
    [
        lambda k: "(" * k + "x" + ")" * k,  # parentheses
        lambda k: "sqrt(" * k + "x" + ")" * k,  # calls
        lambda k: "-" * k + "x",  # signs
        lambda k: "2^" * k + "x",  # exponents
    ],
    ids=["parentheses", "calls", "signs", "exponents"],
)
def test_depth_is_refused_one_past_the_limit(nest: Callable[[int], str]) -> None:
    """The same limit as the browser's (MAX_DEPTH in plot/expression.ts, tested there):
    exactly 24 levels parse, 25 are refused."""
    assert MAX_DEPTH == 24
    parse(nest(MAX_DEPTH), CURVE_VARIABLES)
    assert _refusal(nest(MAX_DEPTH + 1)).code == "depth"


def test_evaluate_never_raises() -> None:
    for case in CASES:
        if "error" in case:
            continue
        node = parse(case["src"], frozenset(case["vars"]))
        for value in (-1e308, -800.0, -1.0, 0.0, 1.0, 800.0, 1e308, math.nan):
            evaluate(node, value)


@pytest.mark.parametrize(
    "source,powers,expected",
    [
        ("sin(x)+ln(exp(x))", True, {"sin", "ln", "exp"}),
        ("e^x", True, {"exp"}),
        ("2^x", True, {"exp"}),
        ("2^(x^2)", True, {"exp"}),
        ("2e", True, {"exp"}),
        ("x^2", True, set()),
        ("x^2+pi", True, set()),
        ("cbrt(x)", True, {"cbrt"}),
    ],
)
def test_functions_reports_what_the_pack_rule_checks(source: str, powers: bool, expected: set[str]) -> None:
    assert functions(parse(source, CURVE_VARIABLES), powers) == expected


def test_a_geometric_term_is_a_power_not_an_exponential() -> None:
    assert functions(parse("3*0.5^(n-1)", SEQUENCE_VARIABLES), powers=False) == set()
    assert functions(parse("e^n", SEQUENCE_VARIABLES), powers=False) == {"exp"}
