"""Spec 017 R3.6: the Dutch system text is its own cached prefix, pinned like the French and the English ones.

`system_text_sha_nl.txt` and `system_text_sha_nl_discussion.txt` were generated once from the Dutch prompt set and the
Dutch sequences chapter, read by a person, and pinned. Delete a file and rerun to regenerate it after an intended change
to a Dutch prompt, the pack or the curriculum.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import get_settings
from app.services import curriculum_render, prompt_service
from app.services.prompts import PromptLibrary
from scripts.chapter_files import load_chapter_dir
from tests.conftest import DUTCH_LESSON_DIR

RENDER = Path(__file__).parents[1] / "fixtures" / "render"


def _rendering(voice: bool, mode: str = "parcours") -> str:
    prompts = PromptLibrary(get_settings().prompts_dir)
    chapter = load_chapter_dir(DUTCH_LESSON_DIR, "mathematics", prompts, language="nl")
    return prompt_service.render_system_text(
        prompts.tutor("nl"),
        prompts.subject("mathematics", "nl"),
        chapter.pack,
        curriculum_render.overview(chapter.curriculum, mode, "nl"),  # type: ignore[arg-type]
        prompts.mode(mode, "nl"),  # type: ignore[arg-type]
        prompts.mode_opening(mode, "nl"),  # type: ignore[arg-type]
        voice=voice,
    )


def _pinned(name: str, text: str) -> None:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = RENDER / name
    if not path.exists():
        path.write_text(digest + "\n")
    assert digest == path.read_text().strip()


def test_the_dutch_text_rendering_is_byte_stable() -> None:
    text = _rendering(voice=False)
    _pinned("system_text_sha_nl.txt", text)
    assert "## Het vak: wiskunde" in text and "## Traject van het hoofdstuk" in text
    assert "hardop" not in text.lower()


def test_the_dutch_discussion_rendering_is_byte_stable() -> None:
    text = _rendering(voice=False, mode="discussion")
    _pinned("system_text_sha_nl_discussion.txt", text)
    assert "## De bespreking" in text
    assert "start_section" not in text.replace("`start_section(id)`", "") or "geen sectie openen" in text
    assert "complete_section(id" not in text.split("## De bespreking")[0].split("Traject van het hoofdstuk")[0]


def test_the_dutch_voice_rendering_carries_both_voice_blocks() -> None:
    text = _rendering(voice=True)
    assert "Wanneer we hardop praten" in text and "Wiskunde hardop" in text
    assert "<!-- VOICE -->" not in text and "<!-- /VOICE -->" not in text


def test_the_dutch_rendering_carries_no_french_or_english_prompt_text() -> None:
    for mode in ("parcours", "discussion"):
        text = _rendering(voice=True, mode=mode)
        for other in (
            "Ta seule source", "Parcours du chapitre", "à voix haute", "Hors sujet",
            "Your only source", "Chapter path", "out loud", "Off-topic",
        ):
            assert other not in text, other


def test_the_three_languages_render_three_prefixes() -> None:
    from tests.unit.test_prompt_service import _real_rendering
    from tests.unit.test_prompt_service_en import _rendering as english

    renderings = {_real_rendering(voice=False), english(voice=False), _rendering(voice=False)}
    assert len(renderings) == 3
