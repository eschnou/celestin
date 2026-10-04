from __future__ import annotations

import math
import string
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.figure import Figure, FigureBlock

BLOCK = TypeAdapter(FigureBlock)
FIGURE: TypeAdapter[Any] = TypeAdapter(Figure)

# One valid figure of each kind, shared with the rule tests and the board tests.
VALID: dict[str, dict[str, Any]] = {
    "plane": {
        "kind": "plane",
        "points": {"A": [0, 0], "B": [4, 0], "C": [0, 3]},
        "shapes": [
            {"draw": "polygon", "of": ["A", "B", "C"]},
            {"draw": "right_angle", "of": ["B", "A", "C"]},
            {"draw": "segment", "of": ["B", "C"], "label": "$5$ cm"},
        ],
    },
    "number_line": {
        "kind": "number_line",
        "intervals": [{"start": 2, "end": None, "closed": "left", "label": "$S$"}],
        "marks": [{"x": 0}],
    },
    "sets": {
        "kind": "sets",
        "layout": "overlap",
        "sets": [{"id": "A", "label": "Diviseurs de 12"}, {"id": "B", "label": "Diviseurs de 18"}],
        "elements": [
            {"text": t, "within": w}
            for t, w in [
                ("4", ["A"]),
                ("12", ["A"]),
                ("1", ["A", "B"]),
                ("2", ["A", "B"]),
                ("3", ["A", "B"]),
                ("6", ["A", "B"]),
                ("9", ["B"]),
                ("18", ["B"]),
            ]
        ],
        "shade": [["A", "B"]],
    },
}

# ℕ ⊂ ℤ ⊂ 𝔻 ⊂ ℚ ⊂ ℝ, outermost first; 7 is listed in every set and lands in ℕ.
NESTED: dict[str, Any] = {
    "kind": "sets",
    "layout": "nested",
    "sets": [{"id": i, "label": f"$\\mathbb{{{i}}}$"} for i in "RQDZN"],
    "elements": [
        {"text": "$\\sqrt{2}$", "within": ["R"]},
        {"text": "$\\pi$", "within": ["R"]},
        {"text": "$\\frac{1}{3}$", "within": ["Q"]},
        {"text": "0,5", "within": ["D"]},
        {"text": "−3", "within": ["Z"]},
        {"text": "0", "within": ["N"]},
        {"text": "7", "within": ["N", "Z", "D", "Q", "R"]},
    ],
}

STATS: dict[str, Any] = {
    "kind": "sets",
    "layout": "nested",
    "sets": [{"id": "P", "label": "Population"}, {"id": "E", "label": "Échantillon"}],
    "elements": [{"text": "individu", "within": ["E"]}],
}

AXES_ONLY: dict[str, Any] = {"kind": "plane", "axes": True, "grid": True}


def figure(base: str, **changes: Any) -> Any:
    return FIGURE.validate_python({**VALID[base], **changes})


def refused(base: str, **changes: Any) -> None:
    with pytest.raises(ValidationError):
        figure(base, **changes)


@pytest.mark.parametrize("fig", [*VALID.values(), NESTED, STATS, AXES_ONLY])
def test_valid_figures_validate_and_dump_their_kind(fig: dict[str, Any]) -> None:
    block = BLOCK.validate_python({"type": "figure", "figure": fig})
    dumped = block.model_dump(mode="json")
    assert dumped["type"] == "figure"
    assert dumped["figure"]["kind"] == fig["kind"]


def test_the_block_names_its_type() -> None:
    # `type` is required: a card's `drawing` reads a missing tag from the keys only to
    # report the figure's own error (« type » missing), never to accept it untagged.
    with pytest.raises(ValidationError):
        BLOCK.validate_python({"figure": VALID["plane"]})


def test_defaults_follow_the_usual_conventions() -> None:
    assert figure("plane").marker == "cross"
    assert figure("number_line").convention == "brackets"
    assert figure("plane").show_values is False
    assert figure("sets").elements[0].within == ["A"]


@pytest.mark.parametrize("name", ["A", "A'", "M''", "A_1", "B_12"])
def test_points_are_named_as_a_course_names_them(name: str) -> None:
    assert name in figure("plane", points={name: [1, 2]}, shapes=[]).points


@pytest.mark.parametrize("name", ["AB", "a", "1", "$A$", "A1", "A'''", "A_123", ""])
def test_other_point_names_are_refused(name: str) -> None:
    refused("plane", points={name: [1, 2]}, shapes=[])


def test_a_bad_point_name_is_located_under_figure() -> None:
    with pytest.raises(ValidationError) as caught:
        BLOCK.validate_python({"type": "figure", "figure": {"kind": "plane", "points": {"AB": [0, 0]}}})
    error = caught.value.errors()[0]
    assert "figure" in error["loc"]
    assert error["type"] == "string_pattern_mismatch"


@pytest.mark.parametrize(
    "kind,changes",
    [
        ("plane", {"kind": "venn"}),
        ("plane", {"shapes": [{"draw": "curve", "of": ["A", "B"]}]}),
        ("sets", {"layout": "venn"}),
        ("number_line", {"intervals": [{"start": 0, "end": 1, "closed": "open"}]}),
        ("number_line", {"convention": "circles"}),
        ("plane", {"marker": "star"}),
        ("plane", {"shapes": [{"draw": "segment", "of": ["A", "B"], "style": "bold"}]}),
        ("number_line", {"intervals": [{"start": 0, "end": 1}]}),
    ],
)
def test_unknown_enums_are_refused(kind: str, changes: dict[str, Any]) -> None:
    refused(kind, **changes)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_numbers_are_finite(bad: float) -> None:
    refused("plane", points={"A": [bad, 0]})
    refused("plane", x_range=[0, bad])
    refused("plane", shapes=[{"draw": "circle", "of": ["A"], "radius": bad}])
    refused("number_line", intervals=[{"start": bad, "end": 3, "closed": "both"}])
    refused("number_line", marks=[{"x": bad}])


def test_set_ids_are_short() -> None:
    refused("sets", sets=[{"id": "ABC", "label": "x"}, {"id": "B", "label": "y"}])
    refused("sets", sets=[{"id": "1", "label": "x"}, {"id": "B", "label": "y"}])
    assert figure("sets", sets=[{"id": "E1", "label": "x"}, {"id": "B", "label": "y"}]).sets[0].id == "E1"


def _names(n: int) -> list[str]:
    return (list(string.ascii_uppercase) + [f"{c}'" for c in string.ascii_uppercase])[:n]


def test_sizes_are_bounded() -> None:
    assert figure("plane", points={n: [i, 0] for i, n in enumerate(_names(26))}, shapes=[])
    refused("plane", points={n: [i, 0] for i, n in enumerate(_names(27))}, shapes=[])
    refused("plane", shapes=[{"draw": "segment", "of": ["A", "B"]}] * 31)
    refused("plane", shapes=[{"draw": "polygon", "of": _names(13)}])
    refused("plane", shapes=[{"draw": "polygon", "of": []}])
    refused("number_line", intervals=[{"start": i, "end": i + 0.5, "closed": "both"} for i in range(5)])
    refused("number_line", marks=[{"x": i} for i in range(13)])
    refused("sets", sets=[{"id": c, "label": c} for c in "ABCDEF"])
    refused("sets", sets=[])
    refused("sets", elements=[{"text": str(i), "within": ["A"]} for i in range(25)])
    refused("sets", shade=[["A"]] * 9)


def test_fields_are_bounded() -> None:
    refused("plane", shapes=[{"draw": "circle", "of": ["A"], "radius": 0}])
    refused("plane", shapes=[{"draw": "circle", "of": ["A"], "radius": -1}])
    refused("plane", shapes=[{"draw": "segment", "of": ["A", "B"], "marks": 4}])
    refused("plane", shapes=[{"draw": "segment", "of": ["A", "B"], "marks": -1}])
    refused("plane", shapes=[{"draw": "segment", "of": ["A", "B"], "label": "x" * 41}])
    refused("plane", caption="x" * 201)
    refused("sets", universe="")
    refused("plane", x_range=[0, 1, 2])
    refused("plane", points={"A": [0]})


@pytest.mark.parametrize(
    "kind,changes",
    [
        ("plane", {"colour": "red"}),
        ("plane", {"shapes": [{"draw": "segment", "of": ["A", "B"], "colour": "red"}]}),
        ("number_line", {"intervals": [{"start": 0, "end": 1, "closed": "both", "colour": "red"}]}),
        ("number_line", {"marks": [{"x": 0, "colour": "red"}]}),
        ("sets", {"sets": [{"id": "A", "label": "x", "colour": "red"}, {"id": "B", "label": "y"}]}),
        ("sets", {"elements": [{"text": "1", "within": ["A"], "colour": "red"}]}),
    ],
)
def test_unknown_fields_are_refused(kind: str, changes: dict[str, Any]) -> None:
    refused(kind, **changes)


def test_sets_are_a_list_so_their_order_is_explicit() -> None:
    refused("sets", sets={"A": "Diviseurs de 12", "B": "Diviseurs de 18"})
