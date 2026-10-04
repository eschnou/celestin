import os
import shutil
from pathlib import Path

import pytest

from app.domain.errors import PromptInvalid, PromptUnavailable
from app.services.prompts import PromptLibrary

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    copy = tmp_path / "prompts"
    shutil.copytree(PROMPTS, copy)
    return copy


def test_real_files_load_and_check():
    library = PromptLibrary(PROMPTS)
    library.check()
    assert "<!-- SUBJECT -->" in library.tutor()
    assert library.template("sciences").subject == "sciences"
    assert library.subject("mathematics").startswith("## La matière")
    assert library.authoring_pack() and library.authoring_curriculum()
    assert "--- page N ---" in library.transcribe() and "sure: false" in library.verify()
    assert library.unavailable() == []


def test_missing_subject_prompt_fails_startup_naming_the_file(root: Path):
    (root / "subjects" / "sciences.fr.md").unlink()
    with pytest.raises(PromptInvalid, match="sciences.fr.md"):
        PromptLibrary(root).check()


def test_broken_template_fails_startup(root: Path):
    (root / "templates" / "mathematics.pack.fr.md").write_text("pas de front matter", encoding="utf-8")
    with pytest.raises(PromptInvalid, match="mathematics.pack.fr.md"):
        PromptLibrary(root).check()


def test_unavailable_lists_broken_files_at_runtime(root: Path):
    library = PromptLibrary(root)
    library.check()
    (root / "authoring" / "pack.fr.md").unlink()
    (root / "templates" / "sciences.pack.fr.md").write_text("---\nsubject: nope\n---\n", encoding="utf-8")
    assert library.unavailable() == ["templates/sciences.pack.fr.md", "authoring/pack.fr.md"]
    with pytest.raises(PromptUnavailable):
        library.template("sciences")
    with pytest.raises(PromptUnavailable):
        library.authoring_pack()


def test_unavailable_subjects_are_not_required(root: Path):
    assert not (root / "subjects" / "history.fr.md").exists()
    assert "subjects/history.fr.md" not in PromptLibrary(root).required()


def test_edit_is_picked_up_by_mtime(root: Path):
    library = PromptLibrary(root)
    path = root / "tutor.fr.md"
    before = library.tutor()
    path.write_text(before + "\najout\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    assert library.tutor().endswith("ajout\n")
