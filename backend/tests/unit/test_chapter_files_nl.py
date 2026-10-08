"""Spec 017 task 8.1: the Dutch fixture chapters the drawing probes run on. Each passes the validation the editors
apply (the Dutch template, every reference resolving) and holds the facts the probes rely on."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.prompts import PromptLibrary
from scripts.chapter_files import load_chapter_dir

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CHAPTERS = FIXTURES / "chapters"
PROMPTS = PromptLibrary(Path(__file__).resolve().parents[2] / "prompts")

DUTCH_CHAPTERS = [
    ("rijen_nl", "mathematics", "Rekenkundige en meetkundige rijen"),
    ("statistiek_nl", "mathematics", "Beschrijvende statistiek met één veranderlijke"),
    ("analytische_meetkunde_nl", "mathematics", "Analytische meetkunde in het vlak"),
    ("ongelijkheden_nl", "mathematics", "Intervallen en eerstegraadsongelijkheden"),
    ("eenparige_beweging_nl", "sciences", "Eenparige rechtlijnige beweging"),
]


def pack(name: str) -> str:
    return (CHAPTERS / name / "pack.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("directory", "subject", "title"), DUTCH_CHAPTERS)
def test_each_dutch_chapter_validates_against_its_dutch_template(directory: str, subject: str, title: str) -> None:
    chapter = load_chapter_dir(CHAPTERS / directory, subject, PROMPTS, language="nl")  # type: ignore[arg-type]
    assert chapter.language == "nl" and chapter.title == title
    assert chapter.curriculum.sections[-1].kind in ("practise", "synthesis")


@pytest.mark.parametrize(("directory", "subject", "title"), DUTCH_CHAPTERS)
def test_a_dutch_chapter_is_not_valid_in_another_language(directory: str, subject: str, title: str) -> None:
    from scripts.chapter_files import ChapterFilesInvalid

    for language in ("fr", "en"):
        with pytest.raises(ChapterFilesInvalid):
            load_chapter_dir(CHAPTERS / directory, subject, PROMPTS, language=language)  # type: ignore[arg-type]


@pytest.mark.parametrize("directory", [d for d, _, _ in DUTCH_CHAPTERS])
def test_the_dutch_fixtures_use_the_belgian_notation_and_no_decimal_point(directory: str) -> None:
    import re

    text = re.sub(r"^#.*$|§\s*\d+(?:\.\d+)*", "", pack(directory), flags=re.MULTILINE)  # headings and references
    assert not re.search(r"(?<![\w.])\d+\.\d+(?![\w.])", text), "a decimal point in a Dutch pack"
    assert "Geen." in text or "Niets in de cursus" in text


def test_the_statistics_chapter_draws_its_nested_sets_and_every_chart() -> None:
    text = pack("statistiek_nl").casefold()
    for name in ("cirkeldiagram", "staafdiagram", "histogram", "cumulatieve frequentiepolygoon", "boxplot"):
        assert name in text
    assert "verzamelingendiagram met ingesloten verzamelingen" in text and "steekproef" in text


def test_the_geometry_chapter_marks_points_with_a_cross_and_has_its_right_angle_at_b() -> None:
    text = pack("analytische_meetkunde_nl")
    assert "kruisje" in text and "orthonormaal assenstelsel" in text
    assert "rechte hoek in $B$" in text and "$B(3 ; 4)$" in text


def test_the_inequalities_chapter_draws_its_bounds_as_brackets() -> None:
    text = pack("ongelijkheden_nl")
    assert "getallenas" in text and "verzamelingendiagram" in text
    assert "haakje" in text and "bolletje" not in text and "Hoofdstuk" not in text.splitlines()[0]
    assert "]-\\infty ; 4[" in text or "]−∞ ; 4[" in text


def test_the_motion_chapter_keeps_its_wrong_answer_and_leaves_it_out_of_the_path() -> None:
    chapter = load_chapter_dir(CHAPTERS / "eenparige_beweging_nl", "sciences", PROMPTS, language="nl")
    assert [s.id for s in chapter.curriculum.sections] == ["beweging", "eenparig", "oefenen"]
    assert chapter.curriculum.sections[-1].exercises == ["6.1.1", "6.2.1", "6.2.2"]
    assert "| $x$ (m) | 1,0 | 2,5 | 4,0 | 5,5 | 7,0 |" in chapter.pack
    assert "360 km (het antwoord van de verbetersleutel; zie § 7)" in chapter.pack


@pytest.mark.parametrize("name", ["maths_statistiek_nl.txt", "fysica_eenparige_beweging_nl.txt"])
def test_the_dutch_materials_are_dutch_and_carry_the_figures_the_chapters_describe(name: str) -> None:
    text = (FIXTURES / "material" / name).read_text(encoding="utf-8")
    assert "[figuur:" in text or "grafiek" in text
    assert "chapitre" not in text.lower() and "chapter" not in text.lower()
