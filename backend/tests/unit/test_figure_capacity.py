"""The capacity contract between the `crowded` rule and the board's layout of sets.

`tests/fixtures/figure/capacity.json` holds the numbers and the cases; the
frontend's `figure/venn.ts` reads the same table (its copy lives next to its
tests), so the tool never refuses what the board can draw, nor lets through what
it cannot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.figure import Figure
from app.services.tools import figures

FIXTURE = Path(__file__).parent.parent / "fixtures" / "figure" / "capacity.json"
FRONTEND_COPY = (
    Path(__file__).resolve().parents[3] / "frontend" / "src" / "components" / "celestin" / "figure" / "__tests__" / "capacity.json"
)
TABLE: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
ADAPTER: TypeAdapter[Any] = TypeAdapter(Figure)


def test_the_frontend_reads_the_same_bytes() -> None:
    # The older path_cases.json copies drifted; this one cannot.
    assert FRONTEND_COPY.read_bytes() == FIXTURE.read_bytes()


def test_the_module_constants_are_the_table_constants() -> None:
    constants = TABLE["constants"]
    for name in ("BOARD_PX", "MARGIN_PX", "ROW_PX", "GAP_PX", "CHAR_PX", "GLYPH_PX", "MAX_PER_ZONE"):
        assert getattr(figures, name) == constants[name], name
    assert figures.NESTED == TABLE["nested"]
    slots = {
        layout: {"".join(str(i) for i in zone): list(slot) for zone, slot in zones.items()}
        for layout, zones in figures.SLOTS.items()
    }
    assert slots == TABLE["slots"]


@pytest.mark.parametrize("text,px", TABLE["text_px"])
def test_text_widths(text: str, px: int) -> None:
    assert figures.text_px(text) == px


@pytest.mark.parametrize("case", TABLE["rows"])
def test_flow_rows(case: dict[str, Any]) -> None:
    assert figures.flow_rows(case["widths"], case["slot"]) == case["rows"]


@pytest.mark.parametrize("case", TABLE["cases"], ids=[c["name"] for c in TABLE["cases"]])
def test_crowded_iff_the_layout_cannot_hold_it(case: dict[str, Any]) -> None:
    found = figures.figure_refusal(ADAPTER.validate_python(case["figure"]), "blocks[0]")
    # Every case is otherwise valid: the only rule it may break is `crowded`.
    assert found is None or found[0] == "crowded", found
    assert (found is None) == case["fits"]
