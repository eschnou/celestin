from __future__ import annotations

import math

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.chart import ChartBlock

ADAPTER = TypeAdapter(ChartBlock)

VALID = {
    "bars": {
        "kind": "bars",
        "measure": "effectif",
        "categories": ["Vélo", "Bus", "À pied"],
        "values": [12, 7, 5],
        "y_title": "Effectifs",
    },
    "sticks": {
        "kind": "sticks",
        "measure": "effectif",
        "x": [12, 14, 16],
        "values": [2, 5, 3],
        "polygon": True,
        "x_title": "Note",
        "y_title": "Effectifs",
    },
    "histogram": {
        "kind": "histogram",
        "measure": "effectif",
        "bounds": [0, 10, 30],
        "values": [10, 10],
        "closed": "left",
        "reference_amplitude": 10,
        "polygon": "closed",
        "x_title": "Taille (cm)",
        "y_title": "Effectif pour une amplitude de 10",
    },
    "cumulative": {
        "kind": "cumulative",
        "measure": "frequence",
        "bounds": [0, 10, 20],
        "values": [0.4, 0.6],
        "closed": "left",
        "direction": "increasing",
        "x_title": "Âge",
        "y_title": "Fréquences cumulées",
    },
    "pie": {
        "kind": "pie",
        "measure": "pourcentage",
        "categories": ["Oui", "Non"],
        "values": [62.5, 37.5],
        "show_values": True,
    },
    "box": {
        "kind": "box",
        "boxes": [{"label": "5A", "minimum": 4, "q1": 9, "median": 12, "q3": 14, "maximum": 19}],
        "x_title": "Note sur 20",
    },
}


@pytest.mark.parametrize("kind", sorted(VALID))
def test_each_kind_validates(kind: str) -> None:
    block = ADAPTER.validate_python({"type": "chart", "chart": VALID[kind]})
    assert block.chart.kind == kind


def _refused(chart: dict) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"type": "chart", "chart": chart})


def test_unknown_kind_refused() -> None:
    _refused({**VALID["bars"], "kind": "scatter"})


def test_negative_value_refused() -> None:
    _refused({**VALID["bars"], "values": [12, -1, 5]})


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_non_finite_numbers_refused(bad: float) -> None:
    _refused({**VALID["sticks"], "x": [12, bad, 16]})
    _refused({**VALID["bars"], "values": [12, bad, 5]})


def test_sizes_are_bounded() -> None:
    _refused({**VALID["bars"], "categories": [f"c{i}" for i in range(21)], "values": [1] * 21})
    _refused({**VALID["pie"], "categories": [f"c{i}" for i in range(9)], "values": [1] * 9})
    _refused({**VALID["box"], "boxes": VALID["box"]["boxes"] * 5})
    _refused({**VALID["bars"], "categories": ["x" * 41, "Bus", "À pied"]})


def test_unknown_field_refused() -> None:
    _refused({**VALID["bars"], "colour": "red"})
