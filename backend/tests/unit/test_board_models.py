from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.board import BoardCard
from app.domain.chart import ChartBlock
from app.domain.figure import FigureBlock
from app.domain.flowchart import FlowchartBlock
from app.domain.plot import PlotBlock
from tests.unit.test_chart_models import VALID as CHARTS
from tests.unit.test_figure_models import VALID as FIGURES
from tests.unit.test_flowchart_models import VALID as FLOWCHARTS
from tests.unit.test_plot_models import VALID as PLOTS

ADAPTER = TypeAdapter(BoardCard)

VALID = {
    "title": {"kind": "title", "eyebrow": "5e secondaire", "title": "Suites", "objective": "Objectif"},
    "explanation": {
        "kind": "explanation",
        "title": "Somme d'une SG",
        "blocks": [
            {"type": "text", "text": "Dans une SG de raison $q$ :"},
            {"type": "quote", "tex": "S_n = u_1\\frac{1-q^n}{1-q}", "caption": "formule du cours"},
            {"type": "quote", "text": "Une suite arithmétique est…", "caption": "définition du cours"},
            {"type": "note", "label": "Attention", "text": "q ≠ 1"},
            {"type": "formula", "tex": "S_n = n \\cdot u_1"},
            {
                "type": "definition",
                "entries": [{"term": "raison", "text": "Le nombre $q$ est appelé raison."}],
            },
        ],
    },
    "worked_example": {
        "kind": "worked_example",
        "title": "1 + 2 + … + 2^10",
        "statement": "Calcule la somme",
        "steps": [{"tex": "u_1 = 1"}, {"tex": "q = 2", "note": "la raison"}],
    },
    "exercise": {"kind": "exercise", "title": "Le manuel", "statement": "Combien vaut-il ?", "hint": None},
    "check_question": {
        "kind": "check_question",
        "question": "Pourquoi $q \\neq 1$ ?",
        "options": [{"id": "a", "text": "Division par zéro"}, {"id": "b", "text": "Autre"}],
        "correct_option_id": "a",
        "feedback": "Exact.",
    },
    "recap": {"kind": "recap", "acquired": ["Sn d'une SG"], "watch": ["l'indice"], "next": "Les limites"},
}


@pytest.mark.parametrize("kind", sorted(VALID))
def test_each_kind_parses(kind: str) -> None:
    assert ADAPTER.validate_python(VALID[kind]).kind == kind


def test_check_question_needs_two_to_four_options() -> None:
    one = {**VALID["check_question"], "options": [{"id": "a", "text": "x"}]}
    five = {
        **VALID["check_question"],
        "options": [{"id": c, "text": "x"} for c in "abcde"],
        "correct_option_id": "a",
    }
    for payload in (one, five):
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(payload)


def test_correct_option_must_exist() -> None:
    with pytest.raises(ValidationError, match="correct_option_id"):
        ADAPTER.validate_python({**VALID["check_question"], "correct_option_id": "zzz"})


def test_option_ids_must_be_unique() -> None:
    payload = {
        **VALID["check_question"],
        "options": [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}],
    }
    with pytest.raises(ValidationError, match="unique"):
        ADAPTER.validate_python(payload)


def test_steps_bounded() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**VALID["worked_example"], "steps": []})
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(
            {**VALID["worked_example"], "steps": [{"tex": f"s{i}"} for i in range(9)]}
        )


def test_empty_strings_rejected() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**VALID["title"], "title": ""})


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({**VALID["title"], "surprise": 1})


def test_a_quote_takes_exactly_one_body() -> None:
    """Prose in `tex` is the failure that matters: KaTeX detaches every accent."""
    both = {"type": "quote", "text": "une définition", "tex": "S_n", "caption": "c"}
    neither = {"type": "quote", "caption": "c"}
    for block in (both, neither):
        with pytest.raises(ValidationError, match="exactly one"):
            ADAPTER.validate_python({**VALID["explanation"], "blocks": [block]})


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"kind": "nope"})


def test_a_definition_block_holds_one_to_six_entries() -> None:
    entry = {"term": "population", "text": "Une population est un ensemble d'individus."}
    for entries in ([], [entry] * 7):
        with pytest.raises(ValidationError):
            ADAPTER.validate_python(
                {**VALID["explanation"], "blocks": [{"type": "definition", "entries": entries}]}
            )


CHART = {"type": "chart", "chart": CHARTS["sticks"]}


def test_a_chart_goes_in_an_explanation_and_as_a_drawing() -> None:
    explanation = ADAPTER.validate_python({**VALID["explanation"], "blocks": [CHART]})
    worked = ADAPTER.validate_python({**VALID["worked_example"], "drawing": CHART})
    exercise = ADAPTER.validate_python({**VALID["exercise"], "drawing": CHART})
    assert explanation.blocks[0].chart.kind == "sticks"  # type: ignore[union-attr]
    assert worked.drawing.chart.kind == exercise.drawing.chart.kind == "sticks"  # type: ignore[union-attr]


def test_cards_without_a_drawing_still_validate() -> None:
    for kind in ("worked_example", "exercise"):
        assert ADAPTER.validate_python(VALID[kind]).drawing is None  # type: ignore[union-attr]


# --- the drawing blocks after 008: flowchart, figure, plot -------------------

DRAWINGS: dict[str, tuple[dict[str, Any], type]] = {
    "chart": (CHART, ChartBlock),
    "flowchart": (FLOWCHARTS["method"], FlowchartBlock),
    "figure": ({"type": "figure", "figure": FIGURES["plane"]}, FigureBlock),
    "plot": (PLOTS["parabola"], PlotBlock),
}


@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_each_drawing_block_goes_in_an_explanation(name: str) -> None:
    block, model = DRAWINGS[name]
    card = ADAPTER.validate_python({**VALID["explanation"], "blocks": [{"type": "text", "text": "Voici :"}, block]})
    assert isinstance(card.blocks[1], model)  # type: ignore[union-attr]
    assert ADAPTER.validate_python(card.model_dump()) == card


@pytest.mark.parametrize("kind", ["worked_example", "exercise"])
@pytest.mark.parametrize("name", sorted(DRAWINGS))
def test_each_drawing_block_is_a_drawing(name: str, kind: str) -> None:
    block, model = DRAWINGS[name]
    card = ADAPTER.validate_python({**VALID[kind], "drawing": block})
    assert isinstance(card.drawing, model)  # type: ignore[union-attr]
    # A stored card replays: its dump reads back as the same drawing.
    assert card.model_dump()["drawing"]["type"] == name  # type: ignore[union-attr]
    assert ADAPTER.validate_python(card.model_dump()) == card


@pytest.mark.parametrize("kind", ["worked_example", "exercise"])
def test_a_chart_drawing_without_type_is_still_a_chart(kind: str) -> None:
    """008 let a chart drawing leave `type` out; the callable discriminator reads a
    missing tag as a chart, so those cards keep validating."""
    card = ADAPTER.validate_python({**VALID[kind], "drawing": {"chart": CHARTS["pie"]}})
    assert isinstance(card.drawing, ChartBlock)  # type: ignore[union-attr]
    assert card.model_dump()["drawing"]["type"] == "chart"  # type: ignore[union-attr]


@pytest.mark.parametrize("kind", ["worked_example", "exercise"])
@pytest.mark.parametrize("name", ["flowchart", "figure", "plot"])
def test_a_later_drawing_without_type_is_refused_as_itself(name: str, kind: str) -> None:
    """Read from its keys, not as a chart: the one error is its own block's missing
    `type`, so the model reads what to add rather than a chart's complaints."""
    untagged = {k: v for k, v in DRAWINGS[name][0].items() if k != "type"}
    with pytest.raises(ValidationError) as exc:
        ADAPTER.validate_python({**VALID[kind], "drawing": untagged})
    assert [(error["loc"], error["type"]) for error in exc.value.errors()] == [((kind, "drawing", name, "type"), "missing")]


@pytest.mark.parametrize(
    "drawing,member",
    [
        ({"chart": {}}, "chart"),
        ({"figure": {}}, "figure"),
        ({"nodes": []}, "flowchart"),
        ({"x_range": [0, 1]}, "plot"),
        ({"y_range": [0, 1]}, "plot"),
        ({"curves": []}, "plot"),
        # Nothing tells: a chart, as under 008.
        ({}, "chart"),
        ({"bars": 3}, "chart"),
        # The chart key wins over another block's.
        ({"chart": {}, "nodes": []}, "chart"),
    ],
)
def test_a_drawing_without_type_is_read_from_its_keys(drawing: dict[str, Any], member: str) -> None:
    with pytest.raises(ValidationError) as exc:
        ADAPTER.validate_python({**VALID["exercise"], "drawing": drawing})
    assert {error["loc"][:3] for error in exc.value.errors()} == {("exercise", "drawing", member)}


@pytest.mark.parametrize("tag", ["diagram", "Chart", None])
def test_an_unknown_drawing_type_is_refused(tag: str | None) -> None:
    with pytest.raises(ValidationError) as exc:
        ADAPTER.validate_python({**VALID["exercise"], "drawing": {"type": tag, "chart": CHARTS["sticks"]}})
    assert exc.value.errors()[0]["type"] in {"union_tag_invalid", "union_tag_not_found"}


def test_an_unknown_block_type_is_refused_in_an_explanation() -> None:
    with pytest.raises(ValidationError) as exc:
        ADAPTER.validate_python({**VALID["explanation"], "blocks": [{"type": "diagram", "chart": CHARTS["sticks"]}]})
    assert exc.value.errors()[0]["type"] == "union_tag_invalid"


def test_the_wire_layer_re_exports_every_drawing_model() -> None:
    """The schema layer re-exports the card models rather than duplicating them: every
    public model of a drawing block, down to its parts, is reachable from it."""
    import inspect

    from pydantic import BaseModel

    from app.api.schemas import board as wire
    from app.domain import chart, figure, flowchart, plot

    for module in (chart, figure, flowchart, plot):
        models = [
            name
            for name, value in vars(module).items()
            if inspect.isclass(value)
            and issubclass(value, BaseModel)
            and value.__module__ == module.__name__
            and not name.startswith("_")
        ]
        assert models, module.__name__
        for name in models:
            assert name in wire.__all__, f"{module.__name__}.{name}"
            assert getattr(wire, name) is getattr(module, name)
    for union in ("Chart", "Figure", "Drawing"):
        assert union in wire.__all__
