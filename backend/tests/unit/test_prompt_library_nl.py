"""Spec 017 R3.4: the prompt library reads the Dutch files like the others, and requires them once Dutch is offered.

The mechanics are pinned for French and English in `test_prompt_library_languages.py`; these cover the third language on
a copy of the real tree (the Dutch files are the real ones as far as they are written)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.domain.errors import PromptInvalid, PromptUnavailable
from app.services import prompts
from app.services.prompts import PromptLibrary, file_name

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
AUTHORING_SET = [
    "subjects/mathematics.nl.md", "templates/mathematics.pack.nl.md", "subjects/sciences.nl.md",
    "templates/sciences.pack.nl.md", "subjects/languages.nl.md", "templates/languages.pack.nl.md",
    "subjects/general.nl.md", "templates/general.pack.nl.md", "authoring/pack.nl.md", "authoring/curriculum.nl.md",
    "transcription/transcribe.nl.md", "transcription/verify.nl.md", "transcription/work.nl.md",
]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    copy = tmp_path / "prompts"
    shutil.copytree(PROMPTS, copy)
    return copy


def test_file_names_carry_the_dutch_language() -> None:
    assert file_name("tutor", "nl") == "tutor.nl.md"
    assert prompts.subject_file("sciences", "nl") == "subjects/sciences.nl.md"
    assert prompts.template_file("mathematics", "nl") == "templates/mathematics.pack.nl.md"
    assert prompts.authoring_curriculum_file("nl") == "authoring/curriculum.nl.md"
    assert prompts.work_file("nl") == "transcription/work.nl.md"


def test_the_authoring_files_exist_and_are_dutch() -> None:
    library = PromptLibrary(PROMPTS)
    for name in AUTHORING_SET:
        assert (PROMPTS / name).is_file(), name
    assert "traject" in library.authoring_curriculum("nl") and "hoofdstuk" in library.authoring_pack("nl")
    assert library.transcribe("nl") != library.transcribe("en") != library.transcribe("fr")
    assert library.subject("mathematics", "nl").startswith("## Het vak: wiskunde")


def test_templates_are_parsed_for_dutch_and_know_it() -> None:
    library = PromptLibrary(PROMPTS)
    for subject in ("mathematics", "sciences", "languages", "general"):
        template = library.template(subject, "nl")  # type: ignore[arg-type]
        assert template.language == "nl" and template.exercises_section == 6
        assert template is library.template(subject, "nl")  # type: ignore[arg-type]
    assert library.template("mathematics", "nl").headings[-1] == (7, "Na te kijken punten")


def test_dutch_is_one_of_the_other_languages_templates() -> None:
    library = PromptLibrary(PROMPTS)
    assert [t.language for t in library.other_templates("sciences", "fr")] == ["en", "nl"]
    assert [t.language for t in library.other_templates("sciences", "nl")] == ["fr", "en"]


def test_a_missing_dutch_file_is_nothing_for_a_subject_that_does_not_offer_dutch(root: Path, french_only: None) -> None:
    (root / "subjects" / "sciences.nl.md").unlink()
    PromptLibrary(root).check()
    assert not any(name.endswith(".nl.md") for name in PromptLibrary(root).required())


def test_an_offered_dutch_requires_its_files_and_names_the_missing_one(root: Path) -> None:
    required = PromptLibrary(root).required()
    assert set(AUTHORING_SET) <= set(required)
    (root / "subjects" / "sciences.nl.md").unlink()
    with pytest.raises(PromptInvalid, match=r"\.nl\.md"):  # the first Dutch file missing, by name
        PromptLibrary(root).check()


def test_health_lists_a_broken_dutch_file_with_its_language(root: Path) -> None:
    # The tutor and mode files are written in the next phase: this asserts only on what is broken here.
    library = PromptLibrary(root)
    (root / "authoring" / "pack.nl.md").unlink()
    (root / "templates" / "sciences.pack.nl.md").write_text("---\nsubject: nope\n---\n", encoding="utf-8")
    broken = library.unavailable()
    assert "templates/sciences.pack.nl.md" in broken and "authoring/pack.nl.md" in broken
    with pytest.raises(PromptUnavailable):
        library.authoring_pack("nl")
    library.authoring_pack("fr")  # the other sets are untouched
