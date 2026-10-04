from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.plot import PlotBlock

ADAPTER = TypeAdapter(PlotBlock)

# One valid plot per use the design names (specs/009-board-drawings/plot.md §2.3). The frontend's fixtures
# (plot/__tests__/fixtures.ts) draw the same seven.
VALID: dict[str, dict[str, Any]] = {
    "parabola": {
        "type": "plot",
        "x_range": [-4, 4],
        "y_range": [-5, 6],
        "x_title": "$x$",
        "y_title": "$y$",
        "curves": [{"expr": "x^2-4", "label": "$f$"}],
        "points": [{"x": 0, "y": -4, "label": "$S$", "show_values": True}],
    },
    "motion": {
        "type": "plot",
        "x_range": [0, 16],
        "y_range": [0, 12],
        "x_title": "$t$ (s)",
        "y_title": "$v$ (m/s)",
        "x_step": 2,
        "y_step": 2,
        "curves": [
            {"expr": "2t", "domain": [0, 5]},
            {"expr": "10", "domain": [5, 12]},
            {"expr": "10-2.5(t-12)", "domain": [12, 16]},
        ],
    },
    "sequence": {
        "type": "plot",
        "x_range": [0, 8],
        "y_range": [0, 22],
        "x_title": "$n$",
        "y_title": "$u_n$",
        "x_step": 1,
        "sequences": [{"expr": "2+3(n-1)", "last": 7, "label": "$u_n$"}],
    },
    "hyperbola": {
        "type": "plot",
        "x_range": [-4, 6],
        "y_range": [-5, 5],
        "x_title": "$x$",
        "y_title": "$y$",
        "curves": [{"expr": "1/(x-1)", "label": "$h$"}],
        "lines": [{"vertices": [[1, -5], [1, 5]], "dashed": True}],
    },
    "piecewise": {
        "type": "plot",
        "x_range": [-3, 4],
        "y_range": [-3, 5],
        "x_title": "$x$",
        "y_title": "$y$",
        "curves": [
            {"expr": "x+1", "domain": [-3, 1], "end_dot": "hollow", "label": "$f$"},
            {"expr": "4", "domain": [1, 4], "start_dot": "filled", "label": "$f$"},
        ],
    },
    "data": {
        "type": "plot",
        "x_range": [0, 2.5],
        "y_range": [0, 60],
        "x_title": "$t$ (s)",
        "y_title": "$x$ (cm)",
        "x_step": 0.5,
        "y_step": 10,
        "points": [
            {"x": 0, "y": 0, "mark": "cross"},
            {"x": 0.5, "y": 12, "mark": "cross"},
            {"x": 1, "y": 24, "mark": "cross"},
            {"x": 1.5, "y": 36, "mark": "cross"},
            {"x": 2, "y": 48, "mark": "cross"},
        ],
        "lines": [{"vertices": [[0, 0], [2, 48]]}],
        "caption": "Position de la bille (toutes les 0,5 s)",
    },
    "orthonormal": {
        "type": "plot",
        "x_range": [-5, 5],
        "y_range": [-2, 4],
        "x_title": "$x$",
        "y_title": "$y$",
        "x_step": 1,
        "y_step": 1,
        "orthonormal": True,
        "curves": [{"expr": "0.5x+1", "label": "$d$"}],
    },
}


def plot(**changes: Any) -> dict[str, Any]:
    return {**VALID["parabola"], **changes}


@pytest.mark.parametrize("name", sorted(VALID))
def test_every_valid_plot_validates(name: str) -> None:
    assert ADAPTER.validate_python(VALID[name]).type == "plot"


def test_defaults() -> None:
    block = ADAPTER.validate_python(
        {"type": "plot", "x_range": [0, 1], "y_range": [0, 1], "x_title": "x", "y_title": "y"}
    )
    assert (block.grid, block.orthonormal, block.x_step, block.caption) == (True, False, None, None)
    assert (block.curves, block.sequences, block.points, block.lines) == ([], [], [], [])
    sequence = ADAPTER.validate_python(VALID["sequence"]).sequences[0]
    assert sequence.first == 1  # FWB indexes from u₁
    curve = ADAPTER.validate_python(VALID["parabola"]).curves[0]
    assert (curve.domain, curve.start_dot, curve.end_dot, curve.dashed) == (None, "none", "none", False)
    point = ADAPTER.validate_python(VALID["parabola"]).points[0]
    assert (point.mark, point.guides) == ("filled", False)


def test_type_is_required() -> None:
    # A drawing without a tag reads as a chart (board.py `Drawing`), so a plot says what it is.
    body = {k: v for k, v in VALID["parabola"].items() if k != "type"}
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(body)


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": 1},
        {"type": "chart"},
        {"x_range": [math.nan, 1]},
        {"x_range": [0, math.inf]},
        {"x_range": [0, 1, 2]},
        {"x_range": [0]},
        {"curves": [{"expr": "x"}] * 7},
        {"points": [{"x": 0, "y": 0}] * 21},
        {"sequences": [{"expr": "n", "last": 3}] * 4},
        {"lines": [{"vertices": [[0, 0], [1, 1]]}] * 9},
        {"lines": [{"vertices": [[i, i] for i in range(31)]}]},
        {"lines": [{"vertices": [[0, 0]]}]},
        {"curves": [{"expr": "x", "label": "x" * 25}]},
        {"curves": [{"expr": "x" * 121}]},
        {"curves": [{"expr": ""}]},
        {"curves": [{"expr": "x", "domain": [0, math.nan]}]},
        {"curves": [{"expr": "x", "start_dot": "open"}]},
        {"curves": [{"expr": "x", "colour": "red"}]},
        {"sequences": [{"expr": "n", "last": 1001}]},
        {"sequences": [{"expr": "n", "first": -1, "last": 3}]},
        {"sequences": [{"expr": "n"}]},
        {"x_step": 0},
        {"x_step": -1},
        {"y_step": math.nan},
        {"points": [{"x": 0, "y": 0, "mark": "star"}]},
        {"points": [{"x": math.inf, "y": 0}]},
        {"x_title": ""},
        {"x_title": "x" * 41},
        {"caption": "c" * 201},
    ],
)
def test_structural_refusals(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(plot(**changes))


def test_a_label_at_the_limit_is_kept() -> None:
    block = ADAPTER.validate_python(plot(curves=[{"expr": "x", "label": "x" * 24}]))
    assert block.curves[0].label == "x" * 24
