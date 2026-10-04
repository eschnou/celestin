from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.board import BoardCard, ExerciseCard, ExplanationCard, WorkedExampleCard
from app.domain.chart import ChartBlock
from app.domain.flowchart import FlowchartBlock
from tests.unit.test_chart_models import VALID as CHARTS

ADAPTER = TypeAdapter(FlowchartBlock)
CARD: TypeAdapter[Any] = TypeAdapter(BoardCard)

# Shared by the other flowchart tests. `method` is chapter 1's 6.3.1 as the pack
# gives it: the question after the quotient has a single « oui » exit, because the
# pack says nothing of « ni SA ni SG ».
VALID: dict[str, dict[str, Any]] = {
    "method": {
        "type": "flowchart",
        "nodes": [
            {"id": "diff", "text": "Calculer les différences entre termes consécutifs", "next": [{"to": "d1"}]},
            {
                "id": "d1",
                "kind": "decision",
                "text": "Sont-elles égales ?",
                "next": [{"to": "sa", "label": "oui"}, {"to": "quot", "label": "non"}],
            },
            {"id": "sa", "text": "C'est une SA"},
            {"id": "quot", "text": "Calculer les quotients entre termes consécutifs", "next": [{"to": "d2"}]},
            {"id": "d2", "kind": "decision", "text": "Sont-ils égaux ?", "next": [{"to": "sg", "label": "oui"}]},
            {"id": "sg", "text": "C'est une SG"},
        ],
        "caption": "SA ou SG ?",
    },
    "loop": {
        "type": "flowchart",
        "nodes": [
            {"id": "debut", "kind": "start", "text": "Début", "next": [{"to": "lire"}]},
            {"id": "lire", "kind": "io", "text": "Lire $n$", "next": [{"to": "init"}]},
            {"id": "init", "text": r"$S \leftarrow 0$ ; $i \leftarrow 1$", "next": [{"to": "test"}]},
            {
                "id": "test",
                "kind": "decision",
                "text": r"$i \leqslant n$ ?",
                "next": [{"to": "ajout", "label": "oui"}, {"to": "afficher", "label": "non"}],
            },
            {"id": "ajout", "text": r"$S \leftarrow S + u_i$", "next": [{"to": "incr"}]},
            {"id": "incr", "text": r"$i \leftarrow i + 1$", "next": [{"to": "test"}]},
            {"id": "afficher", "kind": "io", "text": "Afficher $S$", "next": [{"to": "fin"}]},
            {"id": "fin", "kind": "end", "text": "Fin"},
        ],
    },
    "nested": {
        "type": "flowchart",
        "nodes": [
            {"id": "calc", "text": r"Calculer $\Delta$", "next": [{"to": "d1"}]},
            {
                "id": "d1",
                "kind": "decision",
                "text": r"$\Delta > 0$ ?",
                "next": [{"to": "two", "label": "oui"}, {"to": "d2", "label": "non"}],
            },
            {"id": "two", "text": "Deux solutions"},
            {
                "id": "d2",
                "kind": "decision",
                "text": r"$\Delta = 0$ ?",
                "next": [{"to": "one", "label": "oui"}, {"to": "zero", "label": "non"}],
            },
            {"id": "one", "text": "Une solution"},
            {"id": "zero", "text": "Pas de solution"},
        ],
    },
}


def valid(name: str) -> dict[str, Any]:
    return copy.deepcopy(VALID[name])


def _refused(block: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(block)


@pytest.mark.parametrize("name", sorted(VALID))
def test_each_valid_flowchart_validates_and_round_trips(name: str) -> None:
    block = ADAPTER.validate_python(VALID[name])
    assert block.type == "flowchart"
    assert ADAPTER.validate_python(block.model_dump()) == block


def test_the_defaults_cover_the_common_case() -> None:
    block = ADAPTER.validate_python(
        {"type": "flowchart", "nodes": [{"id": "a", "text": "A", "next": [{"to": "b"}]}, {"id": "b", "text": "B"}]}
    )
    first, second = block.nodes
    assert (first.kind, second.next, first.next[0].label) == ("step", [], None)
    assert (block.path, block.hidden, block.caption) == ([], [], None)


def test_an_unknown_kind_is_refused() -> None:
    bad = valid("method")
    bad["nodes"][0]["kind"] = "loop"
    _refused(bad)


def test_sizes_are_bounded() -> None:
    node = {"id": "a", "text": "A"}
    _refused({"type": "flowchart", "nodes": [node]})
    _refused({"type": "flowchart", "nodes": [{"id": f"n{i}", "text": "A"} for i in range(13)]})
    for field, value in (("text", ""), ("text", "x" * 81), ("id", "x" * 17)):
        bad = valid("method")
        bad["nodes"][2][field] = value
        _refused(bad)
    bad = valid("method")
    bad["nodes"][1]["next"][0]["label"] = "x" * 17
    _refused(bad)
    bad = valid("method")
    bad["nodes"][1]["next"].append({"to": "sg", "label": "peut-être"})
    _refused(bad)
    _refused({**valid("method"), "hidden": ["diff", "d1", "sa", "quot", "d2"]})
    _refused({**valid("method"), "path": ["diff"] * 25})
    _refused({**valid("method"), "caption": "x" * 201})


def test_the_maximum_sizes_are_accepted() -> None:
    twelve = ADAPTER.validate_python({"type": "flowchart", "nodes": [{"id": f"n{i}", "text": "A"} for i in range(12)]})
    assert len(twelve.nodes) == 12
    at_most = valid("method")
    at_most["nodes"][2]["text"] = "x" * 80
    at_most["nodes"][2]["id"] = "i" * 16
    at_most["nodes"][1]["next"] = [{"to": "i" * 16, "label": "l" * 16}, {"to": "quot", "label": "non"}]
    at_most["path"] = ["diff"] * 24
    at_most["hidden"] = ["diff", "d1", "quot", "d2"]
    at_most["caption"] = "c" * 200
    block = ADAPTER.validate_python(at_most)
    assert (len(block.nodes[2].text), len(block.nodes[2].id)) == (80, 16)
    assert block.nodes[1].next[0].label == "l" * 16
    assert (len(block.path), len(block.hidden), len(block.caption or "")) == (24, 4, 200)


def test_type_is_required() -> None:
    bad = valid("method")
    del bad["type"]
    _refused(bad)


def test_no_geometry_and_no_style() -> None:
    bad = valid("method")
    bad["nodes"][0]["x"] = 10
    _refused(bad)
    _refused({**valid("method"), "color": "red"})


def test_a_flowchart_is_an_explanation_block() -> None:
    card = CARD.validate_python({"kind": "explanation", "title": "Méthode", "blocks": [VALID["method"]]})
    assert isinstance(card, ExplanationCard)
    assert isinstance(card.blocks[0], FlowchartBlock)


def test_a_flowchart_is_a_drawing() -> None:
    worked = CARD.validate_python(
        {
            "kind": "worked_example",
            "title": "Méthode",
            "statement": "3 ; 6 ; 12",
            "drawing": VALID["method"],
            "steps": [{"tex": "6 - 3 \\neq 12 - 6"}],
        }
    )
    exercise = CARD.validate_python(
        {"kind": "exercise", "title": "Méthode", "statement": "Suis l'organigramme.", "drawing": VALID["loop"]}
    )
    assert isinstance(worked, WorkedExampleCard) and isinstance(worked.drawing, FlowchartBlock)
    assert isinstance(exercise, ExerciseCard) and isinstance(exercise.drawing, FlowchartBlock)
    assert CARD.validate_python(exercise.model_dump()) == exercise


@pytest.mark.parametrize("tagged", [True, False])
def test_a_chart_drawing_still_reads_as_a_chart(tagged: bool) -> None:
    """008 let a chart drawing leave out `type`; it still does."""
    drawing: dict[str, Any] = {"chart": CHARTS["sticks"]}
    if tagged:
        drawing["type"] = "chart"
    card = CARD.validate_python(
        {"kind": "exercise", "title": "Lecture", "statement": "Quel est le mode ?", "drawing": drawing}
    )
    assert isinstance(card.drawing, ChartBlock)


def test_cards_without_a_drawing_are_unchanged() -> None:
    card = CARD.validate_python({"kind": "exercise", "title": "Calcul", "statement": "Calcule $u_3$."})
    assert card.drawing is None
    assert card.model_dump()["drawing"] is None


def test_a_bad_node_in_a_drawing_is_located_under_flowchart() -> None:
    drawing = valid("loop")
    drawing["nodes"][0]["kind"] = "loop"
    with pytest.raises(ValidationError) as exc:
        CARD.validate_python({"kind": "exercise", "title": "Boucle", "statement": "Suis-le.", "drawing": drawing})
    locs = [error["loc"] for error in exc.value.errors()]
    assert any("flowchart" in loc and "kind" in loc for loc in locs), locs
