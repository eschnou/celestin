"""The rows the `wide` rule counts are the rows the board draws: `layers` here and
in `frontend/src/components/celestin/flowchart/layout.ts` read one case table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.tools.flowcharts import layers

FIXTURE = Path(__file__).parents[1] / "fixtures" / "flowchart_layers.json"
FRONTEND_COPY = (
    Path(__file__).parents[3] / "frontend/src/components/celestin/flowchart/__tests__/layer_cases.json"
)
CASES: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_layers_match_the_shared_cases(case: dict[str, Any]) -> None:
    ids: list[str] = case["ids"]
    # Built in node order, whatever the ids look like: "10" stays before "2".
    exits = {ids[i]: [ids[j] for j in targets] for i, targets in enumerate(case["exits"])}
    row, loops = layers(exits)
    index = {name: i for i, name in enumerate(ids)}
    assert [row[name] for name in ids] == case["rows"]
    assert sorted([index[u], index[v]] for u, v in loops) == case["loops"]


def test_the_table_covers_numeric_ids_and_loops() -> None:
    names = {case["name"] for case in CASES}
    assert {"numeric_ids", "while", "leftover", "nested_decisions"} <= names


@pytest.mark.skipif(not FRONTEND_COPY.exists(), reason="the frontend is not checked out")
def test_the_frontend_copy_is_byte_identical() -> None:
    """The older path_cases.json copies drifted apart; this one cannot."""
    assert FRONTEND_COPY.read_bytes() == FIXTURE.read_bytes()
