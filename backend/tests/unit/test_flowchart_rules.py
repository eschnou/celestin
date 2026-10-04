from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.domain.board import BoardCard, card_blocks
from app.domain.flowchart import FlowchartBlock
from app.services.tools.charts import Refusal
from app.services.tools import flowcharts
from app.services.tools.flowcharts import (
    MAX_QUESTION,
    ROW_BUDGET,
    flowchart_refusal,
    flowcharts_refusal,
    leaks,
    reading_order,
)
from tests.fixtures.curricula import ctx_for
from tests.unit.test_chart_models import VALID as CHARTS
from tests.unit.test_flowchart_models import VALID, valid

CARD: TypeAdapter[Any] = TypeAdapter(BoardCard)
CTX = ctx_for()

Change = Callable[[dict[str, Any]], None]


def explanation(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "explanation", "title": "Méthode", "blocks": list(blocks)}


def worked(drawing: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "worked_example", "title": "Méthode", "statement": "3 ; 6 ; 12", "drawing": drawing, "steps": [{"tex": "q = 2"}]}


def exercise(
    drawing: dict[str, Any],
    statement: str = "Complète l'organigramme.",
    hint: str | None = None,
    title: str = "À compléter",
) -> dict[str, Any]:
    return {"kind": "exercise", "title": title, "statement": statement, "drawing": drawing, "hint": hint}


def refusal(card: dict[str, Any]) -> Refusal | None:
    parsed = CARD.validate_python(card)
    items = [(path, block) for path, block in card_blocks(parsed) if isinstance(block, FlowchartBlock)]
    return flowcharts_refusal(items, parsed, CTX)


def changed(name: str, change: Change, **fields: Any) -> dict[str, Any]:
    block = {**valid(name), **fields}
    change(block)
    return block


def node(block: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(n for n in block["nodes"] if n["id"] == node_id)


def keep(_: dict[str, Any]) -> None:
    pass


def setting(node_id: str, **fields: Any) -> Change:
    return lambda block: node(block, node_id).update(fields)


def adding(**new: Any) -> Change:
    return lambda block: block["nodes"].append(new)


def both(*changes: Change) -> Change:
    def run(block: dict[str, Any]) -> None:
        for change in changes:
            change(block)

    return run


# A root question whose two answers are questions too: two diamonds side by side.
TWO_QUESTIONS = {
    "type": "flowchart",
    "nodes": [
        {"id": "a", "kind": "decision", "text": "$n$ pair ?", "next": [{"to": "b", "label": "oui"}, {"to": "c", "label": "non"}]},
        {"id": "b", "kind": "decision", "text": "$n > 10$ ?", "next": [{"to": "d", "label": "oui"}]},
        {"id": "c", "kind": "decision", "text": "$n > 5$ ?", "next": [{"to": "d", "label": "oui"}]},
        {"id": "d", "text": "Afficher $n$"},
    ],
}

# A question beside two steps, three rows down.
QUESTION_AND_STEPS = {
    "type": "flowchart",
    "nodes": [
        {"id": "a", "text": "Lire", "next": [{"to": "r"}]},
        {"id": "r", "kind": "decision", "text": "R ?", "next": [{"to": "p", "label": "oui"}, {"to": "q", "label": "non"}]},
        {"id": "p", "kind": "decision", "text": "P ?", "next": [{"to": "d3", "label": "oui"}, {"to": "t", "label": "non"}]},
        {"id": "q", "text": "Q", "next": [{"to": "u"}]},
        {"id": "d3", "kind": "decision", "text": "D ?", "next": [{"to": "v", "label": "oui"}]},
        {"id": "t", "text": "T"},
        {"id": "u", "text": "U"},
        {"id": "v", "text": "V"},
    ],
}


# The method with its formulas: the question repeats the step's formula.
FORMULA_METHOD = {
    "type": "flowchart",
    "nodes": [
        {"id": "diff", "text": r"Calculer $u_{n+1} - u_n$", "next": [{"to": "d1"}]},
        {
            "id": "d1",
            "kind": "decision",
            "text": r"$u_{n+1} - u_n$ constante ?",
            "next": [{"to": "sa", "label": "oui"}, {"to": "quot", "label": "non"}],
        },
        {"id": "sa", "text": "C'est une SA"},
        {"id": "quot", "text": r"Calculer $\frac{u_{n+1}}{u_n}$", "next": [{"to": "d2"}]},
        {"id": "d2", "kind": "decision", "text": r"$\frac{u_{n+1}}{u_n}$ constant ?", "next": [{"to": "sg", "label": "oui"}]},
        {"id": "sg", "text": "C'est une SG"},
    ],
}


@pytest.mark.parametrize("name", sorted(VALID))
def test_every_valid_flowchart_passes_everywhere_it_may_sit(name: str) -> None:
    assert refusal(explanation(VALID[name])) is None
    assert refusal(worked(VALID[name])) is None
    assert refusal(exercise(VALID[name])) is None


CASES: list[tuple[str, dict[str, Any], str, str]] = [
    ("per card", explanation(VALID["method"], VALID["loop"]), "per_card", "au plus un organigramme"),
    (
        "path on an exercise",
        exercise(changed("loop", keep, path=["debut", "lire"])),
        "exercise_path",
        "accompagne un exercice ouvert : pas de path",
    ),
    (
        "hidden in an explanation",
        explanation(changed("method", keep, hidden=["sa"])),
        "hidden_place",
        "hidden ne sert que sur le drawing d'un exercise",
    ),
    ("hidden in a worked example", worked(changed("method", keep, hidden=["sa"])), "hidden_place", "Ici, montre"),
    (
        "an id twice",
        explanation(changed("method", setting("sa", id="diff"))),
        "ids",
        "l'identifiant « diff » sert à nodes[0] et à nodes[2]",
    ),
    ("hidden twice", exercise(changed("method", keep, hidden=["sa", "sa"])), "ids", "hidden cite « sa » deux fois"),
    (
        "an exit to nowhere",
        explanation(changed("method", setting("diff", next=[{"to": "zz"}]))),
        "unknown_id",
        "nodes[0].next[0].to renvoie à « zz »",
    ),
    ("a path to nowhere", explanation(changed("method", keep, path=["diff", "zz"])), "unknown_id", "path[1] renvoie"),
    ("a hidden nowhere", exercise(changed("method", keep, hidden=["zz"])), "unknown_id", "hidden[0] renvoie"),
    (
        "a self loop",
        explanation(changed("method", setting("sa", next=[{"to": "sa"}]))),
        "self_loop",
        "nodes[2] (« sa ») sort vers lui-même",
    ),
    ("a start not first", explanation(changed("loop", setting("lire", kind="start"))), "start", "vient en premier"),
    ("two starts", explanation(changed("loop", setting("fin", kind="start"))), "start", "il n'y en a qu'un"),
    (
        "back to the start",
        explanation(changed("loop", setting("incr", next=[{"to": "debut"}]))),
        "start",
        "nodes[5] (« incr ») ramène au nœud start",
    ),
    (
        "an end that goes on",
        explanation(changed("loop", setting("fin", next=[{"to": "lire"}]))),
        "end",
        "nodes[7] (« fin ») est un nœud end",
    ),
    (
        "a step with two exits",
        explanation(changed("method", setting("diff", next=[{"to": "d1"}, {"to": "sa"}]))),
        "exits",
        "nodes[0] (« diff ») a 2 sorties",
    ),
    (
        "an io box with two exits",
        explanation(changed("loop", setting("lire", next=[{"to": "init"}, {"to": "afficher"}]))),
        "exits",
        "nodes[1] (« lire ») a 2 sorties",
    ),
    (
        "a start with two exits",
        explanation(changed("loop", setting("debut", next=[{"to": "lire"}, {"to": "init"}]))),
        "exits",
        "nodes[0] (« debut ») a 2 sorties",
    ),
    (
        "a question without exit",
        explanation(changed("method", setting("d2", next=[]))),
        "decision",
        "la question nodes[4] (« d2 ») n'a pas de sortie",
    ),
    (
        "an answer without label",
        explanation(changed("method", setting("d1", next=[{"to": "sa", "label": "oui"}, {"to": "quot"}]))),
        "decision",
        "nodes[1].next[1] n'a pas d'étiquette",
    ),
    (
        "one answer twice",
        explanation(changed("method", setting("d1", next=[{"to": "sa", "label": "Oui"}, {"to": "quot", "label": " oui"}]))),
        "decision",
        "portent l'étiquette « ",
    ),
    (
        "both answers to one node",
        explanation(changed("method", setting("d1", next=[{"to": "sa", "label": "oui"}, {"to": "sa", "label": "non"}]))),
        "decision",
        "mènent à « sa »",
    ),
    (
        "a long question",
        explanation(changed("method", setting("d1", text="x" * (MAX_QUESTION - 1) + " ?"))),
        "decision_text",
        "dépasse 40 caractères",
    ),
    (
        "a blank box",
        explanation(changed("method", setting("sa", text="   "))),
        "blank",
        "nodes[2].text est vide",
    ),
    (
        "a blank answer",
        explanation(changed("method", setting("d1", next=[{"to": "sa", "label": " "}, {"to": "quot", "label": "non"}]))),
        "blank",
        "nodes[1].next[0].label est vide ; écris sa réponse",
    ),
    (
        "a blank label on a step",
        explanation(changed("method", setting("diff", next=[{"to": "d1", "label": "  "}]))),
        "blank",
        "nodes[0].next[0].label est vide ; écris-la, ou retire-la",
    ),
    ("a blank caption", explanation(changed("method", keep, caption=" ")), "blank", "caption est vide"),
    (
        "one answer twice, spaced differently in TeX",
        explanation(
            changed("method", setting("d1", next=[{"to": "sa", "label": r"$\Delta>0$"}, {"to": "quot", "label": r"$\Delta > 0$"}]))
        ),
        "decision",
        "portent l'étiquette « $\\Delta > 0$ »",
    ),
    (
        "a node nothing leads to",
        explanation(changed("method", adding(id="x", text="Isolé"))),
        "unreachable",
        "de nodes[0] à nodes[6] (« x »)",
    ),
    (
        "a dead end beside an end",
        explanation(changed("loop", both(setting("incr", next=[{"to": "x"}]), adding(id="x", text="Rien")))),
        "dead_end",
        "nodes[8] (« x ») n'a pas de sortie",
    ),
    (
        "two questions side by side",
        explanation(TWO_QUESTIONS),
        "wide",
        "nodes[1] (« b ») et nodes[2] (« c ») se retrouvent côte à côte",
    ),
    (
        "a question beside two steps",
        explanation(QUESTION_AND_STEPS),
        "wide",
        "nodes[4] (« d3 »), nodes[5] (« t ») et nodes[6] (« u »)",
    ),
    (
        "a path that jumps",
        explanation(changed("loop", keep, path=["debut", "init"])),
        "path",
        "path passe de « debut » à « init »",
    ),
    (
        "a lone hidden text in the statement",
        exercise(changed("method", keep, hidden=["sa"]), statement="Si les différences sont égales, c'est une SA."),
        "hidden_leak",
        "nodes[2] (« sa ») se lit dans statement",
    ),
    (
        "a lone hidden text in the hint",
        exercise(changed("method", keep, hidden=["quot"]), hint="Pense à calculer les quotients entre termes consécutifs."),
        "hidden_leak",
        "se lit dans hint",
    ),
    (
        "a hidden text in another box",
        exercise(changed("method", setting("sg", text="Sinon, c'est une SA ?"), hidden=["sa"])),
        "hidden_leak",
        "se lit dans drawing.nodes[5].text",
    ),
    (
        "a hidden text on an arrow",
        exercise(changed("method", setting("d1", next=[{"to": "sa", "label": "c'est une SA"}, {"to": "quot", "label": "non"}]), hidden=["sa"])),
        "hidden_leak",
        "se lit dans drawing.nodes[1].next[0].label",
    ),
    (
        "a hidden formula in the statement",
        exercise(changed("loop", keep, hidden=["incr"]), statement=r"Quelle case suit $S \leftarrow S+u_i$ ? Indice : $i\leftarrow i+1$."),
        "hidden_leak",
        "se lit dans statement",
    ),
    (
        "a lone hidden text in the title",
        exercise(changed("method", keep, hidden=["sa"]), title="C'est une SA ?"),
        "hidden_leak",
        "nodes[2] (« sa ») se lit dans title",
    ),
    (
        "a hidden text in the caption",
        exercise(changed("method", keep, hidden=["sa", "sg"], caption="Si oui, c'est une SA.")),
        "hidden_leak",
        "nodes[2] (« sa ») se lit dans drawing.caption",
    ),
    (
        "a hidden formula inside a longer one",
        exercise(changed("loop", keep, hidden=["incr"]), statement=r"À chaque tour : $S \leftarrow S + u_i ; i \leftarrow i + 1$."),
        "hidden_leak",
        "nodes[5] (« incr ») se lit dans statement",
    ),
    (
        "two hidden, one formula inside a longer one in a box",
        exercise(changed("loop", setting("afficher", text=r"Afficher $S$ ($i \leftarrow i + 1$ fait)"), hidden=["ajout", "incr"])),
        "hidden_leak",
        "nodes[5] (« incr ») se lit dans drawing.nodes[6].text",
    ),
    (
        "two hidden, one formula in a box",
        exercise(changed("loop", setting("afficher", text=r"Afficher $S$ après $i \leftarrow i + 1$"), hidden=["ajout", "incr"])),
        "hidden_leak",
        "nodes[5] (« incr ») se lit dans drawing.nodes[6].text",
    ),
]


@pytest.mark.parametrize("card,rule,named", [case[1:] for case in CASES], ids=[case[0] for case in CASES])
def test_each_rule_refuses_and_names_the_field(card: dict[str, Any], rule: str, named: str) -> None:
    found = refusal(card)
    assert found is not None
    assert found[0] == rule, found
    assert named in found[1], found[1]
    if rule != "per_card":
        at = "blocks[0]" if card["kind"] == "explanation" else "drawing"
        assert found[1].startswith(f"L'organigramme {at}"), found[1]


def test_a_lone_hidden_text_in_the_statement_says_how_to_make_a_word_bank() -> None:
    found = refusal(exercise(changed("method", keep, hidden=["sa"]), statement="C'est une SA ?"))
    assert found is not None and "cache au moins deux cases" in found[1]
    elsewhere = refusal(exercise(changed("method", setting("sg", text="C'est une SA"), hidden=["sa"])))
    assert elsewhere is not None and "cache au moins deux cases" not in elsewhere[1]


def test_boundaries_are_accepted() -> None:
    # A one-exit question (the pack gives no « ni SA ni SG »), leaves without exits
    # when there is no end, a question beside a step, the while loop's back edge.
    for name in ("method", "nested", "loop"):
        assert refusal(explanation(VALID[name])) is None
    # Exactly 40 characters of question.
    question = "x" * (MAX_QUESTION - 2) + " ?"
    assert len(question) == MAX_QUESTION
    assert refusal(explanation(changed("method", setting("d1", text=question)))) is None
    # Three steps side by side: a question's two answers and a step's exit.
    three = changed("nested", both(setting("two", next=[{"to": "x"}]), adding(id="x", text="X")))
    assert refusal(explanation(three)) is None


def test_answers_that_differ_only_in_case_inside_tex_are_two_answers() -> None:
    block = changed("method", setting("d1", next=[{"to": "sa", "label": r"$\Delta > 0$"}, {"to": "quot", "label": r"$\delta > 0$"}]))
    assert refusal(explanation(block)) is None


def test_four_hidden_boxes_are_accepted() -> None:
    assert refusal(exercise(changed("loop", keep, hidden=["init", "ajout", "incr", "afficher"]))) is None


FOUR_STEPS = {
    "type": "flowchart",
    "nodes": [
        {"id": "r", "kind": "decision", "text": "R ?", "next": [{"to": "p", "label": "oui"}, {"to": "q", "label": "non"}]},
        {"id": "p", "kind": "decision", "text": "P ?", "next": [{"to": "a", "label": "oui"}, {"to": "b", "label": "non"}]},
        {"id": "q", "kind": "decision", "text": "Q ?", "next": [{"to": "c", "label": "oui"}, {"to": "d", "label": "non"}]},
        {"id": "a", "text": "A"},
        {"id": "b", "text": "B"},
        {"id": "c", "text": "C"},
        {"id": "d", "text": "D"},
    ],
}


def test_four_steps_side_by_side_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # A row takes its nodes from the exits of the row above, and a row within
    # budget has three exits at most: four steps side by side always sit under a
    # row that is too wide already, and the rule reports that row first.
    found = refusal(explanation(FOUR_STEPS))
    assert found is not None and found[0] == "wide"
    assert "nodes[1] (« p ») et nodes[2] (« q »)" in found[1]
    # The weighing itself, rows given: four steps weigh 4, three weigh 3.
    method = FlowchartBlock.model_validate(VALID["method"])
    steps = ["diff", "sa", "quot", "sg"]
    assert all(n.kind == "step" for n in method.nodes if n.id in steps)
    in_a_row = {"d1": 0, "diff": 1, "sa": 1, "quot": 1, "sg": 1, "d2": 2}
    monkeypatch.setattr(flowcharts, "layers", lambda _: (in_a_row, set()))
    found = flowchart_refusal(method, "blocks[0]")
    assert found is not None and found[0] == "wide", found
    assert "nodes[0] (« diff »), nodes[2] (« sa »), nodes[3] (« quot ») et nodes[5] (« sg »)" in found[1]
    assert ROW_BUDGET == 3
    monkeypatch.setattr(flowcharts, "layers", lambda _: ({**in_a_row, "sg": 3}, set()))
    assert flowchart_refusal(method, "blocks[0]") is None


def test_a_path_may_walk_a_loop_twice_or_start_mid_chart() -> None:
    twice = ["test", "ajout", "incr", "test", "ajout", "incr", "test", "afficher"]
    assert refusal(explanation(changed("loop", keep, path=twice))) is None
    assert refusal(explanation(changed("loop", keep, path=["init", "test"]))) is None
    assert refusal(worked(changed("loop", keep, path=["debut", "lire", "init", "test"]))) is None


def test_a_chart_beside_a_flowchart_is_not_a_second_flowchart() -> None:
    card = explanation({"type": "chart", "chart": CHARTS["sticks"]}, VALID["method"])
    assert refusal(card) is None


def test_what_the_leak_rule_lets_through() -> None:
    # « Fin » is too short to look for.
    assert refusal(exercise(changed("loop", keep, hidden=["fin"]), statement="Que se passe-t-il à la fin ?")) is None
    # Whole words: « raison » is not in « raisonnement ».
    raison = changed("method", setting("sa", text="Raison"), hidden=["sa"])
    assert refusal(exercise(raison, statement="Explique ton raisonnement.")) is None
    # Two hidden boxes: the statement may list their texts as labels to place.
    bank = "Place « C'est une SA » et « C'est une SG » dans les cases."
    assert refusal(exercise(changed("method", keep, hidden=["sa", "sg"]), statement=bank)) is None
    # A formula under four characters is the chapter's notation, not an answer.
    short = changed("method", setting("sa", text="$u_n$"), hidden=["sa"])
    assert refusal(exercise(short, statement="Que vaut $u_n$ ?")) is None
    # A hidden question whose answers stay on their arrows.
    assert refusal(exercise(changed("method", keep, hidden=["d1"]))) is None
    # A hidden box with words is not given away by its formula alone: the method's
    # own notation shows in the boxes around it.
    assert refusal(exercise(changed("nested", keep, hidden=["calc"]))) is None
    assert refusal(exercise(FORMULA_METHOD | {"hidden": ["d1"]})) is None
    assert refusal(exercise(FORMULA_METHOD | {"hidden": ["diff", "d2"]})) is None


def test_shape_rules_come_first() -> None:
    # An exit to nowhere also leaves a node unreachable: the exit is reported.
    dangling = changed("method", setting("d1", next=[{"to": "sa", "label": "oui"}, {"to": "zz", "label": "non"}]))
    found = refusal(explanation(dangling))
    assert found is not None and found[0] == "unknown_id"
    # A path on an exercise is reported before a broken graph.
    broken = changed("method", setting("sa", id="diff"), path=["diff"])
    found = refusal(exercise(broken))
    assert found is not None and found[0] == "exercise_path"


def test_leaks_compares_whole_words_and_formulas() -> None:
    assert leaks("C'est une SA", "Décide si c'est une SA ou une SG.")
    assert not leaks("Raison", "Explique ton raisonnement.")
    assert not leaks("Fin", "à la fin")
    assert leaks(r"$i \leftarrow i + 1$", r"on fait $i\leftarrow i+1$ ensuite")
    assert leaks(r"$S \leftarrow S + u_i$", r"Afficher $S \leftarrow S + u_i$ puis $i$")
    assert not leaks("$u_n$", "Que vaut $u_n$ ?")


def test_leaks_looks_for_five_letters_and_formulas_of_four() -> None:
    # Five letters or digits (MIN_SECRET) are looked for, four are not.
    assert leaks("Somme", "Calcule la somme des termes.")
    assert leaks("$u_{12}$", "Que vaut $u_{12}$ ?")
    assert not leaks("Test", "Fais le test.")
    # A formula of four characters (MIN_FORMULA) is found inside a longer one, of three not.
    assert leaks("$2n+1$", "Le terme $u_{2n+1}$ ?")
    assert not leaks("$n+1$", "Le terme $u_{n+1}$ ?")


def test_leaks_finds_a_formula_inside_another_as_whole_symbols() -> None:
    assert leaks(r"$i \leftarrow i + 1$", r"À chaque tour : $S \leftarrow S + u_i ; i \leftarrow i + 1$")
    assert leaks(r"Si $i \leqslant n$", r"Tant que $i \leqslant n + 1$")
    assert not leaks(r"$i \leftarrow i + 1$", r"Puis $i \leftarrow i + 10$.")
    assert not leaks("$a+1$", r"Puis $\beta+1$.")
    # A text with words gives itself away as a whole run only.
    assert not leaks(r"Calculer $\Delta$", r"$\Delta > 0$ ?")
    assert not leaks(r"$u_{n+1} - u_n$ constante ?", r"Calculer $u_{n+1}-u_n$")
    assert leaks(r"$u_{n+1} - u_n$ constante ?", r"Est-ce que $u_{n+1}-u_n$ constante ?")


def test_reading_order_is_the_boards() -> None:
    block = FlowchartBlock.model_validate(
        {
            "type": "flowchart",
            "nodes": [
                {"id": "10", "kind": "decision", "text": "Q ?", "next": [{"to": "b", "label": "non"}, {"to": "2", "label": "oui"}]},
                {"id": "2", "text": "A"},
                {"id": "b", "text": "B", "next": [{"to": "c"}]},
                {"id": "c", "text": "C"},
                {"id": "seul", "text": "Seul"},
            ],
        }
    )
    assert reading_order(block) == [0, 2, 3, 1, 4]
    loop = FlowchartBlock.model_validate(VALID["loop"])
    assert reading_order(loop) == [0, 1, 2, 3, 4, 5, 6, 7]


# --- placeholder (after the probe run: « ? » typed as box text) -----------------


@pytest.mark.parametrize("text", ["?", " ? ", "…", "...", "___", "? ?", "« ? »", "( ? )", "$?$", r"$\ldots$"])
def test_a_box_whose_text_is_a_placeholder_is_refused(text: str) -> None:
    found = refusal(exercise(changed("method", setting("sa", text=text))))
    assert found is not None and found[0] == "placeholder"
    assert "nodes[2].text" in found[1] and "hidden" in found[1]


# The verification's worded holes (specs/009-board-drawings/README.md, finding #16), then
# their case, accent and punctuation variants.
HOLE_PHRASES = [
    "À compléter",
    "à compléter…",
    "??? à trouver",
    "(à remplir)",
    "… ?",
    "Étape manquante",
    "A COMPLETER !",
    "Case à compléter",
    "Étape 3 : ?",
    "Case nº 2 à compléter",
    "Nœud caché",
    "[à placer]",
    "Réponse ?",
    "Mystère",
]


@pytest.mark.parametrize("text", HOLE_PHRASES)
def test_a_box_whose_whole_text_is_a_hole_phrase_is_refused(text: str) -> None:
    found = refusal(exercise(changed("method", setting("sa", text=text))))
    assert found is not None and found[0] == "placeholder", found
    assert found[1].startswith(f"L'organigramme drawing : nodes[2].text, « {text.strip()} », marque un trou"), found[1]
    assert "hidden" in found[1]


def test_a_hole_phrase_is_refused_on_a_question_too() -> None:
    found = refusal(explanation(changed("method", setting("d2", text="Question à trouver ?"))))
    assert found is not None and found[0] == "placeholder"
    assert "nodes[4].text" in found[1]


@pytest.mark.parametrize(
    "text",
    [
        "Sont-ils égaux ?",
        "$q$ ?",
        "C'est une SA…",
        # A hole phrase inside a real step is the step.
        "Compléter le tableau",
        "Trouver la raison",
        "Calculer la valeur manquante",
        "Réponse : $q = 2$",
        "Afficher « ? »",
        "Étape suivante",
        "Case vide ?",
        "Compléter",
        "A",
        "$0$",
    ],
)
def test_a_real_text_is_not_a_placeholder(text: str) -> None:
    assert refusal(explanation(changed("method", setting("sa", text=text)))) is None


@pytest.mark.parametrize(
    "text",
    ["□", "⋯", "{ ? }", "<?>", "？", "À compléter par l'élève", "À toi de compléter", "Étape manquante ici"],
)
def test_more_placeholder_shapes_are_refused(text: str) -> None:
    found = refusal(exercise(changed("method", setting("sa", text=text))))
    assert found is not None and found[0] == "placeholder"


@pytest.mark.parametrize("text", ["Compléter le tableau", "À toi de jouer : calcule $u_2$", "Case vide ?"])
def test_real_steps_near_hole_words_pass(text: str) -> None:
    assert refusal(explanation(changed("method", setting("sa", text=text)))) is None
