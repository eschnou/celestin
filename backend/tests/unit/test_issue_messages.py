"""Spec 010 R5.6, §4.9: the reasons a content edit is refused, for the student's editor.

Each coded producer says the same thing in French as it always did (its `message`, which
the authoring model also reads), and says it in English from its code. An issue nobody has
coded yet falls back to its French message: the known gap, kept visible by the last test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.api.routes import courses as courses_routes  # noqa: F401  (imported to load the module)
from app.domain.curriculum import check_curriculum
from app.domain.errors import ContentInvalid
from app.domain.messages import CATALOGS, render
from app.domain.messages.issues import render_issue, render_where
from app.domain.pack import ContentIssue, index_pack
from app.domain.references import reference_issues
from app.services.authoring.agent import _repair_message  # type: ignore[attr-defined]
from tests.unit.test_pack import maths, template

APP = Path(__file__).resolve().parents[2] / "app"

PACK_MUTATIONS = {
    "pack.title_missing": lambda t: t.replace("# Les fonctions du premier degré\n", "", 1),
    "pack.section_missing": lambda t: t.replace("## 5. Vocabulaire", "## 5. Lexique"),
    "pack.subsection_parent": lambda t: t.replace("### 4.2 Pente", "### 3.2 Pente"),
    "pack.subsection_duplicate": lambda t: t.replace("### 4.2 Pente", "### 4.1 Pente"),
    "pack.exercise_duplicate": lambda t: t.replace("#### 6.1.2 Lecture", "#### 6.1.1 Lecture"),
    "pack.exercise_parent": lambda t: t.replace("#### 6.1.2 Lecture", "#### 6.2.2 Lecture"),
    "pack.exercise_section": lambda t: t.replace("La pente vaut $a$.", "#### 4.2.1\nLa pente vaut $a$."),
    "pack.exercise_required": lambda t: t.replace("#### 6.1.1\n", "").replace("#### 6.1.2 Lecture\n", ""),
    "pack.title_multiple": lambda t: t + "\n# Un second titre\n",
    "pack.section_unexpected": lambda t: t.replace("## 7. Points à vérifier", "## Annexe\n\n## 7. Points à vérifier"),
    "pack.title_too_long": lambda t: t.replace("# Les fonctions du premier degré", "# " + "x" * 300),
}


def issues_of(mutate) -> list[ContentIssue]:
    index, issues = index_pack(mutate(maths()), template("mathematics"))
    assert index is None
    return issues


@pytest.mark.parametrize("code", sorted(PACK_MUTATIONS))
def test_a_pack_issue_is_the_same_sentence_in_french_and_says_it_in_english(code: str) -> None:
    coded = [i for i in issues_of(PACK_MUTATIONS[code]) if i.code == code]
    assert coded, f"no issue with code {code}"
    for issue in coded:
        assert render_issue(issue, "fr")["message"] == issue.message
        english = render_issue(issue, "en")["message"]
        assert english != issue.message and "{" not in english


def test_the_order_and_the_length_issues() -> None:
    text = maths()
    voc = "## 5. Vocabulaire\n\n**Mots du cours, à employer** : pente, ordonnée à l'origine.\n\n"
    swapped = text.replace(voc, "").replace("## 2. Prérequis", voc + "## 2. Prérequis")
    _, issues = index_pack(swapped, template("mathematics"))
    order = next(i for i in issues if i.code == "pack.sections_order")
    assert render_issue(order, "fr")["message"] == order.message
    assert render_issue(order, "en")["message"] == "the sections are not in the template's order"
    _, long = index_pack(maths(), template("mathematics"), max_chars=100)
    too_long = next(i for i in long if i.code == "pack.too_long")
    assert render_issue(too_long, "fr")["message"] == too_long.message
    assert render_issue(too_long, "en")["message"].startswith("the document is over 100 characters (")


SECTION = {"id": "intro", "kind": "teach", "title": "Intro", "goal": "g", "done_when": "d", "beats": ["b"]}


@pytest.mark.parametrize(
    ("section_patch", "code"),
    [
        ({"beats": []}, "curriculum.teach_beats"),
        ({"exercises": ["6.1.1"]}, "curriculum.teach_extras"),
        ({"kind": "practise", "beats": [], "exercises": [], "count": 2}, "curriculum.exercises_required"),
        ({"kind": "practise", "beats": [], "exercises": ["6.1.1"]}, "curriculum.count_required"),
        ({"kind": "synthesis", "beats": ["b"], "exercises": ["6.1.1"], "count": 1}, "curriculum.beats_forbidden"),
    ],
)
def test_a_curriculum_rule_keeps_its_french_and_has_an_english(section_patch: dict, code: str) -> None:
    curriculum, issues = check_curriculum({"id": "chap", "title": "T", "sections": [{**SECTION, **section_patch}]})
    assert curriculum is None
    issue = next(i for i in issues if i.code == code)
    assert render_issue(issue, "fr")["message"] == issue.message
    assert render_issue(issue, "en")["message"] != issue.message
    assert issue.where == "section « intro »"  # the editor parses this form


def test_a_duplicate_section_id() -> None:
    _, issues = check_curriculum({"id": "chap", "title": "T", "sections": [SECTION, {**SECTION, "title": "Autre"}]})
    issue = next(i for i in issues if i.code == "curriculum.duplicate_id")
    assert render_issue(issue, "fr")["message"] == issue.message == "identifiant de section en double : intro"
    assert render_issue(issue, "en")["message"] == "duplicate section id: intro"


def test_a_field_error_passes_the_validators_own_message_through() -> None:
    _, issues = check_curriculum({"id": "chap", "title": "T", "sections": [{**SECTION, "title": ""}]})
    issue = next(i for i in issues if i.code == "curriculum.field")
    assert issue.params["field"] == "title"
    assert render_issue(issue, "fr")["message"] == issue.message  # « title : … »
    assert render_issue(issue, "en")["message"] == f"title: {issue.params['msg']}"


def test_a_whole_curriculum_error() -> None:
    _, issues = check_curriculum({"id": "chap", "title": "T", "sections": []})
    issue = next(i for i in issues if i.code == "curriculum.error")
    assert render_issue(issue, "fr")["message"] == issue.message


def test_reference_issues() -> None:
    index, _ = index_pack(maths(), template("mathematics"))
    assert index is not None
    sections = [
        {**SECTION, "pack": ["4.2", "§9.9"], "id": "intro"},
        {"id": "exos", "kind": "practise", "title": "E", "goal": "g", "done_when": "d", "count": 1,
         "exercises": ["9.9.9", "§8", "n'importe quoi"]},
    ]
    curriculum, issues = check_curriculum({"id": "chap", "title": "T", "sections": sections})
    assert curriculum is not None, issues
    found = reference_issues(curriculum, index)
    assert {i.code for i in found} == {
        "references.section_ref",
        "references.section_missing",
        "references.exercise_missing",
        "references.exercise_ref",
    }
    for issue in found:
        assert render_issue(issue, "fr")["message"] == issue.message
        assert render_issue(issue, "en")["message"] != issue.message
    missing = next(i for i in found if i.code == "references.exercise_missing")
    assert render_issue(missing, "en")["message"] == "exercise 9.9.9 doesn't exist in the content"


def test_an_uncoded_issue_keeps_its_french_message() -> None:
    issue = ContentIssue("§ 4.2", "titre manquant")
    assert render_issue(issue, "en") == {"where": "§ 4.2", "message": "titre manquant"}
    assert render_issue(issue, "fr") == {"where": "§ 4.2", "message": "titre manquant"}


def test_where_is_said_in_the_interface_language_except_the_form_the_editor_parses() -> None:
    assert render_where("titre", "en") == "title"
    assert render_where("exercice 6.1.4", "en") == "exercise 6.1.4"
    assert render_where("section n°3", "en") == "section no. 3"
    assert render_where("document", "en") == "document"
    assert render_where("§ 5", "en") == "§ 5"
    assert render_where("section « suites »", "en") == "section « suites »"
    assert render_where("titre", "fr") == "titre"


def test_a_content_invalid_body_renders_its_issues_per_language() -> None:
    issues = issues_of(PACK_MUTATIONS["pack.title_multiple"])
    error = ContentInvalid(issues)
    french = error.body("fr")
    english = error.body("en")
    assert french["code"] == english["code"] == "content_invalid"
    assert french["issues"][0] == {"where": issues[0].where, "message": issues[0].message}
    assert english["issues"][0] == {"where": "title", "message": "the document can only have one level-1 title"}
    assert english["message"] == "The content isn't valid. Fix the points shown."


def test_the_repair_prompt_does_not_depend_on_codes() -> None:
    coded = ContentIssue("§ 4.2", "titre manquant", "pack.title_missing", {})
    plain = ContentIssue("§ 4.2", "titre manquant")
    what = "Le contenu"
    assert _repair_message(what, [coded]) == _repair_message(what, [plain])
    assert "- § 4.2 : titre manquant" in _repair_message(what, [coded])


def test_every_issue_code_is_in_both_catalogs() -> None:
    codes = set(PACK_MUTATIONS) | {
        "pack.sections_order", "pack.too_long",
        "references.section_ref", "references.section_missing", "references.exercise_missing",
        "references.exercise_ref", "curriculum.teach_beats", "curriculum.teach_extras",
        "curriculum.exercises_required", "curriculum.count_required", "curriculum.beats_forbidden",
        "curriculum.duplicate_id", "curriculum.field", "curriculum.error", "chapter.no_content",
    }
    for catalog in CATALOGS.values():
        assert all(f"issue.{code}" in catalog for code in codes), sorted(
            code for code in codes if f"issue.{code}" not in catalog
        )
    assert render("issue.chapter.no_content", "en") == "this chapter doesn't have any content yet"


def _uncoded_producers() -> set[str]:
    """Files that still build a ContentIssue without a code: the known gap."""
    found: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "ContentIssue"
                and len(node.args) < 3
                and not any(k.arg == "code" for k in node.keywords)
            ):
                found.add(str(path.relative_to(APP)))
    return found


def test_the_producers_without_a_code_are_the_model_only_ones() -> None:
    """These issues go to the authoring model for repair and never to the student's editor
    (transcription pages, the agent's own failures). A new uncoded producer fails here so
    that it is a decision, not an accident."""
    assert _uncoded_producers() == {"domain/transcription.py", "services/authoring/agent.py"}


def test_every_interface_language_has_its_where_words() -> None:
    """Spec 017 §4.3: a language with no entry would read the English words by default."""
    from app.domain.locale import LOCALES
    from app.domain.messages.issues import WHERE_WORDS

    assert set(WHERE_WORDS) == set(LOCALES)


def test_a_dutch_reader_gets_dutch_words_and_reasons() -> None:
    """Spec 017 R1.7: `where` and the reason, in the interface language; an uncoded issue keeps its French message."""
    assert render_where("titre", "nl") == "titel" and render_where("exercice 6.1.2", "nl") == "oefening 6.1.2"
    assert render_where("section n°3", "nl") == "sectie nr. 3" and render_where("§ 4.2", "nl") == "§ 4.2"
    coded = ContentIssue("§ 4.2", "titre manquant", "pack.title_missing", {})
    assert render_issue(coded, "nl")["message"] == "het document moet beginnen met een titel “# Titel van het hoofdstuk”"
    plain = ContentIssue("§ 4.2", "titre manquant")
    assert render_issue(plain, "nl") == {"where": "§ 4.2", "message": "titre manquant"}
    wrong = ContentIssue("document", "x", "pack.wrong_language", {"found_language": "fr", "expected_language": "en"})
    assert render_issue(wrong, "nl")["message"] == (
        "het document volgt het model in het Frans, maar deze cursus is in het Engels"
    )
