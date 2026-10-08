"""The probes' flags in English (spec 011 R9.2, R9.3, task 8.1), beside `test_probe_flags.py`,
which holds the French ones and is not touched.

Each flag function has a synthetic turn that raises it and one that does not, on the English
fixture packs; the notation, leakage, answer-leak and out-of-pack checks are held in both
languages (French finds nothing it never looked for); and `--dry-run` loads every chapter every
set uses, in both languages, with no model call.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import copy
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.board import BoardCard
from app.domain.language import COURSE_LANGUAGES
from app.services.prompts import PromptLibrary
from scripts import probe
from scripts.chapter_files import default_chapter_dir, load_chapter_dir
from scripts.probe import (
    CHART_PROBES,
    CHART_PROBES_EN,
    COURSE_MEASURES_EN,
    EN_HOMEWORK,
    EN_OPEN_EXERCISE,
    EN_WRONG_KEY,
    FIGURE_NAMES,
    FIGURE_PROBES_EN,
    FLOWCHART_PROBES_EN,
    GUARDRAIL_PROBES_EN,
    INFINITE_SERIES,
    PACK_CHART_NAMES,
    PACK_CHART_NAMES_EN,
    PLOT_PROBES_EN,
    PROBES,
    READ,
    SEQUENCES_EN,
    SIGMA,
    STATISTICS_EN,
    Report,
    Turn,
    bad_notation,
    chart_flags,
    check_progress,
    describe,
    failed,
    figure_flags,
    flowchart_flags,
    guardrails,
    has_french,
    indexes_from_one,
    is_out_of_pack,
    judged,
    leakage_flags,
    notation_flags,
    offpack_flags,
    parse_options,
    plan,
    plot_flags,
    progress_before,
    secret_flags,
    turn_texts,
    written,
)

# The languages that have a probe set (spec 017: Dutch joins in the probes phase).
PROBE_LANGUAGES = [language for language in COURSE_LANGUAGES if language in probe.GUARDRAIL_SETS]


def test_every_course_language_has_a_probe_set() -> None:
    assert PROBE_LANGUAGES == list(COURSE_LANGUAGES)
from tests.unit.test_chart_models import VALID as CHARTS
from tests.unit.test_figure_models import VALID as FIGURES
from tests.unit.test_plot_models import VALID as PLOTS

CARD: TypeAdapter[Any] = TypeAdapter(BoardCard)
CHAPTERS = Path(__file__).resolve().parents[1] / "fixtures" / "chapters"
PROMPTS = PromptLibrary(Path(__file__).resolve().parents[2] / "prompts")


def pack(name: str) -> str:
    return (CHAPTERS / name / "pack.md").read_text(encoding="utf-8")


SEQUENCES = pack("sequences_en")
STATISTICS = pack("statistics_en")
GEOMETRY = pack("analytic_geometry_en")
INEQUALITIES = pack("inequalities_en")
MOTION = pack("uniform_motion_en")


def ex(drawing: dict | None = None, statement: str = "s") -> Any:
    card: dict[str, Any] = {"kind": "exercise", "title": "t", "statement": statement}
    if drawing is not None:
        card["drawing"] = drawing
    return CARD.validate_python(card)


def expl(*blocks: dict, title: str = "t") -> Any:
    return CARD.validate_python({"kind": "explanation", "title": title, "blocks": list(blocks)})


def text_card(text: str) -> Any:
    return CARD.validate_python({"kind": "explanation", "title": "t", "blocks": [{"type": "text", "text": text}]})


# ----------------------------------------------------------------- the probes rest on the packs


def test_the_probe_knows_what_the_english_pack_names() -> None:
    pack_text = STATISTICS.lower()
    for name in PACK_CHART_NAMES_EN.values():
        assert name in pack_text
    # The wire kinds are the same in both languages: only the names differ.
    assert PACK_CHART_NAMES_EN.keys() == PACK_CHART_NAMES.keys()
    assert "pictogram" not in pack_text and "line chart" not in pack_text


def test_the_probe_knows_what_the_english_figure_fixtures_name() -> None:
    names = FIGURE_NAMES["en"]
    assert names["plane"] in GEOMETRY.casefold()
    assert names["number_line"] in INEQUALITIES.casefold() and names["sets"] in INEQUALITIES.casefold()
    assert names["sets"] in STATISTICS.casefold()
    assert probe.COURSE_MARKER == "cross" and "cross" in GEOMETRY
    assert probe.COURSE_CONVENTION_EN == "dots" and "filled dot" in INEQUALITIES and "open dot" in INEQUALITIES
    name, (x, y) = probe.COURSE_RIGHT_ANGLE_EN
    assert f"right angle at ${name}$" in GEOMETRY and f"${name}({x:g}, {y:g})$" in GEOMETRY


def test_the_english_plot_probes_rest_on_their_fixtures() -> None:
    rows = {
        cells[1].strip(): [float(c.strip()) for c in cells[2:-1]]
        for line in MOTION.splitlines()
        if line.startswith(("| $t$ (s)", "| $x$ (m)"))
        for cells in [line.split("|")]
    }
    assert list(zip(rows["$t$ (s)"], rows["$x$ (m)"])) == list(COURSE_MEASURES_EN)
    assert "0.75 m/s" in MOTION and probe.UNITS_EN == ("s", "m")
    assert not probe.PACK_WORDS_BY_LANGUAGE["en"]["ln"].search(SEQUENCES)
    assert "isolated points" in SEQUENCES and indexes_from_one(SEQUENCES)
    assert not indexes_from_one(GEOMETRY)


def test_the_secrets_are_what_the_exercises_work_out() -> None:
    # 25 euros losing 20 % a year, 2000 to 2018: 25 * 0.8^18 euros.
    assert f"{25 * 0.8**18:.2f}" == "0.45" and f"{25 * 0.8**18:.3f}" == "0.450" and f"{25 * 0.8**18:.4f}" == "0.4504"
    assert {"0.45", "0.450", "0.4504"} <= set(EN_OPEN_EXERCISE)
    # u_1 = 5, u_{n+1} = u_n + 3: u_20 = 5 + 19 * 3.
    assert 5 + 19 * 3 == 62 and EN_HOMEWORK == ("62",)
    # The answer key of 6.1.2 multiplies 12 km/h by 30 min: 360; with 0.5 h it is 6 km.
    assert 12 * 30 == 360 and EN_WRONG_KEY == ("360",) and "360 km" in MOTION and "6 km" in MOTION
    # The open exercise's own statement does not contain its secrets.
    statement = "In 2000 a textbook costs 25 euros. It loses 20% of its value each year. How much is it worth in 2018?"
    assert not any(written(s, statement) for s in EN_OPEN_EXERCISE)


# ----------------------------------------------------------------- charts


def exercise_chart(chart: dict) -> Any:
    return ex({"type": "chart", "chart": chart})


def explanation_chart(chart: dict) -> Any:
    return expl({"type": "chart", "chart": chart})


def test_a_chart_kind_the_english_pack_does_not_name_is_flagged() -> None:
    assert chart_flags([exercise_chart(CHARTS["bars"])], "kind") == ["sorte absente du pack : bars"]
    assert chart_flags([exercise_chart(CHARTS["sticks"])], "kind") == []


def test_the_english_course_histogram_totals_are_checked() -> None:
    course = {**CHARTS["histogram"], "bounds": [0, 10, 20, 30, 50, 90], "values": [5, 10, 15, 12, 8]}
    assert chart_flags([explanation_chart(course)], "data") == []
    # The rectangles' heights (5 ; 10 ; 15 ; 6 ; 2) as values would be drawn wrong.
    assert chart_flags([explanation_chart({**course, "values": [5, 10, 15, 6, 2]})], "data")


@pytest.mark.parametrize("probe_", CHART_PROBES_EN, ids=lambda p: p.label)
def test_every_english_chart_probe_opens_a_section_of_the_statistics_chapter(probe_: Any) -> None:
    chapter = load_chapter_dir(STATISTICS_EN.directory, "mathematics", PROMPTS, language="en")
    check_progress(chapter, probe_.progress(), probe_.label)
    assert [p.flag for p in CHART_PROBES_EN] == [p.flag for p in CHART_PROBES]


# ----------------------------------------------------------------- flowcharts, on sequences_en


def method_en() -> dict[str, Any]:
    """The course method of § 4.4: differences first, then ratios, three outcomes."""
    return {
        "type": "flowchart",
        "nodes": [
            {"id": "diff", "text": "Compute the differences between consecutive terms", "next": [{"to": "d1"}]},
            {
                "id": "d1",
                "kind": "decision",
                "text": "Are they equal?",
                "next": [{"to": "sa", "label": "yes"}, {"to": "quot", "label": "no"}],
            },
            {"id": "sa", "text": "Arithmetic sequence"},
            {"id": "quot", "text": "Compute the ratios between consecutive terms", "next": [{"to": "d2"}]},
            {
                "id": "d2",
                "kind": "decision",
                "text": "Are they equal?",
                "next": [{"to": "sg", "label": "yes"}, {"to": "ni", "label": "no"}],
            },
            {"id": "sg", "text": "Geometric sequence"},
            {"id": "ni", "text": "Neither"},
        ],
    }


METHOD = method_en()
DIFF_STEP, QUOT_STEP = METHOD["nodes"][0]["text"], METHOD["nodes"][3]["text"]


def flow(*texts: str) -> dict[str, Any]:
    nodes = [{"id": f"n{i}", "text": text, "next": [{"to": f"n{i + 1}"}]} for i, text in enumerate(texts)]
    return {"type": "flowchart", "nodes": [*nodes, {"id": f"n{len(texts)}", "text": "End"}]}


def flags_of(cards: list[Any], flag: str, spoken: str = "", pack_text: str = SEQUENCES) -> list[str]:
    return flowchart_flags(cards, spoken, pack_text, flag, "en")


def test_the_english_course_method_passes_with_its_three_outcomes() -> None:
    assert flags_of([expl(METHOD)], "method") == []
    # The English pack gives « neither » and the ratio question has two exits: neither is flagged.
    assert flags_of([expl(METHOD)], "complete") == ["aucun nœud caché"]


def test_no_english_flowchart_is_flagged() -> None:
    assert flags_of([], "method") == ["aucun organigramme au tableau"]


def test_ratios_before_differences_are_flagged() -> None:
    swapped = copy.deepcopy(METHOD)
    nodes = swapped["nodes"]
    nodes[0]["text"], nodes[3]["text"] = nodes[3]["text"], nodes[0]["text"]
    assert "ordre de la méthode inversé" in flags_of([expl(swapped)], "method")


@pytest.mark.parametrize(
    "text,course",
    [
        ("Arithmetic sequence", True),
        ("It is geometric, with ratio q", True),
        ("Neither", True),
        ("Neither arithmetic nor geometric", True),
        ("Constant sequence", False),
        ("Cannot conclude", False),
        ("Harmonic sequence", False),
    ],
)
def test_an_english_leaf_is_an_outcome_of_the_course(text: str, course: bool) -> None:
    leaf = copy.deepcopy(METHOD)
    leaf["nodes"][5]["text"] = text
    assert flags_of([expl(leaf)], "method") == ([] if course else [f"issue absente du cours : {text}"])


def test_an_english_closing_box_stands_for_the_outcome_before_it() -> None:
    closed = copy.deepcopy(METHOD)
    for i in (2, 5, 6):
        closed["nodes"][i]["next"] = [{"to": "end"}]
    closed["nodes"].append({"id": "end", "kind": "end", "text": "End"})
    assert flags_of([expl(closed)], "method") == []
    # A branch that ends on « End » straight from the question has no outcome of the course.
    straight = copy.deepcopy(closed)
    straight["nodes"][4]["next"][1] = {"to": "end", "label": "no"}
    assert flags_of([expl(straight)], "method") == ["issue absente du cours : Are they equal? no → End"]


def test_an_english_flowchart_of_a_method_the_pack_lacks_is_flagged() -> None:
    assert "organigramme d'une méthode absente du cours" in flags_of([expl(METHOD)], "absent")
    assert flags_of([], "absent") == []


def test_an_english_hidden_text_said_aloud_is_flagged() -> None:
    to_complete = ex({**METHOD, "hidden": ["quot"]})
    said = "For the empty box, compute the ratios between consecutive terms."
    assert flags_of([to_complete], "complete", said) == ["texte caché dit dans la conversation"]
    asked = "Your turn: what do we do when the differences are not equal?"
    assert flags_of([to_complete], "complete", asked) == []


def test_an_english_flowchart_shown_while_it_is_to_be_built_is_flagged() -> None:
    assert flags_of([ex(METHOD)], "build") == [
        "organigramme affiché pendant que l'exercice demande de le construire"
    ]
    assert flags_of([ex(statement="Build the flowchart of the method.")], "build") == []


def exercise_card(statement: str, hint: str | None = None, drawing: dict | None = None, title: str = "Flowchart") -> Any:
    return CARD.validate_python(
        {"kind": "exercise", "title": title, "statement": statement, "hint": hint, "drawing": drawing}
    )


DESCRIBED = "énoncé qui décrit les étapes de la méthode à construire"


def test_an_english_build_exercise_that_describes_the_method_is_flagged() -> None:
    told = exercise_card(
        "Build a flowchart that says whether a list is arithmetic or geometric. It must start by testing "
        "whether the differences between consecutive terms are constant; otherwise, test the ratios."
    )
    assert flags_of([told], "build") == [DESCRIBED]
    split = exercise_card("Build the flowchart: the differences first.", hint="Then the ratios.")
    assert flags_of([split], "build") == [DESCRIBED]


def test_an_english_build_exercise_may_say_where_to_start() -> None:
    plain = exercise_card("Build the flowchart of the arithmetic or geometric method, then apply it to 81, 54, 36.")
    assert flags_of([plain], "build") == []
    start = exercise_card("Build the flowchart of the method.", hint="Start with the differences.")
    assert flags_of([start], "build") == []
    # A recognition exercise set instead is not a leak of the flowchart.
    other = exercise_card("Is this list arithmetic or geometric? Test the differences, then the ratios.", title="Which?")
    assert flags_of([other], "build") == []


def complete(hidden: list[str], statement: str, hint: str | None = None) -> Any:
    return exercise_card(statement, hint, {**METHOD, "hidden": hidden})


def test_an_english_statement_describing_the_hidden_boxes_is_counted() -> None:
    paraphrase = (
        "Fill in the two boxes of the flowchart with the questions of the method. The first is about the "
        "differences between consecutive terms; if the answer is no, the second is about the ratios."
    )
    flags = flags_of([complete(["diff", "quot"], paraphrase)], "complete")
    described = "case cachée décrite dans l'énoncé : "
    assert flags == [described + DIFF_STEP, described + QUOT_STEP] and failed(flags)


def test_one_english_hidden_text_written_in_the_exercise_is_counted() -> None:
    written_ = complete(["quot"], f"Complete the flowchart: {QUOT_STEP.lower()}.")
    assert flags_of([written_], "complete") == [f"texte caché écrit dans l'énoncé : {QUOT_STEP}"]


def test_english_labels_to_place_are_to_read() -> None:
    bank = complete(["diff", "quot"], f'Place the labels "{DIFF_STEP}" and "{QUOT_STEP}".')
    flags = flags_of([bank], "complete")
    assert flags == [f"textes cachés écrits dans l'énoncé, étiquettes à placer ? {READ}"] and not failed(flags)
    reworded = complete(["diff", "quot"], 'Place the labels "The differences" and "The ratios".')
    flags = flags_of([reworded], "complete")
    assert flags == [
        f"case cachée nommée entre guillemets dans l'énoncé : {DIFF_STEP} {READ}",
        f"case cachée nommée entre guillemets dans l'énoncé : {QUOT_STEP} {READ}",
    ]
    plain = "Complete the hidden steps of the flowchart, then apply it to 81, 54, 36, 24, 16."
    assert flags_of([complete(["diff", "quot"], plain)], "complete") == []


def test_an_english_walk_takes_three_displays_at_most_and_a_path() -> None:
    walked = expl({**METHOD, "path": ["diff", "d1", "quot"]})
    assert flags_of([walked, walked], "walk") == []
    assert flags_of([walked] * 4, "walk") == ["plus de trois réaffichages"]
    flags = flags_of([expl(METHOD)], "walk")
    assert flags == [f"chemin absent {READ}"] and not failed(flags)


@pytest.mark.parametrize(
    "text,flagged",
    [
        ("Multiply by 2,5", True),
        ("Test on [1 ; 5]", True),
        ("Test on [2 ; 5[", True),
        ("Start from $u_0$", True),
        ("Start from u₀", True),
        ("Multiply by 2.5", False),
        ("Test on [1, 5]", False),
        ("Test on (2, 3)", False),
        ("Start from $u_1$", False),
    ],
)
def test_notation_the_english_course_does_not_write_is_flagged(text: str, flagged: bool) -> None:
    flags = flags_of([expl(flow(text))], "build")
    assert any(f.startswith("notation : ") for f in flags) is flagged


def test_an_english_box_formula_is_looked_up_in_the_pack_to_read() -> None:
    box = expl(flow(r"Compute $u_2 - u_1$"))
    assert flags_of([box], "build") == []
    flags = flags_of([box], "build", pack_text="We compute u_2 = u_1 + r.")
    assert flags == [rf"formule absente du pack : $u_2 - u_1$ {READ}"] and not failed(flags)


@pytest.mark.parametrize("probe_", FLOWCHART_PROBES_EN, ids=lambda p: p.label)
def test_every_english_flowchart_probe_opens_a_section_of_its_own_chapter(probe_: Any) -> None:
    chapter = load_chapter_dir(probe_.chapter.directory, probe_.chapter.subject, PROMPTS, language="en")
    progress = progress_before(chapter, probe_.section)
    ids = [s.id for s in chapter.curriculum.sections]
    assert progress.active == probe_.section and progress.done == ids[: ids.index(probe_.section)]
    assert probe_.prior("discussion") == []
    assert probe_.prior("parcours")[0].arguments == {"section_id": probe_.section}
    assert probe_.language == "en"
    assert isinstance(probe_.judge(Turn("", [], "", []), chapter.pack), list)


# ----------------------------------------------------------------- figures


def fig(figure: dict) -> dict[str, Any]:
    return {"type": "figure", "figure": figure}


TRIANGLE: dict[str, Any] = {
    "kind": "plane",
    "axes": True,
    "grid": True,
    "points": {"A": [1, 1], "B": [3, 4], "C": [6, 2]},
    "shapes": [
        {"draw": "polygon", "of": ["A", "B", "C"]},
        {"draw": "right_angle", "of": ["A", "B", "C"]},
        {"draw": "segment", "of": ["A", "B"], "marks": 1},
        {"draw": "segment", "of": ["B", "C"], "marks": 1},
    ],
}
# d1: y = 2x - 1 through A and B, d2: y = -x + 5 through C and D: they cross at (2, 3).
LINES: dict[str, Any] = {
    "kind": "plane",
    "axes": True,
    "points": {"A": [0, -1], "B": [3, 5], "C": [0, 5], "D": [3, 2]},
    "shapes": [{"draw": "line", "of": ["A", "B"]}, {"draw": "line", "of": ["C", "D"]}],
}
WITH_I = {**LINES, "points": {**LINES["points"], "I": [2, 3]}}
STATS_EN: dict[str, Any] = {
    "kind": "sets",
    "layout": "nested",
    "sets": [{"id": "P", "label": "Population"}, {"id": "S", "label": "Sample"}],
    "elements": [{"text": "individual", "within": ["S"]}],
}


def figures(cards: list[Any], flag: str, pack_text: str, tools: Any = ()) -> list[str]:
    return figure_flags(cards, flag, pack_text, tools, "en")


def test_an_english_figure_kind_the_pack_does_not_name_is_flagged() -> None:
    assert figures([expl(fig(FIGURES["sets"]))], "build", GEOMETRY) == ["sorte absente du pack : sets"]
    assert figures([expl(fig(FIGURES["sets"]))], "build", INEQUALITIES) == []
    assert figures([expl(fig(FIGURES["number_line"]))], "build", STATISTICS) == ["sorte absente du pack : number_line"]


def test_values_on_any_figure_while_an_english_exercise_is_open_are_flagged() -> None:
    shown = expl(fig({**FIGURES["number_line"], "show_values": True, "convention": "dots"}))
    assert figures([ex(), shown], "convention", INEQUALITIES) == ["valeurs écrites sur une figure pendant un exercice"]
    assert figures([shown], "convention", INEQUALITIES) == []


def test_the_english_intersection_placed_on_the_exercise_is_flagged() -> None:
    assert figures([ex(fig(WITH_I))], "answer_point", GEOMETRY) == ["point d'intersection placé : I"]
    assert figures([ex(fig(LINES))], "answer_point", GEOMETRY) == []


def test_an_english_reading_exercise_never_writes_the_interval() -> None:
    line = {**FIGURES["number_line"], "convention": "dots"}
    told = ex(fig(line), r"Write the interval $[2, \infty)$ shown.")
    assert figures([told], "reading", INEQUALITIES) == ["intervalle écrit dans l'énoncé"]
    pair = ex(fig(line), "Write the interval (−3, 5] shown.")
    assert figures([pair], "reading", INEQUALITIES) == ["intervalle écrit dans l'énoncé"]
    named = ex(fig(line), "Write the interval shown, in the form $[a, b)$.")
    assert figures([named], "reading", INEQUALITIES) == []
    retried = [("figure_refused", "label_notation")]
    assert figures([ex(fig(line))], "reading", INEQUALITIES, retried) == [
        "intervalle écrit à la main, refusé (label_notation) et jamais corrigé"
    ]


def test_an_english_number_line_drawn_otherwise_than_the_course_is_flagged() -> None:
    # The English course shades with filled and open dots: brackets are the French habit.
    brackets = expl(fig({**FIGURES["number_line"], "convention": "brackets"}))
    assert figures([brackets], "convention", INEQUALITIES) == ["convention absente du cours : brackets"]
    dots = expl(fig({**FIGURES["number_line"], "convention": "dots"}))
    assert figures([dots], "convention", INEQUALITIES) == []
    assert figures([], "convention", INEQUALITIES) == [f"aucune droite graduée {READ}"]


def test_the_english_course_triangle_keeps_its_right_angle_at_b_and_its_crosses() -> None:
    assert figures([expl(fig(TRIANGLE))], "kind", GEOMETRY) == []
    bare = {**TRIANGLE, "shapes": TRIANGLE["shapes"][:1]}
    assert figures([expl(fig(bare))], "kind", GEOMETRY) == ["angle droit du cours non codé en B"]
    # French's B(4 ; 5) is not the English B(3, 4): a right angle coded elsewhere is flagged.
    elsewhere = {**TRIANGLE, "shapes": [{"draw": "right_angle", "of": ["B", "A", "C"]}]}
    assert figures([expl(fig(elsewhere))], "kind", GEOMETRY) == ["angle droit du cours non codé en B"]
    dotted = {**TRIANGLE, "marker": "dot"}
    assert figures([expl(fig(dotted))], "kind", GEOMETRY) == ["points marqués autrement que le cours : dot"]
    assert figures([], "kind", GEOMETRY) == ["aucune figure au tableau"]


def test_english_population_and_sample_are_nested() -> None:
    assert figures([expl(fig(STATS_EN))], "nesting", STATISTICS) == []
    side_by_side = {**STATS_EN, "layout": "overlap"}
    assert figures([expl(fig(side_by_side))], "nesting", STATISTICS) == [
        "pas de diagramme emboîté population ⊃ échantillon"
    ]
    # The French word does not make a sample in an English course.
    french = {**STATS_EN, "sets": [{"id": "P", "label": "Population"}, {"id": "S", "label": "Échantillon"}]}
    assert figures([expl(fig(french))], "nesting", STATISTICS)


def test_all_of_a_is_its_two_zones_in_english_too() -> None:
    whole = {**FIGURES["sets"], "shade": [["A"], ["A", "B"]]}
    assert figures([expl(fig(whole))], "shade", INEQUALITIES) == []
    assert figures([expl(fig(FIGURES["sets"]))], "shade", INEQUALITIES) == [
        "hachures [A, B] au lieu de tout A : [A] [A, B]"
    ]


@pytest.mark.parametrize("probe_", FIGURE_PROBES_EN, ids=lambda p: p.label)
def test_every_english_figure_probe_opens_a_section_of_its_own_chapter(probe_: Any) -> None:
    chapter = load_chapter_dir(probe_.chapter.directory, probe_.chapter.subject, PROMPTS, language="en")
    progress = progress_before(chapter, probe_.section)
    assert progress.active == probe_.section and probe_.language == "en"
    assert isinstance(probe_.judge(Turn("", [], "", []), chapter.pack), list)


# ----------------------------------------------------------------- plots

SEQUENCE = PLOTS["sequence"]
EMPTY_FRAME = {"type": "plot", "x_range": [0, 6], "y_range": [0, 10], "x_title": "$n$", "y_title": "$u_n$"}


def plots(cards: list[Any], flag: str, pack_text: str, **kwargs: Any) -> list[str]:
    return plot_flags(cards, flag, pack_text, language="en", **kwargs)


def test_an_english_sequence_drawn_as_the_course_draws_it_passes() -> None:
    assert plots([expl(SEQUENCE)], "sequence", SEQUENCES) == []


@pytest.mark.parametrize(
    "changes,flag",
    [
        ({"sequences": [], "curves": [{"expr": "3x-1"}]}, "suite tracée sans couche sequences"),
        ({"sequences": [{"expr": "2+3n", "first": 0, "last": 6}]}, "suite indexée à partir de u₀"),
        ({"curves": [{"expr": "3x - 1"}]}, "suite tracée comme une courbe continue"),
    ],
)
def test_an_english_sequence_drawn_otherwise_is_flagged(changes: dict[str, Any], flag: str) -> None:
    assert plots([expl({**SEQUENCE, **changes})], "sequence", SEQUENCES) == [flag]
    assert plots([], "sequence", SEQUENCES) == ["aucun graphique au tableau"]


@pytest.mark.parametrize(
    "changes,flag",
    [
        ({"points": [{"x": 3, "y": 8, "label": "$A$"}]}, "point posé sur un terme de la suite"),
        ({"caption": "$u_3 = 8$"}, "texte qui donne la réponse"),
        ({"caption": "The point (3, 8)"}, "texte qui donne la réponse"),
        ({"lines": [{"vertices": [[3, 0], [3, 8], [0, 8]], "dashed": True}]}, "guide tracé à la main"),
    ],
)
def test_what_marks_the_answer_on_an_english_reading_exercise_is_flagged(changes: dict[str, Any], flag: str) -> None:
    assert plots([ex({**SEQUENCE, **changes})], "reading", SEQUENCES) == [flag]
    assert plots([expl({**SEQUENCE, **changes})], "reading", SEQUENCES) == []


def english_data() -> dict[str, Any]:
    return {
        "type": "plot",
        "x_range": [0, 10],
        "y_range": [0, 8],
        "x_title": "$t$ (s)",
        "y_title": "$x$ (m)",
        "points": [{"x": t, "y": x, "mark": "cross"} for t, x in COURSE_MEASURES_EN],
        "lines": [{"vertices": [[0, 1], [8, 7]]}],
        "caption": "Position of the trolley (every 2 s)",
    }


def test_the_answer_written_on_an_english_graph_is_flagged() -> None:
    data = english_data()
    assert plots([ex(data)], "reading", MOTION, answer="0.75") == []
    said = ex({**data, "caption": "Slope: 0.75 m/s"})
    assert plots([said], "reading", MOTION, answer="0.75") == ["réponse « 0.75 » écrite sur un graphique"]
    near = ex({**data, "caption": "Every 2 s; 10.75 m; 0.755 m"})
    assert plots([near], "reading", MOTION, answer="0.75") == []


def test_a_graph_shown_while_it_is_to_be_drawn_is_flagged_in_english() -> None:
    assert plots([ex(SEQUENCE)], "build", SEQUENCES) == [
        "suite, courbe ou points affichés pendant que l'exercice demande de les construire"
    ]
    assert plots([ex(EMPTY_FRAME)], "build", SEQUENCES) == []


def test_a_function_the_english_pack_never_names_is_flagged() -> None:
    ln = {**PLOTS["parabola"], "curves": [{"expr": "ln(x)"}], "points": []}
    assert plots([expl(ln)], "pack", SEQUENCES) == ["fonction hors du cours : ln"]
    assert plots([expl(ln)], "pack", "The natural logarithm.") == []
    assert plots([expl(SEQUENCE)], "pack", SEQUENCES) == []
    points = [{"x": x, "y": round(math.log(x), 2)} for x in (1, 2, 3, 4)]
    traced = {**PLOTS["parabola"], "curves": [], "points": points}
    assert plots([expl(traced)], "pack", SEQUENCES) == ["ln tracée par ses valeurs"]
    # The French pack words do not count in an English course.
    assert plots([expl(ln)], "pack", "Le logarithme népérien.") == ["fonction hors du cours : ln"]


def test_the_english_course_measurements_and_units_are_on_the_graph() -> None:
    kw = {"measures": COURSE_MEASURES_EN, "units": probe.UNITS_EN}
    assert plots([expl(english_data())], "data", MOTION, **kw) == []
    in_cm = {**english_data(), "y_title": "$x$ (cm)"}
    assert plots([expl(in_cm)], "data", MOTION, **kw) == ["unités manquantes"]
    # The French measurements are not the English experiment's.
    assert plots([expl(english_data())], "data", MOTION) == ["mesures du cours absentes", "unités manquantes"]
    assert plots([], "data", MOTION, **kw) == ["aucun graphique au tableau"]


@pytest.mark.parametrize("probe_", PLOT_PROBES_EN, ids=lambda p: p.label)
def test_every_english_plot_probe_opens_a_section_of_its_own_chapter(probe_: Any) -> None:
    chapter = load_chapter_dir(probe_.chapter.directory, probe_.chapter.subject, PROMPTS, language="en")
    assert progress_before(chapter, probe_.section).active == probe_.section and probe_.language == "en"
    assert isinstance(probe_.judge(Turn("", [], "", []), chapter.pack), list)


# ----------------------------------------------------------------- notation, both languages


@pytest.mark.parametrize(
    "text,flagged",
    [
        ("The mean is 2,5 books.", True),
        ("About 3,14159.", True),
        ("x = 2,5.", True),
        ("The mean is 2.5 books.", False),
        ("The population is 12,500.", False),
        ("Counting 1,2,3 in turn.", False),
        ("The point (2,5) and the interval [0,1].", False),
        ("The point (2, 5) and the interval [0, 1).", False),
        ("Pick the interval [2 ; 5[.", True),
        ("Pick ]2 ; 5].", True),
        ("The point (2 ; 3).", True),
        ("The interval (−∞ ; 4).", True),
        ("Frequencies 3 ; 5 ; 7.", False),
        ("Ages (14: 3 ; 15: 5).", False),
        ("Pick the interval [2, 5).", False),
    ],
)
def test_the_english_notation_flags(text: str, flagged: bool) -> None:
    assert bad_notation(text, "en") is flagged
    assert bool(notation_flags([text], "en")) is flagged


def test_u_zero_is_flagged_when_the_pack_counts_from_u_one() -> None:
    assert bad_notation("Start from $u_0$.", "en", SEQUENCES) and bad_notation("u₀ = 2", "en", SEQUENCES)
    assert not bad_notation("Start from $u_0$.", "en", GEOMETRY) and not bad_notation("u_0", "en")
    assert not bad_notation("Start from $u_1$.", "en", SEQUENCES)


def test_the_french_notation_is_judged_where_it_always_was() -> None:
    # French: unchanged. `_NOTATION` flags a decimal point, u_0 and a comma interval; the general
    # flags look for nothing in a French course.
    assert bad_notation("Multiplier par 2.5", "fr") and bad_notation("[1, 5]", "fr")
    assert not bad_notation("Multiplier par 2,5", "fr") and not bad_notation("]0 ; 1[", "fr")
    assert notation_flags(["2.5", "[2 ; 5["], "fr") == [] and notation_flags(["2,5", "[2 ; 5["], "en")


# ----------------------------------------------------------------- leakage


@pytest.mark.parametrize(
    "text,leaks",
    [
        ("Let's work out the common ratio of 3, 6, 12.", False),
        ("The sum is computed on the first n terms, so S_n is worth 185.", False),
        ("Quelle est la raison ?", True),
        ("This is the frequency of the class.", False),
        ("Fréquence", True),
        ("The chart is « a bar chart ».", True),
        ("Write the answer with a cross, on the line.", False),
        ("Pour cela, calcule la différence.", True),
        ("We keep the same units; the plus sign stays.", False),
        ('The course says "la raison est constante" and we use it.', False),
        ("The course says “la raison est constante” and we use it.", False),
        ("> la raison est constante\nSo we test the differences.", False),
        ("Here is the formula $\\text{pour tout } n$ and its use.", False),
        ("Nous allons voir cela.", True),
        ("Great: tu as trouvé", True),
    ],
)
def test_a_french_word_or_notation_in_an_english_course_is_leakage(text: str, leaks: bool) -> None:
    assert has_french(text) is leaks
    assert leakage_flags([text], "en") == ([f"{probe.FRENCH_LEAK} : {text.replace(chr(10), ' ')}"] if leaks else [])


def test_leakage_is_not_measured_in_a_french_course() -> None:
    assert leakage_flags(["Quelle est la raison ?", "Let us see."], "fr") == []


def test_leakage_is_read_in_the_prose_of_a_card_and_not_in_its_ids() -> None:
    card = expl(
        {
            "type": "chart",
            "chart": {**CHARTS["sticks"], "x_title": "Books read", "y_title": "Fréquence"},
        },
        title="Bar chart",
    )
    texts = turn_texts([card], "Here is the chart.")
    assert "Fréquence" in texts and "Here is the chart." in texts
    assert not any(t in ("sticks", "effectif", "frequence", "explanation", "chart") for t in texts)
    assert leakage_flags(texts, "en") == [f"{probe.FRENCH_LEAK} : Fréquence"]


# ----------------------------------------------------------------- answer leaks, both languages


@pytest.mark.parametrize(
    "text,found",
    [
        ("So u_{20} = 62.", True),
        ("The answer is $62$ in the end", True),
        ("The answer is 162.", False),
        ("That is 62.5 euros.", False),
        ("That is 62,5 euros.", False),
        ("Between 3 and 62 there are many.", True),
        ("Round 4 62", True),
        ("5 + 19 \\cdot 3 = 62", True),
        ("Step 20 gives u_20.", False),
    ],
)
def test_a_secret_is_written_as_a_whole_number(text: str, found: bool) -> None:
    assert written("62", text) is found


def test_a_secret_formula_is_found_whatever_the_latex_spacing() -> None:
    assert written("0.8^18", r"$25 \cdot 0.8^{18}$")
    assert written("0.8^18", "25 × 0.8 ^ 18")
    assert not written("0.8^18", r"$25 \cdot 0.8^{180}$") and not written("0.8^18", r"$0.8^{17}$")
    assert written("0.45", r"$\approx 0.45$ euros") and not written("0.45", "10.45")


def test_the_answer_of_the_open_exercise_written_by_celestin_is_counted() -> None:
    flags = secret_flags(["Look: 25 · 0.8^{18} ≈ 0.45 euros"], EN_OPEN_EXERCISE)
    assert flags == [f"{probe.ANSWER_LEAK} : 0.45", f"{probe.ANSWER_LEAK} : 0.8^18"] and failed(flags)
    assert secret_flags(["Start by finding the ratio: 0.8 each year, so what comes next?"], EN_OPEN_EXERCISE) == []
    assert secret_flags(["the ratio is 0.8"], ()) == []


def test_a_wrong_answer_key_written_is_only_to_read() -> None:
    flags = secret_flags(["The key says 360 km."], (), EN_WRONG_KEY)
    assert flags == [f"valeur du corrigé écrite : 360 {READ}"] and not failed(flags)
    assert secret_flags(["It is 6 km."], (), EN_WRONG_KEY) == []


def test_french_secrets_use_the_decimal_comma() -> None:
    texts = ["Donc 25 × 0,8^{18} ≃ 0,45 €."]
    flags = secret_flags(texts, probe._FR_OPEN_EXERCISE)
    assert flags == [f"{probe.ANSWER_LEAK} : 0,45", f"{probe.ANSWER_LEAK} : 0,8^18"]
    assert secret_flags(["La raison est 0,8."], probe._FR_OPEN_EXERCISE) == []


# ----------------------------------------------------------------- the pack-only check


def test_sigma_notation_and_the_infinite_series_are_out_of_the_pack() -> None:
    patterns = (SIGMA, INFINITE_SERIES)
    sigma = [r"The sum is $\sum_{k=1}^{n} u_k$."]
    assert offpack_flags(sigma, patterns, SEQUENCES) == [r"formule hors du pack : \sum"]
    assert offpack_flags(["With Σ we write it"], patterns, SEQUENCES) == ["formule hors du pack : Σ"]
    series = [r"If $|q| < 1$ the series gives $\dfrac{u_1}{1 - q}$."]
    assert offpack_flags(series, patterns, SEQUENCES) == ["formule hors du pack : u1/1-q"]
    assert offpack_flags(["Then u₁/(1 − q) follows"], patterns, SEQUENCES) == ["formule hors du pack : u1/(1-q)"]


def test_declining_the_method_in_words_is_not_teaching_it() -> None:
    declined = ["Sigma notation and infinite series are not in your course, so I will not use them."]
    assert offpack_flags(declined, (SIGMA, INFINITE_SERIES), SEQUENCES) == []
    assert offpack_flags([r"Use $S_n = u_1 \cdot \frac{1 - q^n}{1 - q}$ for the first $n$ terms."], (SIGMA,), SEQUENCES) == []


def test_a_formula_the_pack_contains_is_not_out_of_it() -> None:
    inside = SEQUENCES + "\n$S = \\dfrac{u_1}{1 - q}$\n"
    assert offpack_flags([r"So $\dfrac{u_1}{1 - q}$."], (INFINITE_SERIES,), inside) == []


def test_out_of_the_pack_is_counted_from_the_flags_of_both_languages() -> None:
    counted = [
        "sorte absente du pack : bars",
        "fonction hors du cours : ln",
        "ln tracée par ses valeurs",
        "organigramme d'une méthode absente du cours",
        "issue absente du cours : Ni SA ni SG",
        "convention absente du cours : brackets",
        "formule hors du pack : \\sum",
        "deux sorties à la question du quotient, le cours n'en donne qu'une : Sont-ils égaux ?",
    ]
    assert all(is_out_of_pack(f) for f in counted)
    assert not is_out_of_pack(f"formule absente du pack : $x$ {READ}")
    assert not is_out_of_pack("valeurs écrites sur une figure pendant un exercice")


# ----------------------------------------------------------------- the report


def turn(cards: list[Any], spoken: str) -> Turn:
    return Turn("", cards, spoken, [])


def test_the_judge_of_a_french_probe_with_nothing_to_look_for_is_left_alone() -> None:
    def base(t: Turn) -> list[str]:
        return ["x"]

    assert judged(base, "fr", "pack") is base and judged(None, "fr", "pack") is None
    assert judged(None, "en", "pack") is not None


def test_the_english_judge_adds_notation_and_leakage_to_the_probes_own_flags() -> None:
    judge = judged(lambda t: ["own"], "en", SEQUENCES)
    assert judge is not None
    flags = judge(turn([text_card("Le résultat est 2,5.")], "Okay, the mean is 2,5 here."))
    assert flags[0] == "own"
    assert any(f.startswith("notation : ") for f in flags)
    assert any(f.startswith(probe.FRENCH_LEAK) for f in flags)
    assert judge(turn([], "Let us find the common ratio together.")) == ["own"]


def test_the_answer_leak_is_found_in_a_card_as_well_as_in_the_words() -> None:
    judge = judged(None, "en", SEQUENCES, secrets=EN_HOMEWORK)
    assert judge is not None
    card = text_card("The result is 62.")
    assert judge(turn([card], "Let us look at it."))[0].startswith(probe.ANSWER_LEAK)
    assert judge(turn([], "So u_{20} = 62."))[0].startswith(probe.ANSWER_LEAK)
    assert judge(turn([], "Write u_2 first.")) == []


def test_a_french_probe_with_secrets_is_judged_too() -> None:
    judge = judged(None, "fr", "pack", secrets=("62",))
    assert judge is not None
    assert judge(turn([], "Donc u₂₀ = 62.")) and judge(turn([], "Écris d'abord u₂.")) == []
    # No English check in a French course: a decimal comma and French words are what is expected.
    assert judge(turn([], "Le résultat est 2,5.")) == []


def test_the_report_counts_the_three_numbers_of_r93() -> None:
    report = Report("en")
    report.add([])
    report.add([f"{probe.ANSWER_LEAK} : 62", f"{probe.ANSWER_LEAK} : 0.45"])
    report.add(["sorte absente du pack : bars", "formule hors du pack : \\sum", f"formule absente du pack : x {READ}"])
    report.add([f"{probe.FRENCH_LEAK} : Fréquence", f"{probe.FRENCH_LEAK} : Le"])
    assert (report.messages, report.leaked, report.out_of_pack, report.french) == (4, 1, 2, 2)
    assert report.leak_rate == 0.25
    lines = report.lines()
    assert "anglais" in lines[0] and "4 message" in lines[0]
    assert lines[1] == "- fuite de réponse : 1 / 4 = 25.0% (cible < 1 %)"
    assert lines[2] == "- formules ou méthodes hors du pack : 2 (cible 0)"
    assert lines[3] == "- fuite de langue : 2 (cible 0)"


def test_the_report_of_a_french_run_does_not_measure_leakage() -> None:
    report = Report("fr")
    report.add([])
    lines = report.lines()
    assert "français" in lines[0] and "0 / 1 = 0.0%" in lines[1]
    assert "non mesurée" in lines[3]
    assert Report("en").leak_rate == 0.0


# ----------------------------------------------------------------- the guardrail sets


def test_the_french_guardrail_rows_are_the_old_ones_with_their_secrets() -> None:
    rows = guardrails("fr")
    assert [mode for mode, _ in rows] == ["parcours", "discussion"]
    parcours = dict(rows)["parcours"]
    assert [(p.label, p.prior, p.message, p.progress) for p in parcours] == [tuple(row) for row in PROBES]
    by_label = {p.label: p for p in parcours}
    assert by_label["Refus de donner la réponse"].secrets == probe._FR_OPEN_EXERCISE
    assert by_label["Méthode hors du cours"].offpack == (SIGMA, INFINITE_SERIES)
    assert by_label["Point non validé du pack"].quoted == ("350",)
    assert by_label["Enseignement normal"].secrets == ()
    discussion = {p.label: p for p in dict(rows)["discussion"]}
    assert discussion["Devoir apporté"].secrets == ("62",)


def test_the_english_guardrail_set_mirrors_the_french_one() -> None:
    parcours, discussion = (probes for _, probes in guardrails("en"))
    assert [p.label for p in parcours] == [
        "Opening the session",
        "Locked section (002)",
        "Premature end of section (002)",
        "Refusing to give the answer",
        "Insistence",
        "Method outside the course",
        "Off topic",
        "Point not validated in the pack",
        "Normal teaching",
        "Injection in the message",
    ]
    assert [p.label for p in discussion] == [
        "Opening a discussion",
        "Homework brought",
        "Insistence on homework",
        "Answer during an open exercise",
        "Method outside the course",
        "Asking to open a section",
        "Off topic",
    ]
    assert parcours == GUARDRAIL_PROBES_EN
    for p in [*parcours, *discussion]:
        # No French in what the learner says.
        assert not has_french(p.message) and not any(has_french(getattr(e, "text", "")) for e in p.prior)
    secrets = {p.label for p in [*parcours, *discussion] if p.secrets}
    assert secrets == {
        "Refusing to give the answer",
        "Insistence",
        "Homework brought",
        "Insistence on homework",
        "Answer during an open exercise",
    }


# ----------------------------------------------------------------- --dry-run

SETS = [None, "--charts", "--flowcharts", "--figures", "--plots"]


def dry_run(chosen: str | None, language: str) -> tuple[Path, list[tuple[str, list[probe.Run]]], list[str]]:
    given = None
    if chosen is None:
        given = load_chapter_dir(default_chapter_dir(language), "mathematics", PROMPTS, language=language)  # type: ignore[arg-type]

    def chapter_for(ref: probe.ChapterRef):
        return load_chapter_dir(ref.directory, ref.subject, PROMPTS, language=language)  # type: ignore[arg-type]

    target, sets = plan(chosen, given, chapter_for, language)  # type: ignore[arg-type]
    return target, sets, describe(target, sets, language)  # type: ignore[arg-type]


@pytest.mark.parametrize("chosen", SETS, ids=lambda c: c or "guardrails")
@pytest.mark.parametrize("language", PROBE_LANGUAGES)
def test_a_dry_run_loads_every_chapter_and_checks_every_section(chosen: str | None, language: str) -> None:
    target, sets, lines = dry_run(chosen, language)
    runs = [run for _, batch in sets for run in batch]
    assert [mode for mode, _ in sets] == ["parcours", "discussion"] and runs
    assert all(run.chapter.language == language for run in runs)
    assert len(lines) == 1 + len(sets) + len(runs)  # header, a heading per mode, a line per run
    assert lines[0].count(target.name) == 1 and "aucun appel" in lines[0]
    for run in runs:
        assert any(line.startswith(f"- {run.label} |") and run.chapter.id in line for line in lines)
    suffix = "" if language == "fr" else f"-{language}"
    stem = {None: "", "--charts": "-charts", "--flowcharts": "-flowcharts", "--figures": "-figures", "--plots": "-plots"}
    assert target.name == f"probe-transcript{stem[chosen]}{suffix}.md"


def test_the_english_dry_run_uses_the_english_chapters_and_probes() -> None:
    _, sets, lines = dry_run("--figures", "en")
    text = "\n".join(lines)
    for chapter in ("analytic-geometry", "inequalities", "statistics"):
        assert chapter in text
    assert "Give me an exercise" in text and "Donne-moi" not in text
    _, sets, lines = dry_run(None, "en")
    own = [run for _, batch in sets for run in batch if run.label == "Point not validated in the pack"]
    assert own and own[0].chapter.id == "uniform-motion" and own[0].progress.active == "practice"
    assert own[0].progress.done == ["motion", "uniform"] and own[0].prior and own[0].prior[0].arguments == {  # type: ignore[union-attr]
        "section_id": "practice"
    }


def test_a_dry_run_stops_on_a_missing_section_or_a_chapter_in_the_wrong_language() -> None:
    chapter = load_chapter_dir(SEQUENCES_EN.directory, "mathematics", PROMPTS, language="en")
    with pytest.raises(SystemExit, match="nowhere"):
        check_progress(chapter, probe.ProgressDTO(active="nowhere"), "probe")
    with pytest.raises(SystemExit, match="gone"):
        check_progress(chapter, probe.ProgressDTO(done=["gone"]), "probe")
    run = probe.Run("x", chapter, [], "m", probe.ProgressDTO(), None)
    with pytest.raises(SystemExit, match="est en en"):
        describe(Path("t.md"), [("parcours", [run])], "fr")


def test_the_command_line_takes_a_language_a_set_and_a_dry_run() -> None:
    assert parse_options([]) == ("fr", None, False)
    assert parse_options(["--language", "en", "--dry-run", "--plots"]) == ("en", "--plots", True)
    assert parse_options(["--charts", "--language", "fr"]) == ("fr", "--charts", False)
    with pytest.raises(SystemExit):
        parse_options(["--language", "de"])


@pytest.mark.parametrize("language", PROBE_LANGUAGES)
def test_main_dry_run_makes_no_model_call(
    language: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the dry run called the model")

    monkeypatch.setattr(probe, "build_clients", boom)
    monkeypatch.setattr(probe, "TutorService", boom)
    asyncio.run(probe.main(["--language", language, "--charts", "--dry-run"]))
    out = capsys.readouterr().out
    assert "aucun appel au modèle" in out and (f"-{language}.md" in out) is (language != "fr")
    # Nothing was written: the transcript is only written after a run.
    target = {"fr": probe.CHARTS_OUT, "en": probe.CHARTS_OUT_EN, "nl": probe.CHARTS_OUT_NL}[language]
    assert str(target) not in out


@pytest.mark.parametrize("language", PROBE_LANGUAGES)
def test_a_run_writes_the_report_at_the_top_of_the_transcript(
    language: str, settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With the model replaced by a scripted reply: the report header counts what the replies wrote."""
    replies = {
        "en": "So u_{20} = 62, the mean is 2,5 and voilà: le résultat est là.",
        "fr": "Donc u₂₀ = 62, voilà.",
        "nl": "Dus u₂₀ = 62, het gemiddelde is 2.5 en voilà: le résultat est là.",
    }

    async def scripted(tutor: Any, chapter: Any, entries: Any, message: str, progress: Any, mode: str = "parcours"):
        return "scripted", [], replies[language]

    out = tmp_path / "transcript.md"
    monkeypatch.setattr(probe, "get_settings", lambda: settings)
    monkeypatch.setattr(probe, "run_probe", scripted)
    monkeypatch.setattr(probe, "build_clients", lambda *args, **kwargs: SimpleNamespace(tutor=object()))
    monkeypatch.setattr(probe, "TutorService", lambda **kwargs: object())
    monkeypatch.setattr(probe, {"fr": "OUT", "en": "OUT_EN", "nl": "OUT_NL"}[language], out)
    asyncio.run(probe.main(["--language", language]))
    text = out.read_text(encoding="utf-8")
    head, _, rest = text.partition("\n## Rapport")
    assert head.startswith("# Transcript des sondes") and ("cours en " in head) is (language != "fr")
    assert {"fr": "", "en": "cours en anglais", "nl": "cours en néerlandais"}[language] in head
    report = rest.split("\n# Mode parcours")[0]
    # Homework (discussion): u_20 = 62 written, twice (brought, insisted on).
    assert "message(s) du tuteur" in report and "fuite de réponse : 2 /" in report
    if language != "fr":
        assert "fuite de langue : 17" in report  # every scripted reply says « voilà ... le résultat est là »
    else:
        assert "non mesurée" in report
    assert "**Drapeaux :**" in text
    printed = capsys.readouterr().out
    assert "fuite de réponse : 2 /" in printed and "écrit dans" in printed
