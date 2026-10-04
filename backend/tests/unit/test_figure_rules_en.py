"""Spec 011 R6.3: the figure rules read English notation and numbers.

French stays in `test_figure_rules.py`, untouched; its `;` and decimal-comma cases are
asserted again here only where the two languages must differ.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.figure import Figure
from app.services.tools.figures import _number, figure_refusal
from tests.unit.test_figure_models import AXES_ONLY, NESTED, STATS, VALID

ADAPTER: TypeAdapter[Any] = TypeAdapter(Figure)
BASES: dict[str, dict[str, Any]] = {**VALID, "nested": NESTED, "stats": STATS, "axes": AXES_ONLY}
TRIANGLE = {"A": [0, 0], "B": [4, 0], "C": [0, 3]}


def refusal(base: str, language: str = "en", **changes: Any) -> tuple[str, str] | None:
    return figure_refusal(ADAPTER.validate_python({**BASES[base], **changes}), "blocks[0]", language)  # type: ignore[arg-type]


def plane(points: dict[str, list[float]], *shapes: dict[str, Any], language: str = "en") -> tuple[str, str] | None:
    return refusal("plane", language, points=points, shapes=list(shapes))


def seg(a: str, b: str, **more: Any) -> dict[str, Any]:
    return {"draw": "segment", "of": [a, b], **more}


def angle(a: str, b: str, c: str, **more: Any) -> dict[str, Any]:
    return {"draw": "angle", "of": [a, b, c], **more}


def line_with(label: str, language: str = "en") -> tuple[str, str] | None:
    interval = {"start": 2, "end": 5, "closed": "left", "label": label}
    return refusal("number_line", language, intervals=[interval], marks=[])


@pytest.mark.parametrize("base", sorted(BASES))
def test_every_valid_figure_passes_in_english(base: str) -> None:
    assert refusal(base) is None


# --- hand-written coordinates and intervals --------------------------------------

HAND_WRITTEN = [
    "$(2, 3)$",
    "(2,3)",
    "(2, -1.5)",
    "$(-2.5, 4)$",
    "$[2, 5)$",
    "$(2, 5]$",
    "$[2, 5]$",
    "$(-\\infty, 2]$",
    "$(2, \\infty)$",
    "$(\\frac{1}{2}, 3)$",
    "$\\left(2.5\\,,\\,{-}1\\right)$",
    "Solution: $[0, 1]$",
    "$]2; 5[$",  # French notation by hand is no better in an English course
    "$(2 ; 3)$",
]

NOT_HAND_WRITTEN = [
    "The segment $[AB]$ and the ray $[AB$",
    "The triangle $ABC$ is right-angled at $A$; $[BC]$ is the hypotenuse.",
    "Scale: 1 cm for 1 unit; $[OI]$ measures 1.",
    "$[AB]$ 5 cm; $[CD]$ 3 cm",
    "Solution: the reals greater than 2 (2, exclusive)",
    "Orthonormal frame $(O, \\vec{i}, \\vec{j})$",
    "The frame $(O, I, J)$",
    "A point $M(x, y)$ of the plane",
    "On the interval $[a, b]$",
    "The set $\\{1, 2\\}$ and the set $\\{3, 4\\}$",
    "The elements 1, 2, 3 (in red)",
    "$\\left(AB\\right) \\perp \\left(CD\\right)$",
    "Points $(1, 2, 3)$",
]


@pytest.mark.parametrize("label", HAND_WRITTEN)
def test_hand_written_notation_is_refused_in_english(label: str) -> None:
    for found in (
        plane(TRIANGLE, seg("A", "B", label=label[:40])),
        line_with(label[:40]),
        refusal("sets", caption=label),
    ):
        assert found is not None and found[0] == "label_notation", (label, found)


@pytest.mark.parametrize("caption", NOT_HAND_WRITTEN)
def test_an_english_caption_is_not_read_as_notation(caption: str) -> None:
    assert refusal("plane", caption=caption) is None


def test_the_comma_pair_is_notation_in_english_and_prose_in_french() -> None:
    """In French `(2,3)` is a decimal, `(2 ; 3)` the pair; in English the other way round."""
    assert refusal("sets", "en", caption="A = (2, 3)") is not None
    assert refusal("sets", "fr", caption="A = (2, 3)") is None
    assert refusal("sets", "fr", caption="A = (2 ; 3)") is not None


# --- numbers ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language", "value"),
    [
        ("1,500", "en", 1500.0),
        ("1,234,567.5", "en", 1234567.5),
        ("3.5", "en", 3.5),
        ("1,5", "fr", 1.5),
        ("3.5", "fr", 3.5),
    ],
)
def test_a_number_is_read_as_the_course_writes_it(text: str, language: str, value: float) -> None:
    assert _number(text, language) == value  # type: ignore[arg-type]


def test_the_default_reading_is_the_french_one() -> None:
    assert _number("2,5") == 2.5


def test_measures_use_the_decimal_point() -> None:
    # 3.5 against 7: in the ratio of the drawing.
    points = {"A": [0, 0], "B": [3.5, 0], "C": [0, 7]}
    assert plane(points, seg("A", "B", label="3.5 cm"), seg("A", "C", label="7 cm")) is None
    found = plane(points, seg("A", "B", label="3.5 cm"), seg("A", "C", label="6 cm"))
    assert found is not None and found[0] == "measure"


def test_a_thousands_comma_is_one_length() -> None:
    points = {"A": [0, 0], "B": [1.5, 0], "C": [0, 3]}
    assert plane(points, seg("A", "B", label="1,500 m"), seg("A", "C", label="3,000 m")) is None
    found = plane(points, seg("A", "B", label="1,500 m"), seg("A", "C", label="4,000 m"))
    assert found is not None and found[0] == "measure"


def test_an_angle_is_read_with_a_decimal_point() -> None:
    right = {"A": [1, 0], "B": [0, 0], "C": [1, 1]}
    assert plane(right, angle("A", "B", "C", label="$45^\\circ$")) is None
    assert plane(right, angle("A", "B", "C", label="$45.0°$")) is None
    found = plane(right, angle("A", "B", "C", label="$37.5^\\circ$"))
    assert found is not None and found[0] == "measure" and "37.5°" in found[1]


def test_french_measures_are_read_as_before() -> None:
    right = {"A": [1, 0], "B": [0, 0], "C": [1, 1]}
    found = plane(right, angle("A", "B", "C", label="$37{,}5^\\circ$"), language="fr")
    assert found is not None and found[0] == "measure" and "37,5°" in found[1]
