"""Spec 011 R3.6: the English system text is its own cached prefix, pinned like the French one.

`system_text_sha_en.txt` and `system_text_sha_en_discussion.txt` were generated once from the
English prompt set and the English sequences chapter, read by a person, and pinned. Delete a
file and rerun to regenerate it after an intended change to an English prompt, the pack or
the curriculum.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import get_settings
from app.services import curriculum_render, prompt_service
from app.services.prompts import PromptLibrary
from scripts.chapter_files import load_chapter_dir
from tests.conftest import ENGLISH_LESSON_DIR

RENDER = Path(__file__).parents[1] / "fixtures" / "render"


def _rendering(voice: bool, mode: str = "parcours") -> str:
    prompts = PromptLibrary(get_settings().prompts_dir)
    chapter = load_chapter_dir(ENGLISH_LESSON_DIR, "mathematics", prompts, language="en")
    return prompt_service.render_system_text(
        prompts.tutor("en"),
        prompts.subject("mathematics", "en"),
        chapter.pack,
        curriculum_render.overview(chapter.curriculum, mode, "en"),  # type: ignore[arg-type]
        prompts.mode(mode, "en"),  # type: ignore[arg-type]
        prompts.mode_opening(mode, "en"),  # type: ignore[arg-type]
        voice=voice,
    )


def _pinned(name: str, text: str) -> None:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = RENDER / name
    if not path.exists():
        path.write_text(digest + "\n")
    assert digest == path.read_text().strip()


def test_the_english_text_rendering_is_byte_stable() -> None:
    text = _rendering(voice=False)
    _pinned("system_text_sha_en.txt", text)
    assert "## The subject: mathematics" in text and "## Chapter path" in text
    assert "out loud" not in text.lower()


def test_the_english_discussion_rendering_is_byte_stable() -> None:
    text = _rendering(voice=False, mode="discussion")
    _pinned("system_text_sha_en_discussion.txt", text)
    assert "## The discussion" in text
    assert "start_section" not in text and "complete_section" not in text


def test_the_english_voice_rendering_carries_both_voice_blocks() -> None:
    text = _rendering(voice=True)
    assert "When we talk out loud" in text and "Mathematics out loud" in text
    assert "<!-- VOICE -->" not in text and "<!-- /VOICE -->" not in text


def test_the_english_rendering_carries_no_french_prompt_text() -> None:
    for mode in ("parcours", "discussion"):
        text = _rendering(voice=True, mode=mode)
        for french in ("Ta seule source", "Parcours du chapitre", "à voix haute", "Hors sujet"):
            assert french not in text, french


def test_the_two_languages_render_different_prefixes_for_different_files() -> None:
    from tests.unit.test_prompt_service import _real_rendering

    assert _rendering(voice=False) != _real_rendering(voice=False)
    assert _rendering(voice=False, mode="discussion") != _real_rendering(voice=False, mode="discussion")
