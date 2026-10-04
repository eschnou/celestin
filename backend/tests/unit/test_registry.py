from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from app.domain.errors import ToolValidationError
from app.services.tools import registry
from app.domain.board import marker_for
from app.services.tools.board import BoardCleared, BoardSet, DisplayBoardArgs
from tests.fixtures.curricula import ctx_for
from tests.unit.test_chart_models import VALID as CHARTS
from tests.unit.test_figure_models import VALID as FIGURES
from tests.unit.test_flowchart_models import VALID as FLOWCHARTS
from tests.unit.test_plot_models import VALID as PLOTS

CTX = ctx_for()

CARD = {
    "kind": "explanation",
    "title": "Somme d'une SG",
    "blocks": [{"type": "text", "text": "Bonjour"}],
}


def test_declaration_order_is_stable() -> None:
    names = [t["name"] for t in registry.declarations()]
    assert names == [
        "display_board",
        "clear_board",
        "start_section",
        "complete_section",
        "propose_next_step",
    ]
    assert [t["name"] for t in registry.declarations()] == names


def test_declarations_carry_strict_flags() -> None:
    by_name = {t["name"]: t for t in registry.declarations()}
    assert by_name["display_board"]["strict"] is False
    assert by_name["clear_board"]["strict"] is True
    assert by_name["start_section"]["strict"] is True
    assert by_name["complete_section"]["strict"] is True
    assert by_name["display_board"]["type"] == "function"


def test_board_declarations_did_not_move(snapshot_declarations) -> None:
    """The board tools' bytes sit in the cached prefix; adding section tools after
    them must not change them (002 R4.5)."""
    current = registry.declarations()[:2]
    assert json.dumps(current, ensure_ascii=False, sort_keys=True) == snapshot_declarations


def test_display_board_dispatches() -> None:
    out = registry.execute("display_board", json.dumps({"card": CARD}), CTX)
    assert isinstance(out, BoardSet)
    assert out.card.kind == "explanation"
    assert out.marker == "explication affichée"


def test_clear_board_dispatches() -> None:
    out = registry.execute("clear_board", "{}", CTX)
    assert isinstance(out, BoardCleared)
    assert out.marker == "tableau effacé"


def test_invalid_arguments_name_the_field() -> None:
    bad = {"card": {**CARD, "blocks": []}}
    with pytest.raises(ToolValidationError) as exc:
        registry.execute("display_board", json.dumps(bad), CTX)
    assert "blocks" in exc.value.message


def test_latex_outside_dollars_in_prose_is_a_tool_error() -> None:
    bad = {
        "card": {
            **CARD,
            "blocks": [{"type": "formula", "tex": "u_n=n", "caption": "Exemple : 1 ; 2 ; 3 ; \\dots"}],
        }
    }
    with pytest.raises(ToolValidationError) as exc:
        registry.execute("display_board", json.dumps(bad), CTX)
    assert "card.blocks[0].caption (\\dots)" in exc.value.message


@pytest.mark.parametrize(
    "caption",
    ["Exemple : $1 ; 2 ; 3 ; \\dots$", "de $$S_n=\\frac{a}{b}$$ à 30 €", "Exemple : 1 ; 2 ; 3 ; …"],
)
def test_latex_inside_dollars_or_plain_prose_is_accepted(caption: str) -> None:
    card = {**CARD, "blocks": [{"type": "formula", "tex": "u_n=n \\dots", "caption": caption}]}
    assert isinstance(registry.execute("display_board", json.dumps({"card": card}), CTX), BoardSet)


PACK = """### 1.1 Population

> Une **population** est un ensemble d’individus ayant des caractéristiques propres
> et sur lesquels portent les observations.

> Un individu est un élément de la population.

> Une suite arithmétique est une suite telle que $u_{n+1} = u_n + r$ pour tout $n \\in ℕ_0$.
"""


def _definitions(*entries: tuple[str, str]) -> str:
    card = {
        **CARD,
        "blocks": [
            {"type": "definition", "entries": [{"term": t, "text": x} for t, x in entries]}
        ],
    }
    return json.dumps({"card": card})


@pytest.mark.parametrize(
    "term,text",
    [
        # Apostrophe, emphasis and line breaks differ from the pack; the wording does not.
        (
            "Population",
            "Une population est un ensemble d'individus ayant des caractéristiques "
            "propres et sur lesquels portent les observations.",
        ),
        ("individu", "Un  individu est un élément de la population"),
        # Notation may differ: Unicode against LaTeX.
        ("suite arithmétique", "Une suite arithmétique est une suite telle que uₙ₊₁ = uₙ + r pour tout n ∈ ℕ₀."),
    ],
)
def test_a_definition_quoted_from_the_pack_is_accepted(term: str, text: str) -> None:
    ctx = replace(CTX, pack=PACK)
    assert isinstance(registry.execute("display_board", _definitions((term, text)), ctx), BoardSet)


def test_a_definition_not_in_the_pack_is_a_tool_error() -> None:
    ctx = replace(CTX, pack=PACK)
    reworded = ("individu", "Un individu est une personne de la population.")
    with pytest.raises(ToolValidationError) as exc:
        registry.execute("display_board", _definitions(reworded), ctx)
    assert "« individu »" in exc.value.message
    assert "bloc text" in exc.value.message


def test_a_definition_must_contain_its_term() -> None:
    ctx = replace(CTX, pack=PACK)
    elsewhere = ("échantillon", "Un individu est un élément de la population.")
    with pytest.raises(ToolValidationError, match="n'apparaît pas"):
        registry.execute("display_board", _definitions(elsewhere), ctx)


def test_without_a_pack_only_the_term_is_checked() -> None:
    free = ("variable", "Une variable est ce que l'on observe.")
    assert isinstance(registry.execute("display_board", _definitions(free), CTX), BoardSet)


STICKS = {"type": "chart", "chart": CHARTS["sticks"]}


def _with_blocks(*blocks: dict) -> str:
    return json.dumps({"card": {**CARD, "blocks": list(blocks)}})


def test_a_chart_on_the_board_dispatches_and_logs_its_kind(caplog: pytest.LogCaptureFixture) -> None:
    ctx = replace(CTX, user_id="u1", chapter_id="c1")
    with caplog.at_level(logging.INFO, logger="app.services.tools.board"):
        out = registry.execute("display_board", _with_blocks(STICKS), ctx)
    assert isinstance(out, BoardSet)
    record = next(r for r in caplog.records if r.message == "chart_displayed")
    assert (record.user_id, record.chapter_id, record.mode, record.kinds) == (  # type: ignore[attr-defined]
        "u1",
        "c1",
        "parcours",
        ["sticks"],
    )


def test_a_chart_is_accepted_as_a_drawing() -> None:
    card = {
        "kind": "exercise",
        "title": "Lecture",
        "statement": "Quel est le mode ?",
        "drawing": STICKS,
    }
    assert isinstance(registry.execute("display_board", json.dumps({"card": card}), CTX), BoardSet)


def test_a_broken_chart_is_refused_and_logged_without_its_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = {**STICKS, "chart": {**STICKS["chart"], "x": [12, 16, 14]}}
    with caplog.at_level(logging.INFO, logger="app.services.tools.board"):
        with pytest.raises(ToolValidationError) as exc:
            registry.execute("display_board", _with_blocks({"type": "text", "text": "Vois :"}, broken), CTX)
    assert exc.value.message.startswith("Le graphique blocks[1]")
    record = next(r for r in caplog.records if r.message == "chart_refused")
    assert record.rule == "order"  # type: ignore[attr-defined]
    logged = " ".join(str(v) for v in record.__dict__.values())
    assert "Note" not in logged and "Effectifs" not in logged


def test_an_open_exercise_may_not_write_its_chart_values() -> None:
    shown = {"type": "chart", "chart": {**CHARTS["sticks"], "show_values": True}}
    card = {"kind": "exercise", "title": "Lecture", "statement": "Quel est le mode ?", "drawing": shown}
    with pytest.raises(ToolValidationError, match="show_values reste à false"):
        registry.execute("display_board", json.dumps({"card": card}), CTX)
    # A worked example, or an explanation, may write them.
    worked = {"kind": "worked_example", "title": "Le mode", "statement": "Lis.", "drawing": shown, "steps": [{"tex": "Mo = 14"}]}
    assert isinstance(registry.execute("display_board", json.dumps({"card": worked}), CTX), BoardSet)


def test_a_chart_the_card_model_refuses_is_counted_too(caplog: pytest.LogCaptureFixture) -> None:
    negative = {"type": "chart", "chart": {**CHARTS["sticks"], "values": [2, -5, 3]}}
    with caplog.at_level(logging.INFO, logger="app.services.tools.board"):
        with pytest.raises(ToolValidationError, match="Arguments invalides"):
            registry.execute("display_board", _with_blocks(negative), CTX)
    record = next(r for r in caplog.records if r.message == "chart_refused")
    assert record.rule == "schema.greater_than_equal"  # type: ignore[attr-defined]


def test_a_refused_card_without_a_chart_logs_no_chart_refusal(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.services.tools.board"):
        with pytest.raises(ToolValidationError):
            registry.execute("display_board", json.dumps({"card": {**CARD, "blocks": []}}), CTX)
    assert not [r for r in caplog.records if r.message == "chart_refused"]


def test_a_third_chart_on_one_card_is_refused() -> None:
    # The cross-family cap (two drawings of any kind) is reached first.
    with pytest.raises(ToolValidationError, match="au plus 2 dessins"):
        registry.execute("display_board", _with_blocks(STICKS, STICKS, STICKS), CTX)


def test_latex_outside_dollars_in_a_chart_title_is_refused() -> None:
    bad = {**STICKS, "chart": {**STICKS["chart"], "y_title": "Effectifs \\frac{n}{N}"}}
    with pytest.raises(ToolValidationError, match="y_title"):
        registry.execute("display_board", _with_blocks(bad), CTX)


# --- every drawing family through display_board ------------------------------

LOGGER = "app.services.tools.board"
WHO = replace(CTX, user_id="u1", chapter_id="c1")
# What any LogRecord carries on its own; the rest is what the handler chose to log.
_RECORD = frozenset(logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None).__dict__) | {"message", "asctime"}
IDS = {"user_id": "u1", "chapter_id": "c1", "mode": "parcours"}

FIGURE = {"type": "figure", "figure": FIGURES["plane"]}
FLOWCHART = FLOWCHARTS["method"]
PLOT = PLOTS["parabola"]

# How each string check's message starts; the paths follow, after « : ».
CONTROL = (
    "Un caractère de contrôle a pris la place d'une barre oblique : dans le JSON, "
    "une commande LaTeX s'écrit avec deux barres (\\\\frac, \\\\text)"
)
LATEX = "Du LaTeX hors de $…$ s'affiche tel quel : mets-le entre $…$ ou dans un champ tex"
SCRIPT = "Un indice ou un exposant hors de $…$ s'affiche tel quel : mets-le entre $…$ ou dans un champ tex"


def _extra(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in record.__dict__.items() if key not in _RECORD}


def _records(caplog: pytest.LogCaptureFixture, suffix: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.message.endswith(suffix)]


def _explanation(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {**CARD, "blocks": list(blocks)}


def _worked(drawing: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "worked_example", "title": "Exemple", "statement": "Lis.", "drawing": drawing, "steps": [{"tex": "x"}]}


def _exercise(drawing: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "exercise", "title": "Exercice", "statement": "Cherche.", "drawing": drawing}


def _show(card: dict[str, Any]) -> Any:
    return registry.execute("display_board", json.dumps({"card": card}), WHO)


def _refused(card: dict[str, Any]) -> str:
    with pytest.raises(ToolValidationError) as exc:
        _show(card)
    return exc.value.message


# Where a drawing can sit: among an explanation's blocks, or as a card's `drawing`.
PLACES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "explanation": _explanation,
    "worked_example": _worked,
    "exercise": _exercise,
}

# Each family's display: its block, and what `<type>_displayed` logs beside the ids.
DISPLAYED: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "chart": (STICKS, {"kinds": ["sticks"]}),
    "flowchart": (FLOWCHART, {"nodes": [6], "hidden": 0, "path": False}),
    "figure": (FIGURE, {"kinds": ["plane"]}),
    "plot": (
        PLOT,
        {"count": 1, "layers": {"curves": 1, "sequences": 0, "points": 1, "lines": 0}, "functions": []},
    ),
}


@pytest.mark.parametrize("where", sorted(PLACES))
@pytest.mark.parametrize("name", sorted(DISPLAYED))
def test_each_drawing_dispatches_and_logs_ids_and_counts_only(
    name: str, where: str, caplog: pytest.LogCaptureFixture
) -> None:
    block, summary = DISPLAYED[name]
    if where == "exercise" and name == "plot":
        # An open exercise may not write a point's values: the same plot without them.
        block = {**block, "points": [{**block["points"][0], "show_values": False}]}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        out = _show(PLACES[where](block))
    assert isinstance(out, BoardSet)
    [record] = _records(caplog, "_displayed")
    assert record.message == f"{name}_displayed"
    # Exactly the ids and the family's counts: no label, text, expression or coordinate.
    assert _extra(record) == {**IDS, **summary}
    assert not _records(caplog, "_refused")


def _not_right() -> dict[str, Any]:
    figure = copy.deepcopy(FIGURE)
    figure["figure"]["points"]["C"] = [1, 3]  # the right-angle mark at A is now false
    return figure


def _unknown_exit() -> dict[str, Any]:
    flowchart = copy.deepcopy(FLOWCHART)
    flowchart["nodes"][0]["next"] = [{"to": "zz"}]
    return flowchart


# One tool rule per family, with the start of its message.
TOOL_REFUSALS: dict[str, tuple[dict[str, Any], str, str]] = {
    "chart": ({**STICKS, "chart": {**STICKS["chart"], "x": [12, 16, 14]}}, "order", "Le graphique blocks[0]"),
    "flowchart": (_unknown_exit(), "unknown_id", "L'organigramme blocks[0]"),
    "figure": (_not_right(), "not_right", "La figure blocks[0]"),
    "plot": ({**PLOT, "x_range": [4, -4]}, "window", "Le graphique blocks[0]"),
}


@pytest.mark.parametrize("name", sorted(TOOL_REFUSALS))
def test_each_drawing_logs_the_rule_that_refused_it_and_nothing_else(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    block, rule, start = TOOL_REFUSALS[name]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(_explanation(block))
    assert message.startswith(start)
    [record] = _records(caplog, "_refused")
    assert record.message == f"{name}_refused"
    assert _extra(record) == {**IDS, "rule": rule}
    assert not _records(caplog, "_displayed")


def _bad_node_kind() -> dict[str, Any]:
    flowchart = copy.deepcopy(FLOWCHART)
    flowchart["nodes"][0]["kind"] = "loop"
    return flowchart


# One card-model refusal per family: counted by `on_invalid` under the Pydantic type.
SCHEMA_REFUSALS: dict[str, tuple[dict[str, Any], str]] = {
    "chart": ({**STICKS, "chart": {**STICKS["chart"], "values": [2, -5, 3]}}, "greater_than_equal"),
    "flowchart": (_bad_node_kind(), "literal_error"),
    "figure": ({"type": "figure", "figure": {"kind": "plane", "points": {"AB": [0, 0]}}}, "string_pattern_mismatch"),
    "plot": ({**PLOT, "x_range": [float("nan"), 4]}, "finite_number"),
}


@pytest.mark.parametrize("where", ["explanation", "exercise"])
@pytest.mark.parametrize("name", sorted(SCHEMA_REFUSALS))
def test_each_drawing_the_card_model_refuses_is_counted_under_its_family(
    name: str, where: str, caplog: pytest.LogCaptureFixture
) -> None:
    block, error = SCHEMA_REFUSALS[name]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(PLACES[where](block))
    assert message.startswith("Arguments invalides")
    [record] = _records(caplog, "_refused")
    assert record.message == f"{name}_refused"
    assert _extra(record) == {**IDS, "rule": f"schema.{error}"}


def test_a_valid_chart_beside_a_refused_figure_logs_no_display(caplog: pytest.LogCaptureFixture) -> None:
    """Every family is checked before any display is logged: the chart, first on the
    card and valid, is not counted as displayed on a card that never showed."""
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(_explanation(STICKS, _not_right()))
    assert message.startswith("La figure blocks[1]")
    assert [r.message for r in _records(caplog, "_refused")] == ["figure_refused"]
    assert not _records(caplog, "_displayed")


@pytest.mark.parametrize("pair", [("STICKS", "FLOWCHART"), ("FIGURE", "PLOT")])
def test_two_families_on_one_card_are_displayed_together(
    pair: tuple[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    blocks = {"STICKS": STICKS, "FLOWCHART": FLOWCHART, "FIGURE": FIGURE, "PLOT": PLOT}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        out = _show(_explanation(*(blocks[name] for name in pair)))
    assert isinstance(out, BoardSet)
    expected = {"STICKS": "chart", "FLOWCHART": "flowchart", "FIGURE": "figure", "PLOT": "plot"}
    logged = sorted(r.message for r in _records(caplog, "_displayed"))
    assert logged == sorted(f"{expected[name]}_displayed" for name in pair)


@pytest.mark.parametrize(
    "block,path",
    [
        (
            {"type": "figure", "figure": {**FIGURES["plane"], "caption": "Le triangle \\triangle ABC"}},
            "card.blocks[0].figure.caption (\\triangle)",
        ),
        (
            {
                "type": "figure",
                "figure": {
                    **FIGURES["plane"],
                    "shapes": [*FIGURES["plane"]["shapes"][:2], {"draw": "segment", "of": ["B", "C"], "label": "\\sqrt{25} cm"}],
                },
            },
            "card.blocks[0].figure.shapes[2].label (\\sqrt)",
        ),
        ({**PLOT, "x_title": "\\frac{t}{s}"}, "card.blocks[0].x_title (\\frac)"),
        ({**PLOT, "curves": [{"expr": "x^2-4", "label": "\\mathcal{C}_f"}]}, "card.blocks[0].curves[0].label (\\mathcal)"),
    ],
)
def test_latex_outside_dollars_in_a_figure_or_plot_text_is_refused(
    block: dict[str, Any], path: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(_explanation(block))
    assert message == f"{LATEX} : {path}"
    # Counted under the drawing it sits in, like any rule of the family's own.
    [record] = _records(caplog, "_refused")
    assert record.message == f"{block['type']}_refused"
    assert _extra(record) == {**IDS, "rule": "string_latex"}


@pytest.mark.parametrize("layer", ["curves", "sequences"])
def test_latex_in_a_plot_expression_reaches_the_plot_parser(layer: str, caplog: pytest.LogCaptureFixture) -> None:
    """`expr` is not prose: the parser's message, which says what to write instead,
    is the one the model reads."""
    plot = {**PLOT, "curves": [], "points": []}
    plot[layer] = [{"expr": "\\frac{1}{x}"} if layer == "curves" else {"expr": "\\frac{1}{n}", "last": 5}]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(_explanation(plot))
    assert not message.startswith(LATEX)
    assert "pas du LaTeX" in message
    [record] = _records(caplog, "_refused")
    assert _extra(record) == {**IDS, "rule": "expr.latex"}


def test_flowchart_node_ids_are_not_read_as_prose() -> None:
    """A node id lives in `id`, `next[].to`, `path` and `hidden`: none of them is text
    the board shows, so a backslash in one is not LaTeX outside $…$."""
    nodes = [
        {"id": "\\debut", "text": "Calculer la somme des termes", "next": [{"to": "\\fin"}]},
        {"id": "\\fin", "text": "Afficher le total obtenu"},
    ]
    walked = {"type": "flowchart", "nodes": nodes, "path": ["\\debut", "\\fin"]}
    assert isinstance(_show(_worked(walked)), BoardSet)
    hidden = {"type": "flowchart", "nodes": nodes, "hidden": ["\\fin"]}
    assert isinstance(_show(_exercise(hidden)), BoardSet)
    # A node's text is prose, though.
    bare = {"type": "flowchart", "nodes": [{**nodes[0], "text": "\\Delta"}, nodes[1]]}
    assert "card.blocks[0].nodes[0].text (\\Delta)" in _refused(_explanation(bare))


def test_unknown_tool_is_handled_not_raised_as_crash() -> None:
    with pytest.raises(ToolValidationError) as exc:
        registry.execute("teleport", "{}", CTX)
    assert "teleport" in exc.value.message
    assert "display_board" in exc.value.message


def test_malformed_json_is_a_tool_error() -> None:
    with pytest.raises(ToolValidationError, match="JSON"):
        registry.execute("display_board", "{not json", CTX)


def test_non_object_arguments_rejected() -> None:
    with pytest.raises(ToolValidationError):
        registry.execute("display_board", "[1, 2]", CTX)


def test_every_card_kind_declares_a_marker() -> None:
    """A new card kind cannot ship without its French label."""
    from typing import get_args

    from app.domain.board import BoardCard

    for card in get_args(get_args(BoardCard)[0]):
        assert card.marker, card.__name__


def test_replay_output_is_bare_for_board_tools() -> None:
    assert registry.replay_output("display_board", {"card": CARD}, CTX) == {"ok": True}
    assert registry.replay_output("clear_board", {}, CTX) == {"ok": True}


def test_replay_output_recomputes_a_section_brief() -> None:
    out = registry.replay_output("start_section", {"section_id": "intro"}, CTX)
    assert out["ok"] is True
    assert "Déroulé" in out["result"]


def test_replay_output_never_raises() -> None:
    assert "inconnue" in registry.replay_output("start_section", {"nope": 1}, CTX)["result"]
    assert registry.replay_output("teleport", {}, CTX) == {"ok": True}


def test_replayed_completion_needs_only_the_section_id() -> None:
    out = registry.replay_output("complete_section", {"section_id": "intro"}, CTX)
    assert out["ok"] is True and "Section terminée" in out["result"]


def test_realtime_declarations_are_the_same_tools_without_strict() -> None:
    """003 R2.3: one registry feeds both channels."""
    stripped = [{k: v for k, v in d.items() if k != "strict"} for d in registry.declarations()]
    assert registry.realtime_declarations() == stripped
    assert all("strict" not in d for d in registry.realtime_declarations())



# --- modes (007 §3.5) ---------------------------------------------------------


def test_discussion_declares_the_board_and_nothing_that_moves_the_path() -> None:
    names = [t["name"] for t in registry.declarations("discussion")]
    assert names == ["display_board", "clear_board"]


def test_a_modes_declarations_are_a_prefix_of_the_parcours_bytes() -> None:
    """Adding a mode must not move the bytes of a declaration it shares: both lists
    follow `_TOOLS` order, so the discussion list is the parcours list truncated."""
    parcours = registry.declarations("parcours")
    assert registry.declarations("discussion") == parcours[:2]


@pytest.mark.parametrize("mode", ["parcours", "discussion"])
def test_realtime_declarations_match_per_mode(mode: str) -> None:
    stripped = [{k: v for k, v in d.items() if k != "strict"} for d in registry.declarations(mode)]
    assert registry.realtime_declarations(mode) == stripped


@pytest.mark.parametrize("name", ["start_section", "complete_section", "propose_next_step"])
def test_a_path_tool_is_refused_in_a_discussion(name: str) -> None:
    """The gate, not the prompt: `/api/voice/tool` takes a tool name from the
    browser, so this is what makes the mode a server-side fact."""
    ctx = ctx_for(mode="discussion")
    with pytest.raises(ToolValidationError) as exc:
        registry.execute(name, json.dumps({"section_id": "intro", "summary": "x"}), ctx)
    assert "n'est pas disponible ici" in exc.value.message
    offered = exc.value.message.split("Outils disponibles : ")[1]
    assert offered.rstrip(".") == "display_board, clear_board"


def test_the_board_still_works_in_a_discussion() -> None:
    out = registry.execute("display_board", json.dumps({"card": CARD}), ctx_for(mode="discussion"))
    assert isinstance(out, BoardSet)


def test_default_mode_is_the_parcours() -> None:
    assert registry.declarations() == registry.declarations("parcours")
    assert registry.realtime_declarations() == registry.realtime_declarations("parcours")



# --- drawings across families (lead fixes after the consistency review) --------


def _refused_family(card: dict, caplog: pytest.LogCaptureFixture) -> list[tuple[str, str]]:
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.services.tools.board"):
        with pytest.raises(ToolValidationError):
            registry.execute("display_board", json.dumps({"card": card}), CTX)
    return [(r.message, r.rule) for r in caplog.records if r.message.endswith("_refused")]  # type: ignore[attr-defined]


def test_a_schema_refusal_is_counted_under_the_drawing_it_happened_in(caplog: pytest.LogCaptureFixture) -> None:
    """The family is read at the union tag's place, not from any loc element: a figure
    point named « chart » or a stray `figure` key on a plot names no family."""
    point_named_chart = {
        "kind": "exercise",
        "title": "t",
        "statement": "s",
        "drawing": {"type": "figure", "figure": {"kind": "plane", "points": {"chart": [0, 0]}}},
    }
    stray_key = {
        "kind": "explanation",
        "title": "t",
        "blocks": [{"type": "plot", "x_range": [0, 1], "y_range": [0, 1], "x_title": "x", "y_title": "y", "figure": {}}],
    }
    assert _refused_family(point_named_chart, caplog) == [("figure_refused", "schema.string_pattern_mismatch")]
    assert _refused_family(stray_key, caplog) == [("plot_refused", "schema.extra_forbidden")]


def test_a_card_holds_at_most_two_drawings_of_any_family(caplog: pytest.LogCaptureFixture) -> None:
    three = {**CARD, "blocks": [STICKS, STICKS, {"type": "chart", "chart": CHARTS["pie"]}]}
    # Three charts: the one cap is the card's, whatever the families, and no family
    # rule runs past it.
    assert _refused_family(three, caplog) == [("drawing_refused", "per_card")]
    mixed = {**CARD, "blocks": [STICKS, FIGURE, PLOT]}
    assert _refused_family(mixed, caplog) == [("drawing_refused", "per_card")]
    two = {**CARD, "blocks": [STICKS, {"type": "chart", "chart": CHARTS["pie"]}]}
    assert isinstance(registry.execute("display_board", json.dumps({"card": two}), CTX), BoardSet)



# --- strings the model wrote (after the probe run) --------------------------------

# Python reads `\n`, `\t`, `\r`, `\b` and `\f` as JSON does: each string below is
# what the model's JSON decodes to when it writes a LaTeX command with one backslash.
# (field, string, what the refusal names: the command, "" for none, None if accepted)
CONTROL_CASES: list[tuple[str, str, str | None]] = [
    # A newline is a lost `\n` where LaTeX is written, and only before a real command.
    ("text", "CE : $q \neq 1$", "\\neq"),
    ("text", "$\neq$ ici", "\\neq"),  # right after `$`, where the board would not open maths
    ("text", "$x \ne 0$", "\\ne"),
    ("text", "$x \notin A$", "\\notin"),
    ("text", "$\nu$ vaut 2", "\\nu"),
    ("text", "$\neg p$", "\\neg"),
    ("text", "$\nabla f$", "\\nabla"),
    ("text", "$a \not= b$", "\\not"),
    ("text", "$A \ni x$", "\\ni"),
    ("text", "$u_1 \nleq 3$", "\\nleq"),
    ("text", "$$a \newline b$$", "\\newline"),
    ("tex", "q \neq 1", "\\neq"),
    ("tex", "x \ngeq 0", "\\ngeq"),
    # A tab or a carriage return is lost before a command anywhere, prose included…
    ("text", "vitesse \text{ moyenne}", "\\text"),
    ("text", "3 \times 4", "\\times"),
    ("text", "de 1 \to 5", "\\to"),
    ("text", "l'angle \theta", "\\theta"),
    ("text", "donc \rightarrow fini", "\\rightarrow"),
    ("text", "la masse volumique \rho", "\\rho"),
    # …and never belongs in LaTeX, command or not.
    ("text", "$a \tb$", ""),
    ("text", "$a\r b$", ""),
    ("tex", "a\t+ b", ""),
    ("tex", "a \r+ b", ""),
    # A form feed, a backspace or any other control character is lost anywhere.
    ("text", "\frac{1}{2}", "\\frac"),
    ("text", "pour \forall x", "\\forall"),
    ("text", "l'angle \beta", "\\beta"),
    ("tex", "S_n = \frac{a}{b}", "\\frac"),
    ("tex", "\begin{cases} x", "\\begin"),
    ("text", "un \b seul", ""),
    ("text", "fin\x00", ""),
    ("text", "a\x0bb", ""),
    # Accepted: paragraphs, a CRLF and a tab are prose's own.
    ("text", "Premier paragraphe.\n\nSecond paragraphe.", None),
    ("text", "La somme vaut 12.\nnombre de termes : 4", None),
    ("text", "Pour $x > 0$ :\nnombre positif", None),
    ("text", "Première ligne.\r\nSeconde ligne.", None),
    ("text", "Colonne A\tColonne B", None),
    ("text", "Durée\ten secondes", None),
    ("tex", "a = 1\n+ 2", None),
    ("text", "$$a\r\n+ b$$", None),
]


def _block(field: str, value: str) -> dict[str, Any]:
    return {"type": "text", "text": value} if field == "text" else {"type": "formula", "tex": value}


@pytest.mark.parametrize("field,value,named", CONTROL_CASES)
def test_a_lost_backslash_is_refused_where_it_can_be_one(
    field: str, value: str, named: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    card = _explanation(_block(field, value))
    with caplog.at_level(logging.INFO, logger=LOGGER):
        if named is None:
            assert isinstance(_show(card), BoardSet)
            return
        message = _refused(card)
    path = f"card.blocks[0].{field}"
    expected = f"{CONTROL} : {path} ({named})" if named else f"{CONTROL} : {path}"
    assert message == expected
    # A text or formula block is no drawing: nothing is counted.
    assert not _records(caplog, "_refused")


SCRIPT_CASES: list[tuple[str, str | None]] = [
    ("La suite u_n est croissante.", "u_n"),
    ("On calcule x^2 + 1.", "x^2"),
    # A negative exponent: a unit, a power of ten.
    ("a en m·s^-2", "s^-2"),
    ("10^-3 s", "0^-3"),
    ("v en m·s^-1", "s^-1"),
    ("a en m·s^−2", "s^−2"),
    ("le terme x_-1", "x_-1"),
    # Braces, with or without something before them.
    ("x^{-1}", "x^{"),
    ("le terme u_{n+1}", "u_{"),
    ("au carré : ^{2}", "^{"),
    # Accepted: between dollars, in Unicode, or no script at all.
    ("$m·s^{-2}$ et $10^{-3}$ s", None),
    ("La suite $u_n$ et $x^2$.", None),
    ("en m·s⁻² et uₙ₊₁", None),
    ("10 − 3 = 7, un mot-clé, a - b", None),
]


@pytest.mark.parametrize("text,named", SCRIPT_CASES)
def test_a_bare_subscript_or_superscript_in_prose_is_refused(text: str, named: str | None) -> None:
    card = _explanation({"type": "text", "text": text})
    if named is None:
        assert isinstance(_show(card), BoardSet)
    else:
        assert _refused(card) == f"{SCRIPT} : card.blocks[0].text ({named})"


def test_point_names_are_names_not_scripts() -> None:
    """`A_1` keys a figure's points and fills a shape's `of`: neither is prose."""
    plane = {
        "kind": "plane",
        "points": {"A_1": [0, 0], "B": [4, 0], "C_2": [0, 3]},
        "shapes": [{"draw": "polygon", "of": ["A_1", "B", "C_2"]}],
    }
    assert isinstance(_show(_explanation({"type": "figure", "figure": plane})), BoardSet)
    # Its label is prose, though.
    labelled = {**plane, "caption": "Le triangle A_1BC_2"}
    assert _refused(_explanation({"type": "figure", "figure": labelled})).startswith(SCRIPT)


# One string refusal per family and per check: counted under the drawing it sits in.
STRING_REFUSALS: dict[str, tuple[dict[str, Any], str, str]] = {
    "chart": ({**STICKS, "chart": {**STICKS["chart"], "y_title": "Effectifs n_i"}}, "string_script", "(n_i)"),
    "flowchart": (
        {**FLOWCHART, "nodes": [{**FLOWCHART["nodes"][0], "text": "\\Delta"}, *FLOWCHART["nodes"][1:]]},
        "string_latex",
        "(\\Delta)",
    ),
    "figure": ({"type": "figure", "figure": {**FIGURES["plane"], "caption": "$\neq$"}}, "string_control", "(\\neq)"),
    "plot": ({**PLOT, "x_title": "\theta (°C)"}, "string_control", "(\\theta)"),
}


@pytest.mark.parametrize("where", sorted(PLACES))
@pytest.mark.parametrize("name", sorted(STRING_REFUSALS))
def test_a_string_refused_in_a_drawing_is_counted_under_its_family(
    name: str, where: str, caplog: pytest.LogCaptureFixture
) -> None:
    block, rule, named = STRING_REFUSALS[name]
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(PLACES[where](block))
    assert named in message
    [record] = _records(caplog, "_refused")
    assert record.message == f"{name}_refused"
    assert _extra(record) == {**IDS, "rule": rule}
    assert not _records(caplog, "_displayed")


def test_one_string_refusal_names_every_string_and_counts_each_family_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    card = _explanation(
        {"type": "text", "text": "Vois \\dots"},
        {**STICKS, "chart": {**STICKS["chart"], "x_title": "\\bar{x}", "y_title": "\\frac{n}{N}"}},
        {"type": "figure", "figure": {**FIGURES["plane"], "caption": "\\triangle ABC"}},
    )
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(card)
    assert message == (
        f"{LATEX} : card.blocks[0].text (\\dots), card.blocks[1].chart.x_title (\\bar), "
        "card.blocks[1].chart.y_title (\\frac), card.blocks[2].figure.caption (\\triangle)"
    )
    assert [(r.message, r.rule) for r in _records(caplog, "_refused")] == [  # type: ignore[attr-defined]
        ("chart_refused", "string_latex"),
        ("figure_refused", "string_latex"),
    ]


def test_the_string_checks_run_in_order() -> None:
    """A lost backslash first (the other two would misread it), then LaTeX, then scripts."""
    both = _explanation({"type": "text", "text": "u_n \\dots"}, {"type": "text", "text": "\frac{1}{2}"})
    assert _refused(both).startswith(CONTROL)
    assert _refused(_explanation({"type": "text", "text": "u_n \\dots"})) == f"{LATEX} : card.blocks[0].text (\\dots)"


def test_the_card_model_still_replays_what_the_string_checks_refuse() -> None:
    """The checks run in the tool: a stored card holding LaTeX outside $…$ (accepted
    before the checks existed) still validates, and still has its marker."""
    stored = {"card": _explanation({"type": "text", "text": "Vois \\dots et u_n"}, {"type": "formula", "tex": "\frac{1}{2}"})}
    assert DisplayBoardArgs.model_validate(stored).card.kind == "explanation"
    assert marker_for("display_board", stored) == "explication affichée"


# --- drawings the tool refuses, end to end (specs/009-board-drawings/figure.md §3, §7) ---


def _figure_refused(card: dict[str, Any], caplog: pytest.LogCaptureFixture) -> tuple[str, str]:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(card)
    [record] = _records(caplog, "_refused")
    assert record.message == "figure_refused"
    return record.rule, message  # type: ignore[attr-defined]


def test_an_open_exercise_may_not_write_its_figure_values(caplog: pytest.LogCaptureFixture) -> None:
    shown = {"type": "figure", "figure": {**FIGURES["plane"], "show_values": True}}
    rule, message = _figure_refused(_exercise(shown), caplog)
    assert rule == "exercise_values"
    assert message.startswith("La figure drawing accompagne un exercice ouvert")
    # A worked example writes them.
    assert isinstance(_show(_worked(shown)), BoardSet)


def test_a_figure_label_may_not_write_coordinates(caplog: pytest.LogCaptureFixture) -> None:
    figure = copy.deepcopy(FIGURE)
    figure["figure"]["shapes"][2]["label"] = "$(2{,}5 ; 1)$"
    rule, message = _figure_refused(_explanation(figure), caplog)
    assert rule == "label_notation"
    assert "« $(2{,}5 ; 1)$ »" in message


def test_a_figure_number_past_a_million_is_refused(caplog: pytest.LogCaptureFixture) -> None:
    figure = copy.deepcopy(FIGURE)
    figure["figure"]["points"]["B"] = [2e6, 0]
    rule, message = _figure_refused(_explanation(figure), caplog)
    assert rule == "scale"
    assert "million" in message


@pytest.mark.parametrize("name", ["flowchart", "figure", "plot"])
def test_a_drawing_without_type_is_counted_under_its_own_family(name: str, caplog: pytest.LogCaptureFixture) -> None:
    """Read from its keys, not as a chart: the model reads its own block's missing
    `type`, and the refusal is not counted as a chart's."""
    block = {"flowchart": FLOWCHART, "figure": FIGURE, "plot": PLOT}[name]
    untagged = {key: value for key, value in block.items() if key != "type"}
    with caplog.at_level(logging.INFO, logger=LOGGER):
        message = _refused(_exercise(untagged))
    assert message == f"Arguments invalides. card.exercise.drawing.{name}.type: Field required"
    [record] = _records(caplog, "_refused")
    assert record.message == f"{name}_refused"
    assert _extra(record) == {**IDS, "rule": "schema.missing"}


def test_a_lost_backslash_after_a_price_is_still_found() -> None:
    # « 5$ » is a price (RichText never opens maths after a digit), so $x \neq y$ pairs.
    card = {**CARD, "blocks": [{"type": "text", "text": "Coût 5$ et $x \neq y$"}]}
    with pytest.raises(ToolValidationError, match="deux barres"):
        registry.execute("display_board", json.dumps({"card": card}), CTX)


def test_a_tab_before_a_command_tail_is_refused_even_in_prose() -> None:
    # A deliberate trade-off: « Nom<TAB>au total » is refused as a lost \tau, because a
    # model writes \tau or \to far more often than a real tab before « au » or « o ».
    card = {**CARD, "blocks": [{"type": "text", "text": "Nom\tau total"}]}
    with pytest.raises(ToolValidationError, match="deux barres"):
        registry.execute("display_board", json.dumps({"card": card}), CTX)
    plain = {**CARD, "blocks": [{"type": "text", "text": "Nom\tprénom"}]}
    assert isinstance(registry.execute("display_board", json.dumps({"card": plain}), CTX), BoardSet)
