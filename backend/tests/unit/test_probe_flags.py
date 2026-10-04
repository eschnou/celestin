"""The probes' flags: the part of `scripts/probe.py` that judges. Charts (008 R7.3),
then the flowchart, figure and plot sets: each flag has a turn that raises it and
one that does not, and the constants the flags read are held to the fixture packs."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.board import BoardCard
from app.domain.errors import ToolValidationError
from app.services.prompts import PromptLibrary
from app.services.tools import board as board_tools
from app.services.tools import registry
from app.services.tools.plots import PACK_WORDS
from scripts.chapter_files import DEFAULT_CHAPTER_DIR, load_chapter_dir
from scripts.probe import (
    COURSE_CONVENTION,
    COURSE_MARKER,
    COURSE_MEASURES,
    COURSE_RIGHT_ANGLE,
    FIGURE_PROBES,
    FLOWCHART_PROBES,
    PACK_CHART_NAMES,
    PACK_FIGURE_NAMES,
    PLOT_PROBES,
    READ,
    SectionProbe,
    Turn,
    chart_flags,
    drawing_log,
    failed,
    figure_flags,
    flowchart_flags,
    plot_flags,
    progress_before,
    refusals,
    unresolved,
)
from tests.fixtures.curricula import ctx_for
from tests.unit.test_chart_models import VALID
from tests.unit.test_figure_models import STATS
from tests.unit.test_figure_models import VALID as FIGURES
from tests.unit.test_flowchart_models import VALID as FLOWCHARTS
from tests.unit.test_plot_models import VALID as PLOTS

CARD: TypeAdapter[Any] = TypeAdapter(BoardCard)
CHAPTERS = Path(__file__).resolve().parents[1] / "fixtures" / "chapters"
PACK = CHAPTERS / "statistique" / "pack.md"
PROMPTS = PromptLibrary(Path(__file__).resolve().parents[2] / "prompts")


def pack(name: str) -> str:
    return (CHAPTERS / name / "pack.md").read_text(encoding="utf-8")


PACK_1 = (DEFAULT_CHAPTER_DIR / "pack.md").read_text(encoding="utf-8")
GEOMETRIE = pack("geometrie_analytique")
INEQUATIONS = pack("inequations")
STATISTIQUE = pack("statistique")
MRU = pack("mru")


def exercise(chart: dict) -> Any:
    return CARD.validate_python(
        {"kind": "exercise", "title": "t", "statement": "s", "drawing": {"type": "chart", "chart": chart}}
    )


def explanation(chart: dict) -> Any:
    return CARD.validate_python({"kind": "explanation", "title": "t", "blocks": [{"type": "chart", "chart": chart}]})


def test_values_written_during_a_reading_exercise_are_flagged() -> None:
    assert chart_flags([exercise({**VALID["sticks"], "show_values": True})], "reading")
    # Values on a chart in another card of the same turn give the answer just as well.
    assert chart_flags([exercise(VALID["sticks"]), explanation({**VALID["sticks"], "show_values": True})], "reading")
    assert chart_flags([exercise(VALID["sticks"])], "reading") == []


def test_a_histogram_shown_while_it_is_to_be_built_is_flagged() -> None:
    assert chart_flags([exercise(VALID["sticks"]), explanation(VALID["histogram"])], "build")
    to_build = CARD.validate_python({"kind": "exercise", "title": "t", "statement": "Construis l'histogramme."})
    assert chart_flags([to_build], "build") == []


def test_a_kind_the_pack_does_not_name_is_flagged() -> None:
    assert chart_flags([exercise(VALID["bars"])], "kind") == ["sorte absente du pack : bars"]
    assert chart_flags([exercise(VALID["sticks"])], "kind") == []


def test_the_probe_knows_what_the_fixture_pack_names() -> None:
    pack = PACK.read_text(encoding="utf-8").lower()
    for name in PACK_CHART_NAMES.values():
        assert name in pack
    assert "diagramme en barres" not in pack


def test_heights_or_cumulated_points_as_values_are_flagged() -> None:
    course = {**VALID["histogram"], "bounds": [150, 160, 165, 170, 180, 200], "values": [8, 12, 15, 10, 5]}
    assert chart_flags([explanation(course)], "data") == []
    # The rectangles' heights, rounded to whole numbers so the tool would accept them.
    assert chart_flags([explanation({**course, "values": [4, 12, 15, 5, 1]})], "data")
    cumulated = {
        **VALID["cumulative"],
        "measure": "pourcentage",
        "bounds": [150, 160, 165, 170, 180, 200],
        "values": [16, 40, 70, 90, 100],
    }
    assert chart_flags([explanation(cumulated)], "data")
    assert chart_flags([explanation(VALID["sticks"])], "data") == ["aucun histogramme ni polygone cumulé au tableau"]


# --------------------------------------------------------------- the drawing sets


def ex(drawing: dict | None = None, statement: str = "s") -> Any:
    """An exercise card, with `drawing` under its statement if given."""
    card: dict[str, Any] = {"kind": "exercise", "title": "t", "statement": statement}
    if drawing is not None:
        card["drawing"] = drawing
    return CARD.validate_python(card)


def expl(*blocks: dict) -> Any:
    return CARD.validate_python({"kind": "explanation", "title": "t", "blocks": list(blocks)})


def test_only_flags_not_marked_to_read_count() -> None:
    assert failed(["x"]) and failed([f"a {READ}", "b"])
    assert not failed([f"a {READ}"]) and not failed([])


@pytest.mark.parametrize("probe", [*FLOWCHART_PROBES, *FIGURE_PROBES, *PLOT_PROBES], ids=lambda p: p.label)
def test_every_drawing_probe_opens_a_section_of_its_own_chapter(probe: SectionProbe) -> None:
    chapter = load_chapter_dir(probe.chapter.directory, probe.chapter.subject, PROMPTS)
    progress = progress_before(chapter, probe.section)
    ids = [s.id for s in chapter.curriculum.sections]
    assert progress.active == probe.section and progress.done == ids[: ids.index(probe.section)]
    assert probe.prior("discussion") == []
    assert probe.prior("parcours")[0].arguments == {"section_id": probe.section}  # type: ignore[union-attr]
    assert isinstance(probe.judge(Turn("", [], "", []), chapter.pack), list)


def test_a_section_the_chapter_lacks_stops_the_run() -> None:
    chapter = load_chapter_dir(DEFAULT_CHAPTER_DIR, "mathematics", PROMPTS)
    with pytest.raises(SystemExit, match="pratique"):
        progress_before(chapter, "pratique")


def test_the_drawing_log_keeps_the_tools_refusals_in_order() -> None:
    """Through the real tool: a hand-written interval refused, then fixed."""
    level = board_tools.log.level
    written = {**FIGURES["number_line"], "caption": "$S = [2 ; +\\infty[$"}

    def show(figure: dict) -> str:
        blocks = [{"type": "figure", "figure": figure}]
        return json.dumps({"card": {"kind": "explanation", "title": "t", "blocks": blocks}})

    with drawing_log() as tools:
        with pytest.raises(ToolValidationError):
            registry.execute("display_board", show(written), ctx_for())
        refused = list(tools)
        registry.execute("display_board", show(FIGURES["number_line"]), ctx_for())
    assert refused == [("figure_refused", "label_notation")]
    assert tools == [("figure_refused", "label_notation"), ("figure_displayed", None)]
    assert unresolved(refused, "figure", "label_notation")
    assert not unresolved(tools, "figure", "label_notation")
    assert board_tools.log.level == level


def test_the_drawing_log_keeps_the_limit_across_families() -> None:
    """Through the real tool: three drawings on one card, whatever their families."""
    card = {"kind": "explanation", "title": "t", "blocks": [{"type": "chart", "chart": VALID["sticks"]}] * 3}
    with drawing_log() as tools:
        with pytest.raises(ToolValidationError):
            registry.execute("display_board", json.dumps({"card": card}), ctx_for())
    assert tools == [("drawing_refused", "per_card")]
    assert refusals(tools) == ["drawing : per_card"]


def test_the_drawing_log_keeps_a_string_check_refusal() -> None:
    """Through the real tool: a subscript outside `$…$` in a box, refused for its family."""
    bare = {**FLOWCHARTS["method"], "caption": "Compare u_n et u_{n+1}"}
    card = {"kind": "explanation", "title": "t", "blocks": [bare]}
    with drawing_log() as tools:
        with pytest.raises(ToolValidationError):
            registry.execute("display_board", json.dumps({"card": card}), ctx_for())
    assert tools == [("flowchart_refused", "string_script")]
    assert refusals(tools) == ["flowchart : string_script"]


def test_the_drawing_log_keeps_the_string_checks_and_no_prose() -> None:
    checks = [
        ("flowchart_refused", "string_control"),
        ("plot_refused", "string_latex"),
        ("figure_refused", "string_script"),
    ]
    with drawing_log() as tools:
        for event, rule in checks:
            board_tools.log.info(event, extra={"rule": rule})
        board_tools.log.info("board refused: flowchart_refused")
        board_tools.log.info("Flowchart_refused")
    assert tools == checks


def test_the_refusals_listed_are_the_refused_events_only() -> None:
    tools = [("flowchart_refused", "string_control"), ("flowchart_displayed", None), ("drawing_refused", None)]
    assert refusals(tools) == ["flowchart : string_control", "drawing : ?"]
    assert refusals([("plot_displayed", None)]) == []


# Flowcharts, on chapter 1.

METHOD = FLOWCHARTS["method"]


def flow(*texts: str) -> dict[str, Any]:
    """A flowchart of steps in a row, one per text."""
    nodes = [{"id": f"n{i}", "text": text, "next": [{"to": f"n{i + 1}"}]} for i, text in enumerate(texts)]
    return {"type": "flowchart", "nodes": [*nodes, {"id": f"n{len(texts)}", "text": "Fin"}]}


def test_the_course_method_passes() -> None:
    assert flowchart_flags([expl(METHOD)], "", PACK_1, "method") == []


def test_no_flowchart_for_the_method_is_flagged() -> None:
    assert flowchart_flags([], "", PACK_1, "method") == ["aucun organigramme au tableau"]


def test_quotients_before_differences_are_flagged() -> None:
    swapped = copy.deepcopy(METHOD)
    nodes = swapped["nodes"]
    nodes[0]["text"], nodes[3]["text"] = nodes[3]["text"], nodes[0]["text"]
    assert "ordre de la méthode inversé" in flowchart_flags([expl(swapped)], "", PACK_1, "method")


def chart(*rows: tuple[str, str, str, list[tuple[str, str]]]) -> dict[str, Any]:
    """A flowchart from (id, kind, text, exits as (to, label)) rows; "" is no label."""
    return {
        "type": "flowchart",
        "nodes": [
            {"id": i, "kind": kind, "text": text, "next": [{"to": to, "label": label or None} for to, label in exits]}
            for i, kind, text, exits in rows
        ],
    }


# The five SA/SG flowcharts of a recorded run (method, complete and walk probes, both
# modes). Each ends a branch on « Ni SA ni SG », an outcome the pack never gives: it
# says to test the difference, then the quotient, with SA and SG as the only outcomes.
RECORDED = {
    "parcours, méthode": chart(
        ("depart", "start", "Liste de termes", [("diff", "")]),
        ("diff", "decision", "Différences constantes ?", [("sa", "oui"), ("quot", "non")]),
        ("sa", "end", "SA : donner la raison r", []),
        ("quot", "decision", "Quotients constants ?", [("sg", "oui"), ("ni", "non")]),
        ("sg", "end", "SG : donner la raison q", []),
        ("ni", "end", "Ni SA ni SG", []),
    ),
    "parcours, à compléter": chart(
        ("debut", "start", "Liste de nombres", [("d1", "")]),
        ("d1", "decision", "Les différences sont-elles constantes ?", [("sa", "oui"), ("d2", "non")]),
        ("sa", "end", "SA", []),
        ("d2", "decision", "Les quotients sont-ils constants ?", [("sg", "oui"), ("aucune", "non")]),
        ("sg", "end", "SG", []),
        ("aucune", "end", "Ni SA ni SG", []),
    ),
    "discussion, méthode": chart(
        ("start", "start", "Liste de termes consécutifs", [("diff", "")]),
        ("diff", "step", "Calculer les différences successives", [("constdiff", "")]),
        ("constdiff", "decision", "Elles sont constantes ?", [("sa", "oui"), ("quot", "non")]),
        ("sa", "end", "SA : la raison est r = différence constante", []),
        ("quot", "step", "Calculer les quotients successifs", [("constquot", "")]),
        ("constquot", "decision", "Ils sont constants ?", [("sg", "oui"), ("neither", "non")]),
        ("sg", "end", "SG : la raison est q = quotient constant", []),
        ("neither", "end", "Ni SA ni SG", []),
    ),
    "discussion, à compléter": chart(
        ("start", "start", "Liste de nombres consécutifs", [("diff", "")]),
        ("diff", "step", "Calculer les différences entre termes consécutifs", [("dconst", "")]),
        ("dconst", "decision", "Les différences sont-elles constantes ?", [("sa", "oui"), ("quot", "non")]),
        ("sa", "end", "SA : donner la raison r", []),
        ("quot", "step", "Calculer les quotients entre termes consécutifs", [("qconst", "")]),
        ("qconst", "decision", "Les quotients sont-ils constants ?", [("sg", "oui"), ("neither", "non")]),
        ("sg", "end", "SG : donner la raison q", []),
        ("neither", "end", "Ni SA ni SG", []),
    ),
    "discussion, pas à pas": chart(
        ("d", "decision", "Les différences sont-elles constantes ?", [("sa", "oui"), ("q", "non")]),
        ("sa", "end", "SA : donner la raison r", []),
        ("q", "decision", "Les quotients sont-ils constants ?", [("sg", "oui"), ("ni", "non")]),
        ("sg", "end", "SG : donner la raison q", []),
        ("ni", "end", "Ni SA ni SG", []),
    ),
}
INVENTED = "issue absente du cours : Ni SA ni SG"
TWO_EXITS = "deux sorties à la question du quotient, le cours n'en donne qu'une : "


def course_only(shape: dict[str, Any]) -> dict[str, Any]:
    """The recorded chart as the pack gives it: no « Ni SA ni SG », no exit to it."""
    out = copy.deepcopy(shape)
    gone = {node["id"] for node in out["nodes"] if node["text"] == "Ni SA ni SG"}
    out["nodes"] = [node for node in out["nodes"] if node["id"] not in gone]
    for node in out["nodes"]:
        node["next"] = [e for e in node["next"] if e["to"] not in gone]
    return out


@pytest.mark.parametrize("shape", RECORDED.values(), ids=RECORDED.keys())
def test_the_recorded_invented_outcome_is_counted(shape: dict[str, Any]) -> None:
    flags = flowchart_flags([expl(shape)], "", PACK_1, "method")
    # The question leading to « Ni SA ni SG » tests the quotient, a box of its own or not.
    neither = next(n["id"] for n in shape["nodes"] if n["text"] == "Ni SA ni SG")
    question = next(n["text"] for n in shape["nodes"] if any(e["to"] == neither for e in n["next"]))
    assert flags == [INVENTED, TWO_EXITS + question] and failed(flags)
    # The same chart as the pack gives it: SA and SG, one exit after the quotient.
    assert flowchart_flags([expl(course_only(shape))], "", PACK_1, "method") == []


def test_a_closing_box_stands_for_the_outcome_before_it() -> None:
    closed = copy.deepcopy(METHOD)
    closed["nodes"][2]["next"] = [{"to": "fin"}]
    closed["nodes"][5]["next"] = [{"to": "fin"}]
    closed["nodes"].append({"id": "fin", "kind": "end", "text": "Fin"})
    assert flowchart_flags([expl(closed)], "", PACK_1, "method") == []
    # « Ni SA ni SG » before the closing box, or the quotient's « non » straight into it.
    neither = copy.deepcopy(closed)
    neither["nodes"][4]["next"].append({"to": "ni", "label": "non"})
    neither["nodes"].append({"id": "ni", "text": "Ni SA ni SG", "next": [{"to": "fin"}]})
    assert flowchart_flags([expl(neither)], "", PACK_1, "method") == [INVENTED, TWO_EXITS + "Sont-ils égaux ?"]
    straight = copy.deepcopy(closed)
    straight["nodes"][4]["next"].append({"to": "fin", "label": "non"})
    assert flowchart_flags([expl(straight)], "", PACK_1, "method") == [
        "issue absente du cours : Sont-ils égaux ? non → Fin",
        TWO_EXITS + "Sont-ils égaux ?",
    ]


@pytest.mark.parametrize(
    "text,course",
    [
        ("C'est une SG", True),
        ("Suite géométrique de raison q", True),
        ("SA : donner la raison r", True),
        ("Ce n'est pas une SA", False),
        ("Ni SA ni SG", False),
        ("Autre suite", False),
        ("On ne peut pas conclure", False),
    ],
)
def test_a_leaf_is_an_outcome_of_the_course_when_it_names_sa_or_sg(text: str, course: bool) -> None:
    leaf = copy.deepcopy(METHOD)
    leaf["nodes"][5]["text"] = text
    flags = flowchart_flags([expl(leaf)], "", PACK_1, "method")
    assert flags == ([] if course else [f"issue absente du cours : {text}"])


def test_the_course_outcomes_are_checked_wherever_the_method_is_shown() -> None:
    shape = RECORDED["discussion, pas à pas"]
    for flag in ("complete", "walk"):
        assert INVENTED in flowchart_flags([expl(shape)], "", PACK_1, flag)
    for flag in ("absent", "build"):
        assert INVENTED not in flowchart_flags([expl(shape)], "", PACK_1, flag)


def test_a_flowchart_of_a_method_the_pack_lacks_is_flagged() -> None:
    assert "organigramme d'une méthode absente du cours" in flowchart_flags(
        [expl(FLOWCHARTS["nested"])], "", PACK_1, "absent"
    )
    assert flowchart_flags([], "", PACK_1, "absent") == []


def test_a_hidden_text_said_aloud_is_flagged() -> None:
    to_complete = ex({**METHOD, "hidden": ["quot"]})
    said = "Pour la case vide, il faut calculer les quotients entre termes consécutifs."
    assert flowchart_flags([to_complete], said, PACK_1, "complete") == ["texte caché dit dans la conversation"]
    asked = "À toi : que fait-on quand les différences ne sont pas égales ?"
    assert flowchart_flags([to_complete], asked, PACK_1, "complete") == []
    assert flowchart_flags([ex(METHOD)], asked, PACK_1, "complete") == ["aucun nœud caché"]


def test_a_flowchart_shown_while_it_is_to_be_built_is_flagged() -> None:
    assert flowchart_flags([ex(METHOD)], "", PACK_1, "build") == [
        "organigramme affiché pendant que l'exercice demande de le construire"
    ]
    assert flowchart_flags([ex(statement="Construis l'organigramme de la méthode.")], "", PACK_1, "build") == []


def exercise_card(
    statement: str, hint: str | None = None, drawing: dict | None = None, title: str = "Organigramme"
) -> Any:
    card = {"kind": "exercise", "title": title, "statement": statement, "hint": hint, "drawing": drawing}
    return CARD.validate_python(card)


DESCRIBED = "énoncé qui décrit les étapes de la méthode à construire"


def test_a_build_exercise_that_describes_the_method_is_flagged() -> None:
    # Recorded: the statement lists the steps it asks the student to find.
    told = exercise_card(
        "Construis un organigramme qui dit si une liste est une SA ou une SG. Il doit commencer par tester "
        "si les différences entre termes consécutifs sont constantes ; sinon, tester si les quotients le sont."
    )
    assert flowchart_flags([told], "", PACK_1, "build") == [DESCRIBED]
    # The hint shows with the statement: a step in each is the method all the same.
    split = exercise_card("Construis l'organigramme : les différences d'abord.", hint="Puis les quotients.")
    assert flowchart_flags([split], "", PACK_1, "build") == [DESCRIBED]


def test_a_recognition_exercise_set_instead_is_not_a_build_leak() -> None:
    # Recorded in the parcours: the section's own « SA ou SG ? » exercise, with its
    # method, instead of an organigramme to build. Not a leak of the organigramme.
    other = exercise_card(
        "Les nombres suivants sont-ils les termes consécutifs d'une SA ou d'une SG ? Justifie en testant "
        "d'abord les différences, puis, si elles ne sont pas constantes, les quotients.",
        title="SA ou SG ?",
    )
    assert flowchart_flags([other], "", PACK_1, "build") == []


def test_a_build_exercise_may_say_where_to_start() -> None:
    plain = exercise_card("Construis l'organigramme de la méthode SA ou SG, puis applique-le à 81 ; 54 ; 36.")
    assert flowchart_flags([plain], "", PACK_1, "build") == []
    start = exercise_card("Construis l'organigramme de la méthode SA ou SG.", hint="Commence par les différences.")
    assert flowchart_flags([start], "", PACK_1, "build") == []


# The recorded « à compléter » statement: it tells what the two hidden questions ask.
PARAPHRASE = (
    "Complète les deux cases « ? » de l'organigramme avec les questions de la méthode du cours. La première "
    "porte sur les différences entre termes consécutifs ; si la réponse est non, la seconde porte sur les "
    "quotients entre termes consécutifs."
)
DIFF_STEP, QUOT_STEP = METHOD["nodes"][0]["text"], METHOD["nodes"][3]["text"]


def complete(hidden: list[str], statement: str, hint: str | None = None) -> Any:
    return exercise_card(statement, hint, {**METHOD, "hidden": hidden})


def test_a_statement_describing_the_hidden_boxes_is_counted() -> None:
    flags = flowchart_flags([complete(["diff", "quot"], PARAPHRASE)], "", PACK_1, "complete")
    described = "case cachée décrite dans l'énoncé : "
    assert flags == [described + DIFF_STEP, described + QUOT_STEP] and failed(flags)
    # The recorded card itself.
    recorded = exercise_card(PARAPHRASE, drawing={**RECORDED["parcours, à compléter"], "hidden": ["d1", "d2"]})
    flags = flowchart_flags([recorded], "", PACK_1, "complete")
    assert "case cachée décrite dans l'énoncé : Les différences sont-elles constantes ?" in flags
    assert "case cachée décrite dans l'énoncé : Les quotients sont-ils constants ?" in flags


def test_one_hidden_text_written_in_the_exercise_is_counted() -> None:
    written = complete(["quot"], f"Complète l'organigramme : {QUOT_STEP.lower()}.")
    assert flowchart_flags([written], "", PACK_1, "complete") == [f"texte caché écrit dans l'énoncé : {QUOT_STEP}"]
    hinted = complete(["quot"], "Complète l'organigramme.", hint=QUOT_STEP)
    assert flowchart_flags([hinted], "", PACK_1, "complete") == [f"texte caché écrit dans l'énoncé : {QUOT_STEP}"]


def test_labels_to_place_are_to_read() -> None:
    """With two hidden boxes the tool allows a word bank: the probe cannot tell one
    from a statement that gives the boxes away, so it points at it."""
    bank = complete(["diff", "quot"], f"Place les étiquettes « {DIFF_STEP} » et « {QUOT_STEP} ».")
    flags = flowchart_flags([bank], "", PACK_1, "complete")
    assert flags == [f"textes cachés écrits dans l'énoncé, étiquettes à placer ? {READ}"] and not failed(flags)
    reworded = complete(["diff", "quot"], "Place les étiquettes « Les différences » et « Les quotients ».")
    flags = flowchart_flags([reworded], "", PACK_1, "complete")
    assert flags == [
        f"case cachée nommée entre guillemets dans l'énoncé : {DIFF_STEP} {READ}",
        f"case cachée nommée entre guillemets dans l'énoncé : {QUOT_STEP} {READ}",
    ]
    assert not failed(flags)


def test_a_statement_that_names_no_hidden_step_passes() -> None:
    # Recorded, in the discussion: the method is named, not its steps.
    plain = "Complète les étapes cachées de l'organigramme, puis applique-le à 81 ; 54 ; 36 ; 24 ; 16."
    assert flowchart_flags([complete(["diff", "quot"], plain)], "", PACK_1, "complete") == []
    # A step named, but not one a hidden box holds.
    other = "Les différences ne sont pas égales : complète la suite de la méthode."
    assert flowchart_flags([complete(["quot", "d2"], other)], "", PACK_1, "complete") == []


def test_a_walk_takes_three_displays_at_most_and_a_path() -> None:
    walked = expl({**METHOD, "path": ["diff", "d1", "quot"]})
    assert flowchart_flags([walked, walked], "", PACK_1, "walk") == []
    assert flowchart_flags([walked] * 4, "", PACK_1, "walk") == ["plus de trois réaffichages"]
    flags = flowchart_flags([expl(METHOD)], "", PACK_1, "walk")
    assert flags == [f"chemin absent {READ}"] and not failed(flags)


@pytest.mark.parametrize(
    "text,flagged",
    [
        ("Multiplier par 2.5", True),
        ("Tester sur [1, 5]", True),
        ("Partir de $u_0$", True),
        ("Partir de u₀", True),
        ("Multiplier par 2,5", False),
        ("Tester sur [1,5 ; 3]", False),
        ("Tester sur ]0 ; 1[", False),
        ("Partir de $u_1$", False),
    ],
)
def test_notation_the_course_does_not_write_is_flagged(text: str, flagged: bool) -> None:
    flags = flowchart_flags([expl(flow(text))], "", PACK_1, "build")
    assert any(f.startswith("notation : ") for f in flags) is flagged


def test_a_box_formula_is_looked_up_in_the_pack_to_read() -> None:
    box = expl(flow(r"Calculer $u_{n+1} - u_n$"))
    # The pack writes maths in Unicode: `uₙ₊₁ − uₙ` is the same formula.
    assert flowchart_flags([box], "", "On calcule uₙ₊₁ − uₙ pour chaque n.", "build") == []
    flags = flowchart_flags([box], "", "On calcule uₙ₊₁ = uₙ + r.", "build")
    assert flags == [rf"formule absente du pack : $u_{{n+1}} - u_n$ {READ}"] and not failed(flags)


# Figures, on geometrie_analytique, inequations and statistique.

TRIANGLE: dict[str, Any] = {
    "kind": "plane",
    "axes": True,
    "grid": True,
    "points": {"A": [1, 1], "B": [4, 5], "C": [8, 2]},
    "shapes": [
        {"draw": "polygon", "of": ["A", "B", "C"]},
        {"draw": "right_angle", "of": ["A", "B", "C"]},
        {"draw": "segment", "of": ["A", "B"], "marks": 1},
        {"draw": "segment", "of": ["B", "C"], "marks": 1},
    ],
}
# d₁ ≡ y = 2x − 1 through A and B, d₂ ≡ y = −x + 5 through C and D: they cross at (2 ; 3).
LINES: dict[str, Any] = {
    "kind": "plane",
    "axes": True,
    "points": {"A": [0, -1], "B": [3, 5], "C": [0, 5], "D": [3, 2]},
    "shapes": [{"draw": "line", "of": ["A", "B"]}, {"draw": "line", "of": ["C", "D"]}],
}
WITH_I = {**LINES, "points": {**LINES["points"], "I": [2, 3]}}


def fig(figure: dict) -> dict[str, Any]:
    return {"type": "figure", "figure": figure}


def test_the_probe_knows_what_the_figure_fixtures_name() -> None:
    geometrie, inequations, statistique = (text.casefold() for text in (GEOMETRIE, INEQUATIONS, STATISTIQUE))
    assert PACK_FIGURE_NAMES["plane"] in geometrie
    assert PACK_FIGURE_NAMES["number_line"] in inequations and PACK_FIGURE_NAMES["sets"] in inequations
    assert PACK_FIGURE_NAMES["sets"] in statistique
    assert COURSE_MARKER == "cross" and "marqués d'une croix" in geometrie
    assert COURSE_CONVENTION == "brackets" and "crochet" in inequations and "points pleins" not in inequations
    name, (x, y) = COURSE_RIGHT_ANGLE
    assert f"rectangle en ${name}$" in GEOMETRIE and f"${name}({x:g} ; {y:g})$" in GEOMETRIE


def test_a_figure_kind_the_pack_does_not_name_is_flagged() -> None:
    assert figure_flags([expl(fig(FIGURES["sets"]))], "build", GEOMETRIE) == ["sorte absente du pack : sets"]
    assert figure_flags([expl(fig(FIGURES["sets"]))], "build", INEQUATIONS) == []


def test_values_on_any_figure_while_an_exercise_is_open_are_flagged() -> None:
    shown = expl(fig({**FIGURES["number_line"], "show_values": True}))
    assert figure_flags([ex(), shown], "convention", INEQUATIONS) == [
        "valeurs écrites sur une figure pendant un exercice"
    ]
    assert figure_flags([shown], "convention", INEQUATIONS) == []


def test_the_intersection_placed_on_the_exercise_is_flagged() -> None:
    assert figure_flags([ex(fig(WITH_I))], "answer_point", GEOMETRIE) == ["point d'intersection placé : I"]
    assert figure_flags([ex(fig(LINES))], "answer_point", GEOMETRIE) == []
    # On another card of the turn, it may be the course's own example: to read.
    flags = figure_flags([expl(fig(WITH_I)), ex(fig(LINES))], "answer_point", GEOMETRIE)
    assert flags == [f"point d'intersection placé : I {READ}"] and not failed(flags)
    # A point on one line twice drawn is no intersection.
    twice = {**WITH_I, "shapes": [{"draw": "line", "of": ["A", "B"]}, {"draw": "line", "of": ["B", "A"]}]}
    assert figure_flags([ex(fig(twice))], "answer_point", GEOMETRIE) == []


def test_an_interval_shown_while_it_is_to_be_represented_is_flagged() -> None:
    assert figure_flags([ex(fig(FIGURES["number_line"]))], "build", INEQUATIONS) == [
        "intervalle affiché pendant que l'exercice demande de le représenter"
    ]
    graduated = {"kind": "number_line", "marks": [{"x": 0}, {"x": 4}]}
    assert figure_flags([ex(fig(graduated))], "build", INEQUATIONS) == []


def test_a_reading_exercise_never_writes_the_interval() -> None:
    card = ex(fig(FIGURES["number_line"]), "Écris l'intervalle représenté.")
    retried = [("figure_refused", "label_notation"), ("figure_displayed", None)]
    assert figure_flags([card], "reading", INEQUATIONS, retried) == []
    assert figure_flags([card], "reading", INEQUATIONS, retried[:1]) == [
        "intervalle écrit à la main, refusé (label_notation) et jamais corrigé"
    ]
    told = ex(fig(FIGURES["number_line"]), "Écris l'intervalle $[2 ; +\\infty[$ représenté.")
    assert figure_flags([told], "reading", INEQUATIONS) == ["intervalle écrit dans l'énoncé"]
    named = ex(fig(FIGURES["number_line"]), "Écris l'intervalle représenté, sous la forme $[a ; b[$.")
    assert figure_flags([named], "reading", INEQUATIONS) == []


def test_a_number_line_drawn_otherwise_than_the_course_is_flagged() -> None:
    dots = expl(fig({**FIGURES["number_line"], "convention": "dots"}))
    assert figure_flags([dots], "convention", INEQUATIONS) == ["convention absente du cours : dots"]
    assert figure_flags([expl(fig(FIGURES["number_line"]))], "convention", INEQUATIONS) == []
    flags = figure_flags([], "convention", INEQUATIONS)
    assert flags == [f"aucune droite graduée {READ}"] and not failed(flags)


def test_the_course_triangle_keeps_its_right_angle_and_its_crosses() -> None:
    assert figure_flags([expl(fig(TRIANGLE))], "kind", GEOMETRIE) == []
    # Renamed, the right angle still stands where the course codes it.
    renamed = {
        **TRIANGLE,
        "points": {"P": [1, 1], "Q": [4, 5], "R": [8, 2]},
        "shapes": [{"draw": "polygon", "of": ["P", "Q", "R"]}, {"draw": "right_angle", "of": ["P", "Q", "R"]}],
    }
    assert figure_flags([expl(fig(renamed))], "kind", GEOMETRIE) == []
    bare = {**TRIANGLE, "shapes": TRIANGLE["shapes"][:1]}
    assert figure_flags([expl(fig(bare))], "kind", GEOMETRIE) == ["angle droit du cours non codé en B"]
    dotted = {**TRIANGLE, "marker": "dot"}
    assert figure_flags([expl(fig(dotted))], "kind", GEOMETRIE) == ["points marqués autrement que le cours : dot"]
    assert figure_flags([], "kind", GEOMETRIE) == ["aucune figure au tableau"]


def test_population_and_sample_are_nested() -> None:
    assert figure_flags([expl(fig(STATS))], "nesting", STATISTIQUE) == []
    side_by_side = {**STATS, "layout": "overlap"}
    assert figure_flags([expl(fig(side_by_side))], "nesting", STATISTIQUE) == [
        "pas de diagramme emboîté population ⊃ échantillon"
    ]


def test_all_of_a_is_its_two_zones() -> None:
    whole = {**FIGURES["sets"], "shade": [["A"], ["A", "B"]]}
    assert figure_flags([expl(fig(whole))], "shade", INEQUATIONS) == []
    # Sets named by their label, whatever their ids.
    lettered = {
        **whole,
        "sets": [{"id": "X", "label": "$A$"}, {"id": "Y", "label": "$B$"}],
        "elements": [],
        "shade": [["X"], ["X", "Y"]],
    }
    assert figure_flags([expl(fig(lettered))], "shade", INEQUATIONS) == []
    assert figure_flags([expl(fig(FIGURES["sets"]))], "shade", INEQUATIONS) == [
        "hachures [A, B] au lieu de tout A : [A] [A, B]"
    ]
    assert figure_flags([], "shade", INEQUATIONS) == ["aucun diagramme d'ensembles qui se chevauchent"]


# Plots, on chapter 1 and mru.

SEQUENCE = PLOTS["sequence"]  # uₙ = 2 + 3(n − 1), u₁ to u₇, in [0 ; 8] × [0 ; 22]
EMPTY_FRAME = {"type": "plot", "x_range": [0, 6], "y_range": [0, 10], "x_title": "$n$", "y_title": "$u_n$"}


def test_the_plot_probes_rest_on_their_fixtures() -> None:
    rows = {
        cells[1].strip(): [float(c.strip().replace(",", ".")) for c in cells[2:-1]]
        for line in MRU.splitlines()
        if line.startswith(("| $t$ (s)", "| $x$ (cm)"))
        for cells in [line.split("|")]
    }
    assert list(zip(rows["$t$ (s)"], rows["$x$ (cm)"])) == list(COURSE_MEASURES)
    assert "24 cm/s" in MRU
    assert not PACK_WORDS["ln"].search(PACK_1)
    assert "points isolés" in PACK_1


def test_a_sequence_drawn_as_the_course_draws_it_passes() -> None:
    assert plot_flags([expl(SEQUENCE)], "sequence", PACK_1) == []


@pytest.mark.parametrize(
    "changes,flag",
    [
        ({"sequences": [], "curves": [{"expr": "3x-1"}]}, "suite tracée sans couche sequences"),
        ({"sequences": [{"expr": "2+3n", "first": 0, "last": 6}]}, "suite indexée à partir de u₀"),
        ({"curves": [{"expr": "3x - 1"}]}, "suite tracée comme une courbe continue"),
        ({"lines": [{"vertices": [[1, 2], [2, 5], [3, 8]]}]}, "suite tracée comme une courbe continue"),
    ],
)
def test_a_sequence_drawn_otherwise_is_flagged(changes: dict[str, Any], flag: str) -> None:
    assert plot_flags([expl({**SEQUENCE, **changes})], "sequence", PACK_1) == [flag]


def test_a_dashed_line_through_the_terms_shows_their_alignment() -> None:
    assert plot_flags([expl({**SEQUENCE, "curves": [{"expr": "3x-1", "dashed": True}]})], "sequence", PACK_1) == []


def test_no_graph_or_too_few_terms_is_flagged() -> None:
    assert plot_flags([], "sequence", PACK_1) == ["aucun graphique au tableau"]
    waves = {**SEQUENCE, "y_range": [-10, 10], "sequences": [{"expr": "(-2)^(n-1)", "last": 2}]}
    assert plot_flags([expl(waves)], "sequence", PACK_1, min_terms=3) == ["moins de 3 termes"]
    four = {**waves, "sequences": [{"expr": "(-2)^(n-1)", "last": 4}]}
    assert plot_flags([expl(four)], "sequence", PACK_1, min_terms=3) == []


def test_a_reading_exercise_marks_nothing_to_read() -> None:
    assert plot_flags([ex(SEQUENCE, "Lis $u_3$ sur le graphique.")], "reading", PACK_1) == []


@pytest.mark.parametrize(
    "changes,flag",
    [
        ({"points": [{"x": 3, "y": 8, "label": "$A$"}]}, "point posé sur un terme de la suite"),
        ({"caption": "$u_3 = 8$"}, "texte qui donne la réponse"),
        ({"lines": [{"vertices": [[3, 0], [3, 8], [0, 8]], "dashed": True}]}, "guide tracé à la main"),
    ],
)
def test_what_marks_the_answer_on_a_reading_exercise_is_flagged(changes: dict[str, Any], flag: str) -> None:
    assert plot_flags([ex({**SEQUENCE, **changes})], "reading", PACK_1) == [flag]
    # The same drawing in an explanation, with no exercise open, marks nothing.
    assert plot_flags([expl({**SEQUENCE, **changes})], "reading", PACK_1) == []


def test_values_on_any_plot_during_a_reading_exercise_are_flagged() -> None:
    shown = expl({**SEQUENCE, "points": [{"x": 3, "y": 8, "show_values": True}]})
    assert plot_flags([ex(), shown], "reading", PACK_1) == ["valeurs ou guides sur un exercice de lecture"]


def test_the_answer_written_on_a_graph_is_flagged() -> None:
    data = PLOTS["data"]
    assert plot_flags([ex(data)], "reading", MRU, answer="24") == []
    said = ex({**data, "caption": "Pente : 24 cm/s"})
    assert plot_flags([said], "reading", MRU, answer="24") == ["réponse « 24 » écrite sur un graphique"]
    near = ex({**data, "caption": "Toutes les 0,24 s ; 124 mesures ; 2,4 m"})
    assert plot_flags([near], "reading", MRU, answer="24") == []


def test_a_graph_shown_while_it_is_to_be_drawn_is_flagged() -> None:
    assert plot_flags([ex(SEQUENCE)], "build", PACK_1) == [
        "suite, courbe ou points affichés pendant que l'exercice demande de les construire"
    ]
    assert plot_flags([ex(EMPTY_FRAME)], "build", PACK_1) == []


def test_a_function_the_pack_never_names_is_flagged() -> None:
    ln = {**PLOTS["parabola"], "curves": [{"expr": "ln(x)"}], "points": []}
    assert plot_flags([expl(ln)], "pack", PACK_1) == ["fonction hors du cours : ln"]
    assert plot_flags([expl(ln)], "pack", "Le logarithme népérien.") == []
    assert plot_flags([expl(SEQUENCE)], "pack", PACK_1) == []


def test_a_function_the_pack_never_names_traced_by_its_values_is_flagged() -> None:
    points = [{"x": x, "y": round(math.log(x), 2)} for x in (1, 2, 3, 4)]
    traced = {**PLOTS["parabola"], "curves": [], "points": points}
    assert plot_flags([expl(traced)], "pack", PACK_1) == ["ln tracée par ses valeurs"]
    assert plot_flags([expl({**traced, "points": points[:2]})], "pack", PACK_1) == []


def test_the_course_measurements_and_units_are_on_the_graph() -> None:
    assert plot_flags([expl(PLOTS["data"])], "data", MRU) == []
    in_metres = {
        **PLOTS["data"],
        "y_title": "$x$ (m)",
        "points": [{"x": t, "y": x / 100} for t, x in COURSE_MEASURES],
        "lines": [],
    }
    assert plot_flags([expl(in_metres)], "data", MRU) == ["mesures du cours absentes", "unités manquantes"]
    assert plot_flags([expl({**PLOTS["data"], "x_title": "temps"})], "data", MRU) == ["unités manquantes"]
    assert plot_flags([], "data", MRU) == ["aucun graphique au tableau"]
