"""Which strings of a card are prose, and the one walk that checks them all.

The card models mark every field that is not prose (`NOT_PROSE`, see
`app/domain/prose.py`), a Literal being none by itself; `display_board`'s string
checks read those marks off the parsed card, whatever a field is called.
"""

from __future__ import annotations

import json
import re
import typing
from collections.abc import Iterator
from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, Field

from app.domain.board import BoardCard
from app.domain.errors import ToolValidationError
from app.domain.prose import NOT_PROSE, NotProse
from app.services.tools import board as board_tools
from app.services.tools import registry
from app.services.tools.board import BoardSet
from tests.fixtures.curricula import ctx_for
from tests.unit.test_flowchart_models import VALID as FLOWCHARTS
from tests.unit.test_plot_models import VALID as PLOTS

CTX = ctx_for()
SCRIPT = "Un indice ou un exposant hors de $…$ s'affiche tel quel"
LATEX = "Du LaTeX hors de $…$ s'affiche tel quel"


def _models(annotation: Any) -> Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for arg in typing.get_args(annotation):
        yield from _models(arg)


def _card_models() -> dict[str, type[BaseModel]]:
    """Every model a board card can hold, by name."""
    found: dict[str, type[BaseModel]] = {}

    def visit(model: type[BaseModel]) -> None:
        if model.__name__ not in found:
            found[model.__name__] = model
            for field in model.model_fields.values():
                for inner in _models(field.annotation):
                    visit(inner)

    for model in _models(BoardCard):
        visit(model)
    return found


# The fields whose strings are not prose, model by model: the marked ones (raw
# LaTeX, ids, an expression) and the Literals. A new model or field lands here on
# purpose, by deciding whether the model writes prose in it.
NOT_PROSE_FIELDS: dict[str, set[str]] = {
    "TitleCard": {"kind"},
    "ExplanationCard": {"kind"},
    "TextBlock": {"type"},
    "FormulaBlock": {"tex", "type"},
    "QuoteBlock": {"tex", "type"},
    "NoteBlock": {"type"},
    "DefinitionBlock": {"type"},
    "DefinitionEntry": set(),
    "ChartBlock": {"type"},
    "BarChart": {"kind", "measure"},
    "StickChart": {"kind", "measure"},
    "Histogram": {"closed", "kind", "measure", "polygon"},
    "CumulativePolygon": {"closed", "direction", "kind", "measure"},
    "PieChart": {"kind", "measure"},
    "BoxPlot": {"kind"},
    "Box": set(),
    "FlowchartBlock": {"hidden", "path", "type"},
    "FlowNode": {"id", "kind"},
    "FlowExit": {"to"},
    "FigureBlock": {"type"},
    "PlaneFigure": {"kind", "marker"},
    "FigureShape": {"draw", "of", "style"},
    "NumberLine": {"convention", "kind"},
    "LineInterval": {"closed"},
    "LineMark": set(),
    "SetDiagram": {"kind", "layout", "shade"},
    "FigureSet": {"id"},
    "SetElement": {"within"},
    "PlotBlock": {"type"},
    "PlotCurve": {"end_dot", "expr", "start_dot"},
    "PlotSequence": {"expr"},
    "PlotPoint": {"mark"},
    "PlotLine": set(),
    "WorkedExampleCard": {"kind"},
    "Step": {"tex"},
    "ExerciseCard": {"kind"},
    "CheckQuestionCard": {"correct_option_id", "kind"},
    "Option": {"id"},
    "RecapCard": {"kind"},
}


def test_every_card_model_says_which_of_its_fields_are_not_prose() -> None:
    models = _card_models()
    assert {name: set(board_tools._not_prose(model)) for name, model in models.items()} == NOT_PROSE_FIELDS


def _markers(annotation: Any) -> Iterator[NotProse]:
    """The markers anywhere in a type, however deep: in a list, an optional arm."""
    for arg in typing.get_args(annotation):
        if isinstance(arg, NotProse):
            yield arg
        yield from _markers(arg)


@pytest.mark.parametrize("name", sorted(NOT_PROSE_FIELDS))
def test_a_marker_sits_on_the_field_where_the_checks_see_it(name: str) -> None:
    """`Annotated[NonEmpty, NOT_PROSE] | None` would bury the marker in an arm: the
    field would read as prose. It goes on the field, `Annotated[NonEmpty | None, NOT_PROSE]`."""
    for field_name, field in _card_models()[name].model_fields.items():
        assert not list(_markers(field.annotation)), f"{name}.{field_name}"


def test_the_marker_adds_nothing_to_the_schema() -> None:
    """The tool declarations the model reads (and their cached prefix) do not move."""

    class Plain(BaseModel):
        tex: Annotated[str, Field(min_length=1)] | None = None
        ids: Annotated[list[str], Field(max_length=4)] = []

    class Marked(BaseModel):
        tex: Annotated[Annotated[str, Field(min_length=1)] | None, NOT_PROSE] = None
        ids: Annotated[list[str], Field(max_length=4), NOT_PROSE] = []

    plain, marked = Plain.model_json_schema(), Marked.model_json_schema()
    assert {**plain, "title": ""} == {**marked, "title": ""}


class _Named(BaseModel):
    """Field names borrowed from the card models, with the opposite meaning."""

    to: str
    label: Annotated[str, NOT_PROSE]
    shape: Literal["right_angle"] = "right_angle"
    points: dict[str, str] = {}


def test_prose_is_what_the_model_marks_not_what_a_field_is_called() -> None:
    """A prose `to` is read as prose, though a flowchart exit's `to` is an id; a
    marked field is not, whatever its name; a dict's keys are names, not text."""
    named = _Named(to="u_n", label="u_n", points={"A_1": "B"})
    assert list(board_tools._strings(named, "card")) == [
        ("card.to", "u_n", False),
        ("card.label", "u_n", True),
        ("card.shape", "right_angle", True),
        ("card.points.A_1", "B", False),
    ]
    refusal = board_tools._strings_refusal(named)  # type: ignore[arg-type]
    assert refusal is not None
    rule, message, paths = refusal
    assert (rule, paths) == ("string_script", ["card.to"])
    assert message.startswith(SCRIPT)
    assert board_tools._strings_refusal(_Named(to="uₙ", label="u_n")) is None  # type: ignore[arg-type]


def _show(card: dict[str, Any]) -> object:
    return registry.execute("display_board", json.dumps({"card": card}), CTX)


def _explanation(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "explanation", "title": "Suites", "blocks": list(blocks)}


WORKED = {"kind": "worked_example", "title": "SG", "statement": "Calcule."}


def _flowchart(**node: Any) -> dict[str, Any]:
    chart = FLOWCHARTS["method"]
    return {**chart, "nodes": [{**chart["nodes"][0], **node}, *chart["nodes"][1:]]}


# One card per marked field, holding what prose may not: raw LaTeX or a script.
# Each is accepted, and the same string in a prose field beside it is refused.
MARKED: dict[str, tuple[dict[str, Any], dict[str, Any], str]] = {
    "formula tex": (
        _explanation({"type": "formula", "tex": "u_{n+1} = q \\cdot u_n"}),
        _explanation({"type": "formula", "tex": "u_1", "caption": "u_{n+1} = q \\cdot u_n"}),
        "card.blocks[0].caption",
    ),
    "quote tex, an optional field": (
        _explanation({"type": "quote", "tex": "u_{n+1} = q \\cdot u_n", "caption": "Définition 1"}),
        _explanation({"type": "quote", "text": "u_{n+1} = q \\cdot u_n", "caption": "Définition 1"}),
        "card.blocks[0].text",
    ),
    "worked example step": (
        {**WORKED, "steps": [{"tex": "u_2 = 6"}]},
        {**WORKED, "steps": [{"tex": "u_2", "note": "u_2 = 6"}]},
        "card.steps[0].note",
    ),
    "option ids": (
        {
            "kind": "check_question",
            "question": "Quelle raison ?",
            "options": [{"id": "q_1", "text": "2"}, {"id": "q_2", "text": "3"}],
            "correct_option_id": "q_1",
            "feedback": "Divise deux termes.",
        },
        {
            "kind": "check_question",
            "question": "Quelle raison ?",
            "options": [{"id": "a", "text": "q_1"}, {"id": "b", "text": "3"}],
            "correct_option_id": "a",
            "feedback": "Divise deux termes.",
        },
        "card.options[0].text",
    ),
    "flowchart node id": (
        _explanation(_flowchart(id="u_n")),
        _explanation(_flowchart(text="u_n")),
        "card.blocks[0].nodes[0].text",
    ),
    "plot expression": (
        _explanation({**PLOTS["parabola"], "curves": [{"expr": "x^2 - 1"}]}),
        _explanation({**PLOTS["parabola"], "curves": [{"expr": "x*x - 1", "label": "x^2 - 1"}]}),
        "card.blocks[0].curves[0].label",
    ),
}


@pytest.mark.parametrize("case", sorted(MARKED))
def test_a_marked_field_is_not_read_as_prose(case: str) -> None:
    accepted, refused, path = MARKED[case]
    assert isinstance(_show(accepted), BoardSet)
    with pytest.raises(ToolValidationError) as exc:
        _show(refused)
    assert re.search(rf" : {re.escape(path)} \(", exc.value.message), exc.value.message


def test_the_card_is_walked_once_and_its_maths_taken_out_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whichever check refuses, one walk runs them all: the card is walked once, and
    each prose string has its `$…$` taken out once for the two checks that need it."""
    walks: list[str] = []
    subs: list[str] = []
    walk, math = board_tools._strings, board_tools.MATH

    def counted_walk(value: Any, path: str, raw: bool = False) -> Iterator[tuple[str, str, bool]]:
        if path == "card":
            walks.append(path)
        return walk(value, path, raw)

    class CountedMath:
        def sub(self, repl: str, text: str) -> str:
            subs.append(text)
            return math.sub(repl, text)

    monkeypatch.setattr(board_tools, "_strings", counted_walk)
    monkeypatch.setattr(board_tools, "MATH", CountedMath())
    card = _explanation(
        {"type": "text", "text": "La suite u_n"},
        {"type": "formula", "tex": "u_n", "caption": "Terme $u_n$"},
        {"type": "note", "label": "Attention", "text": "Pas de \\dots"},
    )
    with pytest.raises(ToolValidationError) as exc:
        _show(card)
    # LaTeX comes before scripts: the \dots is named, the u_n is not.
    assert exc.value.message == f"{LATEX} : mets-le entre $…$ ou dans un champ tex : card.blocks[2].text (\\dots)"
    assert walks == ["card"]
    assert subs == ["Suites", "La suite u_n", "Terme $u_n$", "Attention", "Pas de \\dots"]
