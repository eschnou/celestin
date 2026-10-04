"""A flowchart through `display_board`, as the model calls it."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

import pytest

from app.api.schemas.chat import ToolEntry
from app.api.schemas.discussion import StoredEntry
from app.domain.board import marker_for
from app.domain.errors import ToolValidationError
from app.services.tools import registry
from app.services.tools.board import BoardSet
from tests.fixtures.curricula import ctx_for
from tests.unit.test_chart_models import VALID as CHARTS
from tests.unit.test_flowchart_models import VALID, valid

CTX = replace(ctx_for(), user_id="u1", chapter_id="c1")
LOGGER = "app.services.tools.board"


def _call(card: dict[str, Any]) -> Any:
    return registry.execute("display_board", json.dumps({"card": card}), CTX)


def _explanation(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "explanation", "title": "Méthode", "blocks": list(blocks)}


def _exercise(drawing: dict[str, Any], statement: str = "Complète l'organigramme.") -> dict[str, Any]:
    return {"kind": "exercise", "title": "À compléter", "statement": statement, "drawing": drawing}


def _content(block: dict[str, Any]) -> list[str]:
    """Every id, text, label and caption of a flowchart: none may reach a log."""
    out = [block.get("caption") or ""]
    for node in block["nodes"]:
        out += [node["id"], node["text"], *(e.get("label") or "" for e in node.get("next", []))]
    return [value for value in out if value]


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    """What the flowchart records carry beyond where they were logged from."""
    skip = {"pathname", "filename", "module", "funcName", "name", "processName", "threadName", "taskName"}
    return " ".join(
        str(value)
        for record in caplog.records
        if record.message.startswith("flowchart_")
        for key, value in record.__dict__.items()
        if key not in skip
    )


def test_a_flowchart_dispatches_and_logs_counts_only(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        out = _call(_explanation(VALID["loop"]))
    assert isinstance(out, BoardSet)
    assert out.marker == "explication affichée"
    record = next(r for r in caplog.records if r.message == "flowchart_displayed")
    seen = (record.user_id, record.chapter_id, record.mode, record.nodes, record.hidden, record.path)  # type: ignore[attr-defined]
    assert seen == ("u1", "c1", "parcours", [8], 0, False)
    logged = _logged(caplog)
    assert not [value for value in _content(VALID["loop"]) if value in logged]


def test_a_refused_flowchart_logs_its_rule_and_no_content(caplog: pytest.LogCaptureFixture) -> None:
    broken = valid("method")
    broken["nodes"][0]["next"] = [{"to": "zz"}]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        with pytest.raises(ToolValidationError) as exc:
            _call(_explanation({"type": "text", "text": "Voici la méthode :"}, broken))
    assert exc.value.message.startswith("L'organigramme blocks[1]")
    record = next(r for r in caplog.records if r.message == "flowchart_refused")
    assert record.rule == "unknown_id"  # type: ignore[attr-defined]
    logged = _logged(caplog)
    assert not [value for value in _content(broken) if len(value) > 3 and value in logged]
    assert not [r for r in caplog.records if r.message.endswith("_displayed")]


def test_a_flowchart_the_card_model_refuses_is_counted_too(caplog: pytest.LogCaptureFixture) -> None:
    bad = valid("method")
    bad["nodes"][0]["kind"] = "loop"
    with caplog.at_level(logging.INFO, logger=LOGGER):
        with pytest.raises(ToolValidationError, match="Arguments invalides"):
            _call(_explanation(bad))
        with pytest.raises(ToolValidationError, match="Arguments invalides"):
            _call(_exercise(bad))
    rules = [r.rule for r in caplog.records if r.message == "flowchart_refused"]  # type: ignore[attr-defined]
    assert rules == ["schema.literal_error", "schema.literal_error"]


def test_latex_outside_dollars_in_a_node_is_refused() -> None:
    bare = valid("nested")
    bare["nodes"][1]["text"] = r"\Delta > 0 ?"
    with pytest.raises(ToolValidationError, match=r"card\.blocks\[0\]\.nodes\[1\]\.text"):
        _call(_explanation(bare))
    assert isinstance(_call(_explanation(VALID["nested"])), BoardSet)


def test_an_exercise_hides_boxes_but_never_shows_the_way() -> None:
    with pytest.raises(ToolValidationError, match="pas de path"):
        _call(_exercise({**valid("loop"), "path": ["debut", "lire"]}))
    hidden = {**valid("loop"), "hidden": ["ajout", "incr"]}
    assert isinstance(_call(_exercise(hidden, "Complète les deux cases de la boucle.")), BoardSet)


def test_a_refused_chart_beside_a_valid_flowchart_logs_no_display(caplog: pytest.LogCaptureFixture) -> None:
    chart = {"type": "chart", "chart": {**CHARTS["sticks"], "x": [12, 16, 14]}}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        with pytest.raises(ToolValidationError):
            _call(_explanation(chart, VALID["method"]))
    messages = [r.message for r in caplog.records]
    assert "chart_refused" in messages
    assert "flowchart_refused" not in messages
    assert not [m for m in messages if m.endswith("_displayed")]


def test_a_refused_flowchart_beside_a_valid_chart_logs_no_display(caplog: pytest.LogCaptureFixture) -> None:
    chart = {"type": "chart", "chart": CHARTS["sticks"]}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        with pytest.raises(ToolValidationError):
            _call(_explanation(chart, {**valid("method"), "hidden": ["sa"]}))
    messages = [r.message for r in caplog.records]
    assert "flowchart_refused" in messages
    assert not [m for m in messages if m.endswith("_displayed")]


def test_an_exercise_with_a_flowchart_keeps_its_marker_and_replays() -> None:
    card = _exercise({**valid("method"), "hidden": ["sa", "sg"]})
    assert marker_for("display_board", {"card": card}) == "exercice posé"
    stored = StoredEntry.of(ToolEntry(kind="tool", name="display_board", arguments={"card": card}))
    assert stored.marker == "exercice posé"
    assert stored.arguments == {"card": card}
    assert StoredEntry.model_validate(stored.model_dump()) == stored
