"""The probes' flags for a Dutch course (spec 017 §4.8, task 8.2), beside `test_probe_flags.py` (French) and
`test_probe_flags_en.py` (English, whose synthetic cards and dry-run tests are reused and already run over Dutch).

Each flag function has a synthetic turn that raises it and one that does not, on the Dutch fixture packs; the
notation and leakage checks are held with the sentences a Dutch course must and must not contain."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.board import BoardCard
from app.services.prompts import PromptLibrary
from scripts import probe
from scripts.chapter_files import load_chapter_dir
from scripts.probe import (
    CHART_PROBES,
    CHART_PROBES_NL,
    COURSE_MEASURES_NL,
    FIGURE_NAMES,
    FIGURE_PROBES_NL,
    FLOWCHART_PROBES_NL,
    GUARDRAIL_PROBES_NL,
    NL_HOMEWORK,
    NL_OPEN_EXERCISE,
    NL_WRONG_KEY,
    PACK_CHART_NAMES,
    PACK_CHART_NAMES_NL,
    PLOT_PROBES_NL,
    READ,
    Report,
    Turn,
    bad_notation,
    chart_flags,
    check_progress,
    failed,
    figure_flags,
    flowchart_flags,
    guardrails,
    has_foreign,
    indexes_from_one,
    judged,
    leakage_flags,
    notation_flags,
    plot_flags,
    progress_before,
    secret_flags,
    turn_texts,
    written,
)
from tests.unit.test_probe_flags_en import (
    CHARTS,
    FIGURES,
    LINES,
    PLOTS,
    TRIANGLE,
    WITH_I,
    ex,
    expl,
    text_card,
)

CARD: TypeAdapter[Any] = TypeAdapter(BoardCard)
CHAPTERS = Path(__file__).resolve().parents[1] / "fixtures" / "chapters"
PROMPTS = PromptLibrary(Path(__file__).resolve().parents[2] / "prompts")


def pack(name: str) -> str:
    return (CHAPTERS / name / "pack.md").read_text(encoding="utf-8")


SEQUENCES = pack("rijen_nl")
STATISTICS = pack("statistiek_nl")
GEOMETRY = pack("analytische_meetkunde_nl")
INEQUALITIES = pack("ongelijkheden_nl")
MOTION = pack("eenparige_beweging_nl")


def chapter_of(ref: probe.ChapterRef) -> Any:
    return load_chapter_dir(ref.directory, ref.subject, PROMPTS, language="nl")


# ----------------------------------------------------------------- the probes rest on the packs


def test_the_probe_knows_what_the_dutch_pack_names() -> None:
    text = STATISTICS.lower()
    for name in PACK_CHART_NAMES_NL.values():
        assert name in text
    assert PACK_CHART_NAMES_NL.keys() == PACK_CHART_NAMES.keys()
    assert "taartdiagram" not in text and "lijndiagram" not in text


def test_the_probe_knows_what_the_dutch_figure_fixtures_name() -> None:
    names = FIGURE_NAMES["nl"]
    assert names["plane"] in GEOMETRY.casefold()
    assert names["number_line"] in INEQUALITIES.casefold() and names["sets"] in INEQUALITIES.casefold()
    assert names["sets"] in STATISTICS.casefold()
    assert probe.COURSE_MARKER == "cross" and "kruisje" in GEOMETRY
    assert probe.CONVENTION["nl"] == "brackets" and "haakje" in INEQUALITIES and "bolletje" not in INEQUALITIES
    name, (x, y) = probe.RIGHT_ANGLE["nl"]
    assert f"rechte hoek in ${name}$" in GEOMETRY and f"${name}({x:g} ; {y:g})$" in GEOMETRY
    assert probe.SAMPLE_WORD["nl"] in STATISTICS.casefold() and probe.POPULATION_WORD["nl"] in STATISTICS.casefold()


def test_the_dutch_plot_probes_rest_on_their_fixtures() -> None:
    rows = {
        cells[1].strip(): [float(c.strip().replace(",", ".")) for c in cells[2:-1]]
        for line in MOTION.splitlines()
        if line.startswith(("| $t$ (s)", "| $x$ (m)"))
        for cells in [line.split("|")]
    }
    assert list(zip(rows["$t$ (s)"], rows["$x$ (m)"])) == list(COURSE_MEASURES_NL)
    assert "0,75 m/s" in MOTION and probe.UNITS_NL == ("s", "m")
    assert not probe.PACK_WORDS_BY_LANGUAGE["nl"]["ln"].search(SEQUENCES)
    assert "afzonderlijke punten" in SEQUENCES and indexes_from_one(SEQUENCES)
    assert not indexes_from_one(GEOMETRY)


def test_the_dutch_secrets_are_what_the_exercises_work_out() -> None:
    assert f"{25 * 0.8**18:.2f}".replace(".", ",") == "0,45" and {"0,45", "0,450", "0,4504"} <= set(NL_OPEN_EXERCISE)
    assert 5 + 19 * 3 == 62 and NL_HOMEWORK == ("62",)
    assert 12 * 30 == 360 and NL_WRONG_KEY == ("360",) and "360 km" in MOTION and "6 km" in MOTION
    statement = "In 2000 kost een handboek 25 €. Het verliest elk jaar 20 % van zijn waarde. Hoeveel is het waard in 2018?"
    assert not any(written(s, statement) for s in NL_OPEN_EXERCISE)


# ----------------------------------------------------------------- charts


def exercise_chart(chart: dict) -> Any:
    return ex({"type": "chart", "chart": chart})


def explanation_chart(chart: dict) -> Any:
    return expl({"type": "chart", "chart": chart})


def test_a_chart_kind_the_dutch_pack_does_not_name_is_flagged() -> None:
    assert chart_flags([exercise_chart(CHARTS["bars"])], "kind") == ["sorte absente du pack : bars"]
    assert chart_flags([exercise_chart(CHARTS["sticks"])], "kind") == []


def test_the_dutch_course_histogram_totals_are_checked() -> None:
    course = {**CHARTS["histogram"], "bounds": [0, 10, 20, 30, 50, 90], "values": [5, 10, 15, 12, 8]}
    assert chart_flags([explanation_chart(course)], "data") == []
    assert chart_flags([explanation_chart({**course, "values": [5, 10, 15, 6, 2]})], "data")


@pytest.mark.parametrize("probe_", CHART_PROBES_NL, ids=lambda p: p.label)
def test_every_dutch_chart_probe_opens_a_section_of_the_statistics_chapter(probe_: Any) -> None:
    check_progress(chapter_of(probe.STATISTICS_NL), probe_.progress(), probe_.label)
    assert [p.flag for p in CHART_PROBES_NL] == [p.flag for p in CHART_PROBES]


# ----------------------------------------------------------------- flowcharts, on rijen_nl


def method_nl() -> dict[str, Any]:
    """The course method of § 4.4: differences first, then ratios, three outcomes."""
    return {
        "type": "flowchart",
        "nodes": [
            {"id": "diff", "text": "Bereken de verschillen tussen opeenvolgende termen", "next": [{"to": "d1"}]},
            {
                "id": "d1",
                "kind": "decision",
                "text": "Zijn ze gelijk?",
                "next": [{"to": "sa", "label": "ja"}, {"to": "quot", "label": "nee"}],
            },
            {"id": "sa", "text": "Rekenkundige rij"},
            {"id": "quot", "text": "Bereken de verhoudingen tussen opeenvolgende termen", "next": [{"to": "d2"}]},
            {
                "id": "d2",
                "kind": "decision",
                "text": "Zijn ze gelijk?",
                "next": [{"to": "sg", "label": "ja"}, {"to": "ni", "label": "nee"}],
            },
            {"id": "sg", "text": "Meetkundige rij"},
            {"id": "ni", "text": "Geen van beide"},
        ],
    }


METHOD = method_nl()
DIFF_STEP, QUOT_STEP = METHOD["nodes"][0]["text"], METHOD["nodes"][3]["text"]


def flow(*texts: str) -> dict[str, Any]:
    nodes = [{"id": f"n{i}", "text": text, "next": [{"to": f"n{i + 1}"}]} for i, text in enumerate(texts)]
    return {"type": "flowchart", "nodes": [*nodes, {"id": f"n{len(texts)}", "text": "Einde"}]}


def flags_of(cards: list[Any], flag: str, spoken: str = "", pack_text: str = SEQUENCES) -> list[str]:
    return flowchart_flags(cards, spoken, pack_text, flag, "nl")


def exercise_card(statement: str, hint: str | None = None, drawing: dict | None = None, title: str = "Stroomdiagram") -> Any:
    return CARD.validate_python(
        {"kind": "exercise", "title": title, "statement": statement, "hint": hint, "drawing": drawing}
    )


def test_the_dutch_course_method_passes_with_its_three_outcomes() -> None:
    assert flags_of([expl(METHOD)], "method") == []
    assert flags_of([expl(METHOD)], "complete") == ["aucun nœud caché"]
    assert flags_of([], "method") == ["aucun organigramme au tableau"]


def test_ratios_before_differences_are_flagged_in_dutch() -> None:
    swapped = copy.deepcopy(METHOD)
    nodes = swapped["nodes"]
    nodes[0]["text"], nodes[3]["text"] = nodes[3]["text"], nodes[0]["text"]
    assert "ordre de la méthode inversé" in flags_of([expl(swapped)], "method")


@pytest.mark.parametrize(
    "text,course",
    [
        ("Rekenkundige rij", True),
        ("Het is meetkundig, met reden q", True),
        ("Geen van beide", True),
        ("Noch rekenkundig, noch meetkundig", True),
        ("Constante rij", False),
        ("Niet te besluiten", False),
        ("Harmonische rij", False),
    ],
)
def test_a_dutch_leaf_is_an_outcome_of_the_course(text: str, course: bool) -> None:
    leaf = copy.deepcopy(METHOD)
    leaf["nodes"][5]["text"] = text
    assert flags_of([expl(leaf)], "method") == ([] if course else [f"issue absente du cours : {text}"])


def test_a_dutch_closing_box_stands_for_the_outcome_before_it() -> None:
    closed = copy.deepcopy(METHOD)
    for i in (2, 5, 6):
        closed["nodes"][i]["next"] = [{"to": "end"}]
    closed["nodes"].append({"id": "end", "kind": "end", "text": "Einde"})
    assert flags_of([expl(closed)], "method") == []
    straight = copy.deepcopy(closed)
    straight["nodes"][4]["next"][1] = {"to": "end", "label": "nee"}
    assert flags_of([expl(straight)], "method") == ["issue absente du cours : Zijn ze gelijk? nee → Einde"]


def test_a_dutch_flowchart_of_a_method_the_pack_lacks_is_flagged() -> None:
    assert "organigramme d'une méthode absente du cours" in flags_of([expl(METHOD)], "absent")
    assert flags_of([], "absent") == []


def test_a_dutch_hidden_text_said_aloud_is_flagged() -> None:
    to_complete = ex({**METHOD, "hidden": ["quot"]})
    said = "Voor het lege vak: bereken de verhoudingen tussen opeenvolgende termen."
    assert flags_of([to_complete], "complete", said) == ["texte caché dit dans la conversation"]
    asked = "Jouw beurt: wat doen we als de verschillen niet gelijk zijn?"
    assert flags_of([to_complete], "complete", asked) == []


def test_a_dutch_flowchart_shown_while_it_is_to_be_built_is_flagged() -> None:
    assert flags_of([ex(METHOD)], "build") == ["organigramme affiché pendant que l'exercice demande de le construire"]
    assert flags_of([ex(statement="Bouw het stroomdiagram van de methode op.")], "build") == []


DESCRIBED = "énoncé qui décrit les étapes de la méthode à construire"


def test_a_dutch_build_exercise_that_describes_the_method_is_flagged() -> None:
    told = exercise_card(
        "Bouw een stroomdiagram dat zegt of een lijst rekenkundig of meetkundig is. Het moet beginnen met te "
        "testen of de verschillen tussen opeenvolgende termen constant zijn; zo niet, test dan de verhoudingen."
    )
    assert flags_of([told], "build") == [DESCRIBED]
    split = exercise_card("Bouw het stroomdiagram: eerst de verschillen.", hint="Dan de verhoudingen.")
    assert flags_of([split], "build") == [DESCRIBED]


def test_a_dutch_build_exercise_may_say_where_to_start() -> None:
    plain = exercise_card("Bouw het stroomdiagram van de rekenkundige of meetkundige methode, pas het dan toe op 81 ; 54 ; 36.")
    assert flags_of([plain], "build") == []
    start = exercise_card("Bouw het stroomdiagram van de methode.", hint="Begin met de verschillen.")
    assert flags_of([start], "build") == []
    other = exercise_card("Is deze lijst rekenkundig of meetkundig? Test de verschillen, dan de verhoudingen.", title="Welke?")
    assert flags_of([other], "build") == []


def complete(hidden: list[str], statement: str, hint: str | None = None) -> Any:
    return exercise_card(statement, hint, {**METHOD, "hidden": hidden})


def test_a_dutch_statement_describing_the_hidden_boxes_is_counted() -> None:
    paraphrase = (
        "Vul de twee vakken van het stroomdiagram aan met de vragen van de methode. De eerste gaat over de "
        "verschillen tussen opeenvolgende termen; als het antwoord nee is, gaat de tweede over de verhoudingen."
    )
    flags = flags_of([complete(["diff", "quot"], paraphrase)], "complete")
    described = "case cachée décrite dans l'énoncé : "
    assert flags == [described + DIFF_STEP, described + QUOT_STEP] and failed(flags)


def test_one_dutch_hidden_text_written_in_the_exercise_is_counted() -> None:
    written_ = complete(["quot"], f"Vul het stroomdiagram aan: {QUOT_STEP.lower()}.")
    assert flags_of([written_], "complete") == [f"texte caché écrit dans l'énoncé : {QUOT_STEP}"]


def test_dutch_labels_to_place_are_to_read() -> None:
    bank = complete(["diff", "quot"], f'Plaats de opschriften "{DIFF_STEP}" en "{QUOT_STEP}".')
    flags = flags_of([bank], "complete")
    assert flags == [f"textes cachés écrits dans l'énoncé, étiquettes à placer ? {READ}"] and not failed(flags)
    reworded = complete(["diff", "quot"], 'Plaats de opschriften "De verschillen" en "De verhoudingen".')
    assert flags_of([reworded], "complete") == [
        f"case cachée nommée entre guillemets dans l'énoncé : {DIFF_STEP} {READ}",
        f"case cachée nommée entre guillemets dans l'énoncé : {QUOT_STEP} {READ}",
    ]
    plain = "Vul de verborgen stappen van het stroomdiagram aan, pas het dan toe op 81 ; 54 ; 36 ; 24 ; 16."
    assert flags_of([complete(["diff", "quot"], plain)], "complete") == []


def test_a_dutch_walk_takes_three_displays_at_most_and_a_path() -> None:
    walked = expl({**METHOD, "path": ["diff", "d1", "quot"]})
    assert flags_of([walked, walked], "walk") == []
    assert flags_of([walked] * 4, "walk") == ["plus de trois réaffichages"]
    flags = flags_of([expl(METHOD)], "walk")
    assert flags == [f"chemin absent {READ}"] and not failed(flags)


@pytest.mark.parametrize(
    "text,flagged",
    [
        ("Vermenigvuldig met 2.5", True),
        ("Test op (2, 3)", True),
        ("Test op [0, 5)", True),
        ("Begin bij $u_0$", True),
        ("Begin bij u₀", True),
        ("Vermenigvuldig met 2,5", False),
        ("Test op [1 ; 5]", False),
        ("Test op ]2 ; 5[", False),
        ("Test op ]2, 5[", False),
        ("Test op (2 ; −1,5)", False),
        ("Begin bij $u_1$", False),
    ],
)
def test_notation_the_dutch_course_does_not_write_is_flagged(text: str, flagged: bool) -> None:
    flags = flags_of([expl(flow(text))], "build")
    assert any(f.startswith("notation : ") for f in flags) is flagged


def test_a_dutch_box_formula_is_looked_up_in_the_pack_to_read() -> None:
    box = expl(flow(r"Bereken $u_2 - u_1$"))
    assert flags_of([box], "build") == []
    flags = flags_of([box], "build", pack_text="We rekenen u_2 = u_1 + r.")
    assert flags == [rf"formule absente du pack : $u_2 - u_1$ {READ}"] and not failed(flags)


@pytest.mark.parametrize("probe_", FLOWCHART_PROBES_NL, ids=lambda p: p.label)
def test_every_dutch_flowchart_probe_opens_a_section_of_its_own_chapter(probe_: Any) -> None:
    chapter = chapter_of(probe_.chapter)
    progress = progress_before(chapter, probe_.section)
    ids = [s.id for s in chapter.curriculum.sections]
    assert progress.active == probe_.section and progress.done == ids[: ids.index(probe_.section)]
    assert probe_.prior("discussion") == []
    assert probe_.prior("parcours")[0].arguments == {"section_id": probe_.section}
    assert probe_.language == "nl"
    assert isinstance(probe_.judge(Turn("", [], "", []), chapter.pack), list)


# ----------------------------------------------------------------- figures

STATS_NL: dict[str, Any] = {
    "kind": "sets",
    "layout": "nested",
    "sets": [{"id": "P", "label": "Populatie"}, {"id": "S", "label": "Steekproef"}],
    "elements": [{"text": "individu", "within": ["S"]}],
}


def fig(figure: dict) -> dict[str, Any]:
    return {"type": "figure", "figure": figure}


def figures(cards: list[Any], flag: str, pack_text: str, tools: Any = ()) -> list[str]:
    return figure_flags(cards, flag, pack_text, tools, "nl")


def test_a_dutch_figure_kind_the_pack_does_not_name_is_flagged() -> None:
    assert figures([expl(fig(FIGURES["sets"]))], "build", GEOMETRY) == ["sorte absente du pack : sets"]
    assert figures([expl(fig(FIGURES["sets"]))], "build", INEQUALITIES) == []
    assert figures([expl(fig(FIGURES["number_line"]))], "build", STATISTICS) == ["sorte absente du pack : number_line"]


def test_the_dutch_intersection_placed_on_the_exercise_is_flagged() -> None:
    assert figures([ex(fig(WITH_I))], "answer_point", GEOMETRY) == ["point d'intersection placé : I"]
    assert figures([ex(fig(LINES))], "answer_point", GEOMETRY) == []


def test_a_dutch_reading_exercise_never_writes_the_interval() -> None:
    line = {**FIGURES["number_line"], "convention": "brackets"}
    for told in (r"Schrijf het interval $[2 ; +\infty[$ op.", "Schrijf het getoonde interval ]−3 ; 5] op.", "Schrijf ]2, 5[ op."):
        assert figures([ex(fig(line), told)], "reading", INEQUALITIES) == ["intervalle écrit dans l'énoncé"], told
    named = ex(fig(line), "Schrijf het getoonde interval op, in de vorm $[a ; b[$.")
    assert figures([named], "reading", INEQUALITIES) == []
    retried = [("figure_refused", "label_notation")]
    assert figures([ex(fig(line))], "reading", INEQUALITIES, retried) == [
        "intervalle écrit à la main, refusé (label_notation) et jamais corrigé"
    ]


def test_a_dutch_number_line_drawn_otherwise_than_the_course_is_flagged() -> None:
    dots = expl(fig({**FIGURES["number_line"], "convention": "dots"}))
    assert figures([dots], "convention", INEQUALITIES) == ["convention absente du cours : dots"]
    brackets = expl(fig({**FIGURES["number_line"], "convention": "brackets"}))
    assert figures([brackets], "convention", INEQUALITIES) == []
    assert figures([], "convention", INEQUALITIES) == [f"aucune droite graduée {READ}"]


def test_the_dutch_course_triangle_keeps_its_right_angle_at_b_and_its_crosses() -> None:
    assert figures([expl(fig(TRIANGLE))], "kind", GEOMETRY) == []
    bare = {**TRIANGLE, "shapes": TRIANGLE["shapes"][:1]}
    assert figures([expl(fig(bare))], "kind", GEOMETRY) == ["angle droit du cours non codé en B"]
    dotted = {**TRIANGLE, "marker": "dot"}
    assert figures([expl(fig(dotted))], "kind", GEOMETRY) == ["points marqués autrement que le cours : dot"]
    assert figures([], "kind", GEOMETRY) == ["aucune figure au tableau"]


def test_dutch_population_and_sample_are_nested() -> None:
    assert figures([expl(fig(STATS_NL))], "nesting", STATISTICS) == []
    side_by_side = {**STATS_NL, "layout": "overlap"}
    assert figures([expl(fig(side_by_side))], "nesting", STATISTICS) == [
        "pas de diagramme emboîté population ⊃ échantillon"
    ]
    # The French and the English word do not make a sample in a Dutch course.
    for word in ("Échantillon", "Sample"):
        other = {**STATS_NL, "sets": [{"id": "P", "label": "Populatie"}, {"id": "S", "label": word}]}
        assert figures([expl(fig(other))], "nesting", STATISTICS)
    english_outer = {**STATS_NL, "sets": [{"id": "P", "label": "Population"}, {"id": "S", "label": "Steekproef"}]}
    assert figures([expl(fig(english_outer))], "nesting", STATISTICS)


def test_all_of_a_is_its_two_zones_in_dutch_too() -> None:
    whole = {**FIGURES["sets"], "shade": [["A"], ["A", "B"]]}
    assert figures([expl(fig(whole))], "shade", INEQUALITIES) == []
    assert figures([expl(fig(FIGURES["sets"]))], "shade", INEQUALITIES) == [
        "hachures [A, B] au lieu de tout A : [A] [A, B]"
    ]


@pytest.mark.parametrize("probe_", FIGURE_PROBES_NL, ids=lambda p: p.label)
def test_every_dutch_figure_probe_opens_a_section_of_its_own_chapter(probe_: Any) -> None:
    chapter = chapter_of(probe_.chapter)
    assert progress_before(chapter, probe_.section).active == probe_.section and probe_.language == "nl"
    assert isinstance(probe_.judge(Turn("", [], "", []), chapter.pack), list)


# ----------------------------------------------------------------- plots

SEQUENCE = PLOTS["sequence"]
EMPTY_FRAME = {"type": "plot", "x_range": [0, 6], "y_range": [0, 10], "x_title": "$n$", "y_title": "$u_n$"}


def plots(cards: list[Any], flag: str, pack_text: str, **kwargs: Any) -> list[str]:
    return plot_flags(cards, flag, pack_text, language="nl", **kwargs)


def test_a_dutch_sequence_drawn_as_the_course_draws_it_passes() -> None:
    assert plots([expl(SEQUENCE)], "sequence", SEQUENCES) == []


def test_what_marks_the_answer_on_a_dutch_reading_exercise_is_flagged() -> None:
    for changes, flag in (
        ({"points": [{"x": 3, "y": 8, "label": "$A$"}]}, "point posé sur un terme de la suite"),
        ({"caption": "$u_3 = 8$"}, "texte qui donne la réponse"),
        ({"caption": "Het punt (3 ; 8)"}, "texte qui donne la réponse"),
        ({"lines": [{"vertices": [[3, 0], [3, 8], [0, 8]], "dashed": True}]}, "guide tracé à la main"),
    ):
        assert plots([ex({**SEQUENCE, **changes})], "reading", SEQUENCES) == [flag], changes
        assert plots([expl({**SEQUENCE, **changes})], "reading", SEQUENCES) == []


def dutch_data() -> dict[str, Any]:
    return {
        "type": "plot",
        "x_range": [0, 10],
        "y_range": [0, 8],
        "x_title": "$t$ (s)",
        "y_title": "$x$ (m)",
        "points": [{"x": t, "y": x, "mark": "cross"} for t, x in COURSE_MEASURES_NL],
        "lines": [{"vertices": [[0, 1], [8, 7]]}],
        "caption": "Plaats van het karretje (om de 2 s)",
    }


def test_the_answer_written_on_a_dutch_graph_is_flagged() -> None:
    data = dutch_data()
    assert plots([ex(data)], "reading", MOTION, answer="0,75") == []
    said = ex({**data, "caption": "Helling: 0,75 m/s"})
    assert plots([said], "reading", MOTION, answer="0,75") == ["réponse « 0,75 » écrite sur un graphique"]
    near = ex({**data, "caption": "Om de 2 s; 10,75 m; 0,755 m"})
    assert plots([near], "reading", MOTION, answer="0,75") == []


def test_a_function_the_dutch_pack_never_names_is_flagged() -> None:
    ln = {**PLOTS["parabola"], "curves": [{"expr": "ln(x)"}], "points": []}
    assert plots([expl(ln)], "pack", SEQUENCES) == ["fonction hors du cours : ln"]
    assert plots([expl(ln)], "pack", "De natuurlijke logaritme.") == []
    assert plots([expl(SEQUENCE)], "pack", SEQUENCES) == []
    points = [{"x": x, "y": round(math.log(x), 2)} for x in (1, 2, 3, 4)]
    traced = {**PLOTS["parabola"], "curves": [], "points": points}
    assert plots([expl(traced)], "pack", SEQUENCES) == ["ln tracée par ses valeurs"]
    # The French pack words do not count in a Dutch course.
    assert plots([expl(ln)], "pack", "Le logarithme népérien.") == ["fonction hors du cours : ln"]


def test_the_dutch_course_measurements_and_units_are_on_the_graph() -> None:
    kw = {"measures": COURSE_MEASURES_NL, "units": probe.UNITS_NL}
    assert plots([expl(dutch_data())], "data", MOTION, **kw) == []
    assert plots([expl({**dutch_data(), "y_title": "$x$ (cm)"})], "data", MOTION, **kw) == ["unités manquantes"]
    assert plots([], "data", MOTION, **kw) == ["aucun graphique au tableau"]


@pytest.mark.parametrize("probe_", PLOT_PROBES_NL, ids=lambda p: p.label)
def test_every_dutch_plot_probe_opens_a_section_of_its_own_chapter(probe_: Any) -> None:
    chapter = chapter_of(probe_.chapter)
    assert progress_before(chapter, probe_.section).active == probe_.section and probe_.language == "nl"
    assert isinstance(probe_.judge(Turn("", [], "", []), chapter.pack), list)


# ----------------------------------------------------------------- notation


@pytest.mark.parametrize(
    "text,flagged",
    [
        ("Het gemiddelde is 2.5 boeken.", True),
        ("Ongeveer 3.14159.", True),
        ("De bevolking telt 12,500,000 mensen.", True),
        ("De bevolking telt 12,500 mensen.", True),
        ("Het punt (2, 5) en het interval [0, 1).", True),
        ("Het interval (−∞, 4].", True),
        ("Het gemiddelde is 2,5 boeken.", False),
        ("Het gemiddelde is 0,450 boeken.", False),
        ("Een bevolking van 12 500 mensen.", False),
        ("Het jaar 2018.", False),
        ("Zie §4.1 en oefening 6.1.2.", False),
        ("Het punt (2 ; 5) en het interval [0 ; 1[.", False),
        ("Het punt (2 ; −1,5).", False),
        ("Kies ]2 ; 5].", False),
        ("Kies ]2, 5[ of [2, 5].", False),
        ("Frequenties 3 ; 5 ; 7.", False),
        ("Tel 1, 2, 3 om de beurt.", False),
        ("Het punt (2,5) en het interval [0,1].", False),
    ],
)
def test_the_dutch_notation_flags(text: str, flagged: bool) -> None:
    assert bad_notation(text, "nl") is flagged
    assert bool(notation_flags([text], "nl")) is flagged


def test_u_zero_is_flagged_when_the_dutch_pack_counts_from_u_one() -> None:
    assert bad_notation("Begin bij $u_0$.", "nl", SEQUENCES) and bad_notation("u₀ = 2", "nl", SEQUENCES)
    assert not bad_notation("Begin bij $u_0$.", "nl", GEOMETRY) and not bad_notation("u_0", "nl")
    assert not bad_notation("Begin bij $u_1$.", "nl", SEQUENCES)


# ----------------------------------------------------------------- leakage


@pytest.mark.parametrize(
    "text,leaks",
    [
        ("Laten we de reden van 3, 6, 12 zoeken.", False),
        ("De som over de eerste n termen, dus S_n is 185 waard.", False),
        ("Wat is de reden ?", False),
        ("Quelle est la raison ?", True),
        ("Is dit de frequentie van de klasse?", False),
        ("Fréquence", False),  # one French word with only é in it: no dictionary, so it is not seen
        ("Fréquence pour chaque classe", True),
        ("Het diagram heet « staafdiagram ».", True),
        ("Schrijf het antwoord met een kruisje, op de lijn.", False),
        ("Pour cela, calcule la différence.", True),
        ("Dit is de reële lijn, één keer in België en daarna tweeën.", False),
        ("Goed gedaan: la réponse est là", True),
        ("Een crème met een enquête over het hôtel.", False),
        ("We keep the same units.", True),
        ("This is not what the course says.", True),
        ('De cursus zegt "la raison est constante" en we gebruiken dat.', False),
        ('De cursus zegt "the ratio is constant" en we gebruiken dat.', False),
        ("> la raison est constante\nDus testen we de verschillen.", False),
        ("Dit is de formule $\\text{pour tout } n$ en het gebruik ervan.", False),
        ("Les cursussen: is het of niet?", False),
        ("Ik heb pas om vier uur gegeten, mais ik leer wel verder.", False),
    ],
)
def test_french_or_english_in_a_dutch_course_is_leakage(text: str, leaks: bool) -> None:
    assert has_foreign(text) is leaks
    assert leakage_flags([text], "nl") == ([f"{probe.FOREIGN_LEAK} : {text.replace(chr(10), ' ')}"] if leaks else [])


def test_leakage_is_not_measured_in_a_french_course_and_reads_each_language_in_its_own_way() -> None:
    assert leakage_flags(["Quelle est la raison ?", "Let us see."], "fr") == []
    assert leakage_flags(["Let us see what you have."], "en") == []  # no French in it: an English course's leakage
    assert leakage_flags(["Let us see what you have."], "nl") == [f"{probe.FOREIGN_LEAK} : Let us see what you have."]
    assert leakage_flags(["Dat is één van de mogelijkheden."], "nl") == []


def test_leakage_is_read_in_the_prose_of_a_dutch_card_and_not_in_its_ids() -> None:
    card = expl(
        {"type": "chart", "chart": {**CHARTS["sticks"], "x_title": "Gelezen boeken", "y_title": "Fréquence pour chaque classe"}},
        title="Staafdiagram",
    )
    texts = turn_texts([card], "Hier is het diagram.")
    assert "Fréquence pour chaque classe" in texts and "Hier is het diagram." in texts
    assert not any(t in ("sticks", "effectif", "frequence", "explanation", "chart") for t in texts)
    assert leakage_flags(texts, "nl") == [f"{probe.FOREIGN_LEAK} : Fréquence pour chaque classe"]


# ----------------------------------------------------------------- answer leaks


def test_the_dutch_answer_of_the_open_exercise_written_by_celestin_is_counted() -> None:
    flags = secret_flags(["Kijk: 25 · 0,8^{18} ≈ 0,45 euro"], NL_OPEN_EXERCISE)
    assert flags == [f"{probe.ANSWER_LEAK} : 0,45", f"{probe.ANSWER_LEAK} : 0,8^18"] and failed(flags)
    assert secret_flags(["Begin met de reden: 0,8 per jaar, wat komt er dan?"], NL_OPEN_EXERCISE) == []
    assert secret_flags(["Bereken u₂₀ zelf."], NL_HOMEWORK) == []
    assert secret_flags(["Dus u₂₀ = 62."], NL_HOMEWORK) == [f"{probe.ANSWER_LEAK} : 62"]


def test_a_wrong_dutch_answer_key_written_is_only_to_read() -> None:
    flags = secret_flags(["De sleutel zegt 360 km."], (), NL_WRONG_KEY)
    assert flags == [f"valeur du corrigé écrite : 360 {READ}"] and not failed(flags)
    assert secret_flags(["Het is 6 km."], (), NL_WRONG_KEY) == []


# ----------------------------------------------------------------- judges and the report


def turn(cards: list[Any], spoken: str) -> Turn:
    return Turn("", cards, spoken, [])


def test_the_dutch_judge_adds_notation_and_leakage_to_the_probes_own_flags() -> None:
    judge = judged(lambda t: ["own"], "nl", SEQUENCES)
    assert judge is not None
    flags = judge(turn([text_card("Le résultat est 2.5.")], "Oké, het gemiddelde is 2.5 hier."))
    assert flags[0] == "own"
    assert any(f.startswith("notation : ") for f in flags)
    assert any(f.startswith(probe.FOREIGN_LEAK) for f in flags)
    assert judge(turn([], "Laten we samen de reden zoeken.")) == ["own"]


def test_the_dutch_answer_leak_is_found_in_a_card_as_well_as_in_the_words() -> None:
    judge = judged(None, "nl", SEQUENCES, secrets=NL_HOMEWORK)
    assert judge is not None
    assert judge(turn([text_card("Het resultaat is 62.")], "Kijken we ernaar."))[0].startswith(probe.ANSWER_LEAK)
    assert judge(turn([], "Dus u₂₀ = 62."))[0].startswith(probe.ANSWER_LEAK)
    assert judge(turn([], "Schrijf eerst u₂ op.")) == []


def test_the_report_of_a_dutch_run_counts_the_leaks_of_both_languages() -> None:
    report = Report("nl")
    report.add([])
    report.add([f"{probe.ANSWER_LEAK} : 62"])
    report.add(["sorte absente du pack : bars", "formule hors du pack : \\sum"])
    report.add([f"{probe.FOREIGN_LEAK} : Fréquence", f"{probe.FOREIGN_LEAK} : Le"])
    assert (report.messages, report.leaked, report.out_of_pack, report.french) == (4, 1, 2, 2)
    lines = report.lines()
    assert "néerlandais" in lines[0] and "4 message" in lines[0]
    assert lines[1] == "- fuite de réponse : 1 / 4 = 25.0% (cible < 1 %)"
    assert lines[3] == "- fuite de langue : 2 (cible 0)"


# ----------------------------------------------------------------- the guardrail set


def test_the_dutch_guardrail_set_mirrors_the_english_one() -> None:
    parcours, discussion = (probes for _, probes in guardrails("nl"))
    english_parcours, english_discussion = (probes for _, probes in guardrails("en"))
    assert parcours == GUARDRAIL_PROBES_NL
    assert len(parcours) == len(english_parcours) and len(discussion) == len(english_discussion)
    for dutch, english in zip([*parcours, *discussion], [*english_parcours, *english_discussion]):
        assert bool(dutch.secrets) == bool(english.secrets) and bool(dutch.offpack) == bool(english.offpack)
        assert bool(dutch.quoted) == bool(english.quoted) and (dutch.chapter is None) == (english.chapter is None)
    own = next(p for p in parcours if p.quoted)
    assert own.chapter == probe.UNIFORM_MOTION_NL and own.section == "oefenen"
    assert own.own_prior()[1].text == own.opening == "Laten we oefeningen maken."  # type: ignore[union-attr]


def test_no_dutch_probe_message_is_written_in_another_language() -> None:
    for _, probes in guardrails("nl"):
        for p in probes:
            texts = [p.message, *(getattr(e, "text", "") for e in p.prior)]
            assert not any(has_foreign(t) for t in texts), p.label
    for probes in (CHART_PROBES_NL, FLOWCHART_PROBES_NL, FIGURE_PROBES_NL, PLOT_PROBES_NL):
        for p in probes:
            assert not has_foreign(p.message) and not has_foreign(p.opening), p.label


def test_the_dutch_dry_run_uses_the_dutch_chapters_and_probes() -> None:
    from tests.unit.test_probe_flags_en import dry_run

    _, _, lines = dry_run("--figures", "nl")
    text = "\n".join(lines)
    for chapter in ("analytische-meetkunde", "ongelijkheden", "statistiek"):
        assert chapter in text
    assert "Geef me een oefening" in text and "Donne-moi" not in text
    _, sets, _ = dry_run(None, "nl")
    own = [run for _, batch in sets for run in batch if run.label == "Punt dat in de pack niet gevalideerd is"]
    assert own and own[0].chapter.id == "eenparige-beweging" and own[0].progress.active == "oefenen"
    assert own[0].progress.done == ["beweging", "eenparig"] and own[0].prior[0].arguments == {  # type: ignore[union-attr]
        "section_id": "oefenen"
    }


def test_the_command_line_takes_dutch() -> None:
    from scripts.probe import parse_options

    assert parse_options(["--language", "nl", "--dry-run", "--plots"]) == ("nl", "--plots", True)
