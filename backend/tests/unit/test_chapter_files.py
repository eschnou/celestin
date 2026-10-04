import shutil
from pathlib import Path

import pytest

from app.services.prompts import PromptLibrary
from scripts.chapter_files import DEFAULT_CHAPTER_DIR, ChapterFilesInvalid, load_chapter_dir

PROMPTS = PromptLibrary(Path(__file__).resolve().parents[2] / "prompts")


def test_chapter_one_loads_as_a_lesson_chapter():
    chapter = load_chapter_dir(DEFAULT_CHAPTER_DIR, "mathematics", PROMPTS)
    assert chapter.subject == "mathematics"
    assert chapter.title == "Les suites numériques"
    assert chapter.curriculum.id == "suites"
    assert len(chapter.curriculum.sections) > 5


def test_chapter_id_override():
    chapter = load_chapter_dir(DEFAULT_CHAPTER_DIR, "mathematics", PROMPTS, chapter_id="a" * 32)
    assert chapter.id == chapter.curriculum.id == "a" * 32


def test_broken_pack_is_refused_naming_the_issue(tmp_path: Path):
    copy = tmp_path / "ch"
    shutil.copytree(DEFAULT_CHAPTER_DIR, copy)
    pack = copy / "pack.md"
    pack.write_text(pack.read_text(encoding="utf-8").replace("## 5. Vocabulaire", "## 5. Lexique"), encoding="utf-8")
    with pytest.raises(ChapterFilesInvalid, match="§ 5"):
        load_chapter_dir(copy, "mathematics", PROMPTS)


def test_dangling_reference_is_refused(tmp_path: Path):
    copy = tmp_path / "ch"
    shutil.copytree(DEFAULT_CHAPTER_DIR, copy)
    cur = copy / "curriculum.yaml"
    cur.write_text(cur.read_text(encoding="utf-8").replace('"6.1.4"', '"6.1.99"'), encoding="utf-8")
    with pytest.raises(ChapterFilesInvalid, match="6.1.99"):
        load_chapter_dir(copy, "mathematics", PROMPTS)


def test_wrong_subject_template_is_refused():
    with pytest.raises(ChapterFilesInvalid):
        load_chapter_dir(DEFAULT_CHAPTER_DIR, "sciences", PROMPTS)


STATISTIQUE = Path(__file__).resolve().parents[1] / "fixtures" / "chapters" / "statistique"


def test_the_statistics_fixture_chapter_validates():
    """The chapter the chart probes run on (008 task 2.5): pack and curriculum pass
    the same validation as the editors, every reference resolving."""
    chapter = load_chapter_dir(STATISTIQUE, "mathematics", PROMPTS)
    assert chapter.title == "Statistique descriptive à une variable"
    assert [s.id for s in chapter.curriculum.sections] == ["vocabulaire", "graphiques", "parametres", "pratique"]
    assert "Représentations graphiques" in chapter.pack


FIXTURE_CHAPTERS = STATISTIQUE.parent


def test_the_statistics_fixture_draws_its_nested_sets():
    """The figure probes' nesting case asks for population ⊃ échantillon: the course
    draws it, so drawing it is not outside the pack."""
    chapter = load_chapter_dir(STATISTIQUE, "mathematics", PROMPTS)
    assert "diagramme d'ensembles emboîtés" in chapter.pack


def test_the_mru_fixture_chapter_validates():
    """The physics chapter the plot probes' lab experiment runs on, hand-written from
    tests/fixtures/material/physics_mru.txt; the material's wrong answer (720 km) is
    kept and signalled in « Points à vérifier », and left out of the path."""
    chapter = load_chapter_dir(FIXTURE_CHAPTERS / "mru", "sciences", PROMPTS)
    assert chapter.subject == "sciences"
    assert chapter.title == "Le mouvement rectiligne uniforme (MRU)"
    assert [s.id for s in chapter.curriculum.sections] == ["mouvement", "mru", "pratique"]
    assert chapter.curriculum.sections[-1].exercises == ["6.1.1", "6.2.1", "6.2.2"]
    assert "| $x$ (cm) | 0 | 12 | 24 | 36 | 48 |" in chapter.pack
    with pytest.raises(ChapterFilesInvalid):
        load_chapter_dir(FIXTURE_CHAPTERS / "mru", "mathematics", PROMPTS)


def test_the_analytic_geometry_fixture_chapter_validates():
    """The chapter of the figure probes' intersection and course triangle."""
    chapter = load_chapter_dir(FIXTURE_CHAPTERS / "geometrie_analytique", "mathematics", PROMPTS)
    assert chapter.title == "Géométrie analytique plane"
    assert [s.id for s in chapter.curriculum.sections] == ["repere", "droites", "pratique"]
    assert "Figures : dans un repère orthonormé" in chapter.pack


def test_the_inequations_fixture_chapter_validates():
    """The chapter of the figure probes' number lines and overlapping sets."""
    chapter = load_chapter_dir(FIXTURE_CHAPTERS / "inequations", "mathematics", PROMPTS)
    assert chapter.title == "Intervalles et inéquations du premier degré"
    assert [s.id for s in chapter.curriculum.sections] == ["intervalles", "ensembles", "inequations", "pratique"]
    assert "« droite graduée »" in chapter.pack and "« diagramme d'ensembles »" in chapter.pack
