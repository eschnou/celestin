"""Spec 011 R3.4: the prompt library reads one file per course language.

These run on a copy of the French tree whose files are also copied to `*.en.md`, so they
pin the library's mechanics (names, caches, requirements, health) and not the prose of the
English files, which `test_prompt_files_en.py` reads.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from app.domain.errors import PromptInvalid, PromptUnavailable
from app.services import prompts
from app.services.prompts import PromptLibrary, file_name

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    copy = tmp_path / "prompts"
    shutil.copytree(PROMPTS, copy, ignore=shutil.ignore_patterns("*.en.md"))
    for french in list(copy.rglob("*.fr.md")):
        shutil.copy(french, french.with_name(french.name.replace(".fr.md", ".en.md")))
    return copy


def test_file_names_carry_the_language() -> None:
    assert file_name("tutor", "fr") == "tutor.fr.md"
    assert file_name("tutor", "en") == "tutor.en.md"
    assert prompts.subject_file("sciences", "en") == "subjects/sciences.en.md"
    assert prompts.template_file("mathematics", "en") == "templates/mathematics.pack.en.md"
    assert prompts.mode_opening_file("discussion", "en") == "modes/discussion.opening.en.md"
    assert prompts.authoring_pack_file("en") == "authoring/pack.en.md"
    assert prompts.verify_file("en") == "transcription/verify.en.md"
    assert prompts.work_file("en") == "transcription/work.en.md"


def test_french_is_the_default_language(root: Path) -> None:
    (root / "tutor.en.md").write_text("english\n", encoding="utf-8")
    library = PromptLibrary(root)
    assert library.tutor() == library.tutor("fr") != library.tutor("en")


def test_each_language_has_its_own_cache(root: Path) -> None:
    (root / "tutor.en.md").write_text("english\n", encoding="utf-8")
    library = PromptLibrary(root)
    french = library.tutor("fr")
    assert library.tutor("en") == "english\n" and library.tutor("fr") == french
    path = root / "tutor.en.md"
    path.write_text("english, edited\n", encoding="utf-8")
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
    assert library.tutor("en") == "english, edited\n" and library.tutor("fr") == french


def test_templates_are_parsed_per_language_and_know_it(root: Path) -> None:
    library = PromptLibrary(root)
    assert library.template("sciences").language == "fr"
    assert library.template("sciences", "fr").language == "fr"
    assert library.template("sciences", "en").language == "en"
    assert library.template("sciences", "en") is library.template("sciences", "en")  # cached


def test_only_the_offered_languages_are_required(root: Path, french_only: None) -> None:
    names = PromptLibrary(root).required()
    assert "tutor.fr.md" in names and "tutor.en.md" not in names
    assert not any(name.endswith(".en.md") for name in names)


def test_an_offered_language_requires_its_whole_set(root: Path) -> None:
    names = PromptLibrary(root).required()
    expected = [
        "tutor.en.md",
        "modes/parcours.en.md",
        "modes/parcours.opening.en.md",
        "modes/discussion.en.md",
        "modes/discussion.opening.en.md",
        "subjects/mathematics.en.md",
        "templates/mathematics.pack.en.md",
        "subjects/sciences.en.md",
        "templates/sciences.pack.en.md",
        "subjects/languages.en.md",
        "templates/languages.pack.en.md",
        "subjects/general.en.md",
        "templates/general.pack.en.md",
        "authoring/pack.en.md",
        "authoring/curriculum.en.md",
        "transcription/transcribe.en.md",
        "transcription/verify.en.md",
        "transcription/work.en.md",
    ]
    assert set(expected) <= set(names)
    assert len(names) == 3 * len(expected)  # the French and Dutch sets are the same size
    assert len(names) == len(set(names))
    PromptLibrary(root).check()


def test_a_missing_english_file_stops_startup_naming_it_once_english_is_offered(
    root: Path
) -> None:
    (root / "subjects" / "sciences.en.md").unlink()
    with pytest.raises(PromptInvalid, match="sciences.en.md"):
        PromptLibrary(root).check()


def test_a_missing_english_file_is_nothing_while_english_is_not_offered(root: Path, french_only: None) -> None:
    (root / "subjects" / "sciences.en.md").unlink()
    PromptLibrary(root).check()
    assert PromptLibrary(root).unavailable() == []


def test_health_lists_the_broken_english_files_with_their_language(root: Path) -> None:
    library = PromptLibrary(root)
    library.check()
    (root / "authoring" / "pack.en.md").unlink()
    (root / "templates" / "sciences.pack.en.md").write_text("---\nsubject: nope\n---\n", encoding="utf-8")
    assert library.unavailable() == ["templates/sciences.pack.en.md", "authoring/pack.en.md"]
    with pytest.raises(PromptUnavailable):
        library.template("sciences", "en")
    with pytest.raises(PromptUnavailable):
        library.authoring_pack("en")
    library.authoring_pack("fr")  # the French set is untouched


def test_the_other_languages_templates(root: Path) -> None:
    library = PromptLibrary(root)
    assert [t.language for t in library.other_templates("sciences", "fr")] == ["en", "nl"]
    assert [t.language for t in library.other_templates("sciences", "en")] == ["fr", "nl"]


def test_no_other_template_while_a_subject_has_one_language(root: Path, french_only: None) -> None:
    assert PromptLibrary(root).other_templates("sciences", "fr") == []
