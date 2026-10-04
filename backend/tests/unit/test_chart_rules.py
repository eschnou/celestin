from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.chart import Chart
from app.services.tools.charts import chart_refusal, charts_refusal
from tests.unit.test_chart_models import VALID

ADAPTER: TypeAdapter[Any] = TypeAdapter(Chart)


def refusal(kind: str, **changes: Any) -> tuple[str, str] | None:
    return chart_refusal(ADAPTER.validate_python({**VALID[kind], **changes}), "blocks[0]")


@pytest.mark.parametrize("kind", sorted(VALID))
def test_every_valid_chart_passes(kind: str) -> None:
    assert refusal(kind) is None


@pytest.mark.parametrize(
    "kind,changes,rule,named",
    [
        ("bars", {"values": [12, 7]}, "lengths", "3 catégories pour 2 valeurs"),
        ("pie", {"values": [100]}, "lengths", "2 catégories pour 1 valeurs"),
        ("sticks", {"x": [12, 14]}, "lengths", "2 valeurs de x"),
        ("histogram", {"bounds": [0, 30]}, "lengths", "2 classes demandent 3 bornes"),
        ("sticks", {"x": [12, 16, 14]}, "order", "x doit être strictement croissant (16 puis 14)"),
        ("cumulative", {"bounds": [0, 10, 10]}, "order", "bounds"),
        ("bars", {"categories": ["Vélo", "Bus", "  vélo "]}, "repeated", "apparaît deux fois"),
        ("bars", {"values": [12, 7.5, 5]}, "integers", "(7.5)"),
        ("bars", {"categories": ["0", "1", "2,5"]}, "numeric_categories", "sticks"),
        ("bars", {"values": [0, 0, 0]}, "empty", "nulles"),
        ("cumulative", {"values": [0.4, 0.58]}, "sum", "totalisent 1"),
        ("pie", {"values": [62.5, 30]}, "sum", "totalisent 100"),
        (
            "box",
            {"boxes": [{"minimum": 4, "q1": 13, "median": 12, "q3": 14, "maximum": 19}]},
            "box_order",
            "boîte 1",
        ),
        ("histogram", {"bars": False, "polygon": "none"}, "layers", "polygone"),
        ("histogram", {"bounds": [0, 10, 20]}, "reference", "reference_amplitude"),
        ("bars", {"categories": ["$x$", "Bus", "À pied"]}, "label_math", "« $x$ »"),
        (
            "box",
            {"boxes": [{"label": "$A$", "minimum": 1, "q1": 2, "median": 3, "q3": 4, "maximum": 5}]},
            "label_math",
            "$A$",
        ),
    ],
)
def test_each_rule_refuses_and_names_the_field(
    kind: str, changes: dict[str, Any], rule: str, named: str
) -> None:
    found = refusal(kind, **changes)
    assert found is not None
    assert found[0] == rule
    assert found[1].startswith("Le graphique blocks[0]")
    assert named in found[1]


def test_boundaries_are_accepted() -> None:
    # Three fréquences rounded to the thousandth are a fair 1.
    assert refusal("cumulative", bounds=[0, 10, 20, 30], values=[0.333, 0.333, 0.333]) is None
    # 0,98 over two values is outside the slack.
    assert refusal("cumulative", values=[0.49, 0.49]) is not None
    # 7 bounds for 6 classes.
    six = {"bounds": [0, 10, 20, 30, 40, 50, 70], "values": [1, 2, 3, 4, 5, 6]}
    assert refusal("histogram", **six) is None
    assert refusal("histogram", **{**six, "bounds": six["bounds"][:6]}) is not None
    # One non-numeric category keeps a bar chart qualitative.
    assert refusal("bars", categories=["0", "1", "2 ou plus"]) is None
    # A whole number written as a float is an effectif.
    assert refusal("bars", values=[12.0, 7, 5]) is None
    # Equal amplitudes without a reference, and a box that is flat on one side.
    assert refusal("histogram", bounds=[0, 10, 20], reference_amplitude=None) is None
    flat = {"minimum": 4, "q1": 4, "median": 12, "q3": 12, "maximum": 19}
    assert refusal("box", boxes=[flat]) is None


def test_how_many_charts_a_card_holds_is_not_the_chart_rules_business() -> None:
    """The cap is `display_board`'s, across every drawing family, and it is reached
    first: a limit of the chart family's own could never fire."""
    three = [(f"blocks[{i}]", ADAPTER.validate_python(VALID[kind])) for i, kind in enumerate(("sticks", "pie", "bars"))]
    assert charts_refusal(three) is None
    # The chart rules still read every chart: the third one's shape is checked.
    broken = [*three[:2], ("blocks[2]", ADAPTER.validate_python({**VALID["sticks"], "x": [12, 16, 14]}))]
    found = charts_refusal(broken)
    assert found is not None and found[0] == "order" and found[1].startswith("Le graphique blocks[2]")
