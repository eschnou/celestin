"""Spec 011 R4.4–R4.6, tasks 7.2–7.4: packs, titles and repair reasons in the course's language.

French stays in `test_pack.py`, `test_curriculum.py` and `test_issue_messages.py`, untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.content import validate_content
from app.domain.curriculum import check_curriculum, curriculum_from_json, parse_curriculum
from app.domain.messages.issues import issue_text, render_issue
from app.domain.pack import ContentIssue, chapter_title, index_pack, parse_template
from tests.fixtures.curricula import curriculum

BACKEND = Path(__file__).resolve().parents[2]
PACKS = Path(__file__).resolve().parents[1] / "fixtures" / "packs"


def template(subject: str, language: str):
    path = BACKEND / "prompts" / "templates" / f"{subject}.pack.{language}.md"
    return parse_template(path.read_text(encoding="utf-8"), path, language)  # type: ignore[arg-type]


FR, EN = template("mathematics", "fr"), template("mathematics", "en")
FRENCH_PACK = (PACKS / "maths_valid.md").read_text(encoding="utf-8")
ENGLISH_PACK = (PACKS / "maths_valid_en.md").read_text(encoding="utf-8")


# --- chapter titles ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Chapter 3: sequences", "Sequences"),
        ("Chapter 3 - Sequences", "Sequences"),
        ("Chap. II – Real numbers", "Real numbers"),
        ("Ch. 4: Powers", "Powers"),
        ("Lesson 2 – Fractions", "Fractions"),
        ("Unit 4) Forces", "Forces"),
        ("Module IV: Waves", "Waves"),
        ("Section 5 – Vectors", "Vectors"),
        ("Part 2 : Statistics", "Statistics"),
        ("4) Probability", "Probability"),
        ("Sequences", "Sequences"),
        ("Unit vectors", "Unit vectors"),
        ("Chi-squared test", "Chi-squared test"),
        ("Chi square", "Chi square"),
        ("X-ray imaging", "X-ray imaging"),
        ("V-shaped graphs", "V-shaped graphs"),
        ("IV. Waves", "Waves"),
        ("Chapter I Intro", "Intro"),
        ("1000 ways to count", "1000 ways to count"),
        ("Chapter 7", "Chapter 7"),
    ],
)
def test_the_english_numbering_words_are_dropped(heading: str, expected: str) -> None:
    assert chapter_title(heading, "en") == expected


def test_each_language_drops_its_own_numbering_only() -> None:
    assert chapter_title("Chapitre 3 : les suites") == "Les suites"
    assert chapter_title("Chapitre 3 : les suites", "fr") == "Les suites"
    assert chapter_title("Chapter 3: sequences") == "Chapter 3: sequences"  # French default
    assert chapter_title("Chapitre 3 : les suites", "en") == "Chapitre 3 : les suites"
    assert chapter_title("Lesson 2 – Fractions", "fr") == "Lesson 2 – Fractions"


# --- packs against the template of their language -----------------------------------


def test_the_english_pack_follows_the_english_template() -> None:
    index, issues = index_pack(ENGLISH_PACK, EN)
    assert issues == [] and index is not None and index.title
    assert index.sections >= {"§1", "§7", "§4.1"} and index.exercises


def test_the_english_title_is_cleaned_with_english_words() -> None:
    pack = ENGLISH_PACK.replace(ENGLISH_PACK.splitlines()[0], "# Chapter 2: Linear functions", 1)
    index, _ = index_pack(pack, EN)
    assert index is not None and index.title == "Linear functions"
    index_fr, _ = index_pack(pack, EN.__class__(**{**EN.__dict__, "language": "fr"}))
    assert index_fr is not None and index_fr.title == "Chapter 2: Linear functions"


def test_a_french_pack_against_the_english_template_is_a_language_mismatch() -> None:
    index, issues = index_pack(FRENCH_PACK, EN, alternatives=[FR])
    assert index is None
    first = issues[0]
    assert first.code == "pack.wrong_language" and first.where == "document"
    assert dict(first.params) == {"found_language": "fr", "expected_language": "en"}
    assert first.message == "le document suit le modèle en français, mais ce cours est en anglais"
    assert [i.code for i in issues].count("pack.section_missing") == 0  # one clear reason, not seven


def test_an_english_pack_against_the_french_template_is_a_language_mismatch() -> None:
    _, issues = index_pack(ENGLISH_PACK, FR, alternatives=[EN])
    assert issues[0].code == "pack.wrong_language"
    assert issues[0].message == "le document suit le modèle en anglais, mais ce cours est en français"


def test_without_alternatives_a_pack_in_the_wrong_language_reports_its_headings() -> None:
    _, issues = index_pack(FRENCH_PACK, EN)
    assert issues and issues[0].code != "pack.wrong_language"


def test_a_broken_pack_is_not_taken_for_the_other_language() -> None:
    broken = ENGLISH_PACK.replace("## 5. Vocabulary", "## 5. Glossary")
    _, issues = index_pack(broken, EN, alternatives=[FR])
    assert all(i.code != "pack.wrong_language" for i in issues) and issues


def test_validate_content_reads_the_language_from_the_template() -> None:
    data = curriculum("valid_en.yaml").model_dump(mode="json")
    data["title"] = "Chapter 1: Mini chapter"
    content, issues = validate_content(ENGLISH_PACK, {**data, "sections": _sections_of(ENGLISH_PACK)}, EN, 60_000)
    assert issues == [] or all(i.where != "document" for i in issues)
    wrong, mismatch = validate_content(FRENCH_PACK, data, EN, 60_000, [FR])
    assert wrong is None and mismatch[0].code == "pack.wrong_language"


def _sections_of(pack: str) -> list[dict]:
    index, _ = index_pack(pack, EN)
    assert index is not None
    exercise = sorted(index.exercises)[0]
    return [
        {
            "id": "intro",
            "kind": "practise",
            "title": "Exercises",
            "goal": "Apply.",
            "done_when": "Done.",
            "exercises": [exercise],
            "count": 1,
        }
    ]


# --- the curriculum's title ---------------------------------------------------------


def test_a_curriculum_title_loses_the_numbering_of_its_language() -> None:
    data = curriculum("valid_en.yaml").model_dump(mode="json")
    data["title"] = "Lesson 3 – Mini chapter"
    assert curriculum_from_json(data, "en").title == "Mini chapter"
    assert curriculum_from_json(data).title == "Lesson 3 – Mini chapter"
    checked, issues = check_curriculum(data, "en")
    assert issues == [] and checked is not None and checked.title == "Mini chapter"
    french = {**data, "title": "Chapitre 3 : Mini chapitre"}
    assert curriculum_from_json(french).title == "Mini chapitre"
    assert curriculum_from_json(french, "en").title == "Chapitre 3 : Mini chapitre"


def test_parse_curriculum_takes_the_language() -> None:
    text = (Path(__file__).parents[1] / "fixtures" / "curricula" / "valid_en.yaml").read_text(encoding="utf-8")
    text = text.replace("title: Mini chapter", "title: Unit 4) Mini chapter", 1)
    assert parse_curriculum(text, "x.yaml", "en").title == "Mini chapter"
    assert parse_curriculum(text, "x.yaml").title == "Unit 4) Mini chapter"


# --- the reasons the repair prompt reads --------------------------------------------


def test_the_french_reason_is_the_message_byte_for_byte() -> None:
    issue = ContentIssue("§ 4.2", "titre manquant", "pack.title_missing")
    assert issue_text(issue) == issue_text(issue, "fr") == "titre manquant"


def test_a_coded_reason_is_the_catalogs_sentence_in_english() -> None:
    _, issues = index_pack(ENGLISH_PACK.replace("## 5. Vocabulary", "## 5. Glossary"), EN)
    coded = next(i for i in issues if i.code == "pack.section_missing")
    assert issue_text(coded, "en") == render_issue(coded, "en")["message"] != coded.message
    assert issue_text(coded, "fr") == coded.message


def test_an_uncoded_reason_stays_its_message() -> None:
    issue = ContentIssue("pages", "missing marker for page 4")
    assert issue_text(issue, "en") == "missing marker for page 4"


def test_the_wrong_language_reason_names_the_languages_in_the_readers_language() -> None:
    _, issues = index_pack(FRENCH_PACK, EN, alternatives=[FR])
    issue = issues[0]
    assert issue_text(issue, "en") == "the document follows the French template, but this course is in English"
    assert render_issue(issue, "fr")["message"] == issue.message
    assert render_issue(issue, "en")["message"] == issue_text(issue, "en")
