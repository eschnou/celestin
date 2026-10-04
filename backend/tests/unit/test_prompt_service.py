from __future__ import annotations

import pytest

from app.config import get_settings
from app.domain.errors import PromptUnavailable
from app.domain.progress import Progress
from app.services import prompt_service
from tests.fixtures.curricula import curriculum

CUR = curriculum()
PROMPT = (
    "p <!-- SUBJECT --> s <!-- COURSE_PACK --> q <!-- CURRICULUM --> r"
    " <!-- MODE --> t <!-- MODE_OPENING --> u"
)
SUBJECT = "SUBJ\n"
MODE = "MODE\n"
OPENING = "OPENING\n"


def test_markers_substituted_in_layer_order() -> None:
    out = prompt_service.render_system_text(PROMPT, SUBJECT, "PACK", "OVERVIEW", MODE, OPENING)
    assert out == "p SUBJ s PACK q OVERVIEW r MODE t OPENING u"


@pytest.mark.parametrize(
    "prompt",
    [
        "no marker here",
        "<!-- COURSE_PACK --> <!-- CURRICULUM --> <!-- MODE --> <!-- MODE_OPENING -->",
        "<!-- SUBJECT --> <!-- CURRICULUM --> <!-- MODE --> <!-- MODE_OPENING -->",
        "<!-- SUBJECT --> <!-- COURSE_PACK --> <!-- MODE --> <!-- MODE_OPENING -->",
        "<!-- SUBJECT --> <!-- COURSE_PACK --> <!-- CURRICULUM --> <!-- MODE_OPENING -->",
        "<!-- SUBJECT --> <!-- COURSE_PACK --> <!-- CURRICULUM --> <!-- MODE -->",
    ],
)
def test_missing_marker_raises(prompt: str) -> None:
    with pytest.raises(PromptUnavailable):
        prompt_service.render_system_text(prompt, SUBJECT, "PACK", "OVERVIEW", MODE, OPENING)


def test_real_prompt_file_carries_every_marker() -> None:
    text = (get_settings().prompts_dir / "tutor.fr.md").read_text(encoding="utf-8")
    assert prompt_service.SUBJECT_MARKER in text
    assert prompt_service.PACK_MARKER in text
    assert prompt_service.CURRICULUM_MARKER in text
    assert prompt_service.MODE_MARKER in text
    assert prompt_service.MODE_OPENING_MARKER in text


def test_developer_message_is_first_and_carries_breakpoint() -> None:
    items = prompt_service.build(
        PROMPT, SUBJECT, "PACK", CUR, Progress(), [{"role": "user", "content": "hi"}], MODE, OPENING
    )
    assert items[0]["role"] == "developer"
    block = items[0]["content"][0]
    assert block["type"] == "input_text"
    assert block["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert "PACK" in block["text"]
    assert "Parcours du chapitre" in block["text"]
    assert "`intro`" in block["text"]


def test_history_follows_the_breakpoint_and_state_is_last() -> None:
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "salut"}]
    items = prompt_service.build(
        PROMPT, SUBJECT, "PACK", CUR, Progress(active="intro"), history, MODE, OPENING
    )
    assert items[1:3] == history
    state = items[-1]
    assert state["role"] == "developer"
    assert "prompt_cache_breakpoint" not in state["content"][0]
    assert "Section en cours" in state["content"][0]["text"]
    assert "intro" in state["content"][0]["text"]


def test_prefix_is_byte_identical_across_progress_history_and_time() -> None:
    from datetime import datetime

    a = prompt_service.build(
        PROMPT,
        SUBJECT,
        "PACK",
        CUR,
        Progress(),
        [{"role": "user", "content": "1"}],
        MODE,
        OPENING,
        now=datetime(2026, 9, 11, 10, 5),
    )
    b = prompt_service.build(
        PROMPT,
        SUBJECT,
        "PACK",
        CUR,
        Progress(done=frozenset({"intro"}), active="exos"),
        [{"role": "user", "content": "2"}],
        MODE,
        OPENING,
        now=datetime(2026, 9, 12, 19, 0),
    )
    assert a[0] == b[0]
    assert a[-1] != b[-1]
    assert "le matin" in a[-1]["content"][0]["text"]
    assert "le soir" in b[-1]["content"][0]["text"]


VOICE_PROMPT = (
    "a\n<!-- VOICE -->\nvoix\n<!-- /VOICE -->\n\n"
    "b <!-- SUBJECT --> <!-- COURSE_PACK --> <!-- CURRICULUM --> <!-- MODE --> <!-- MODE_OPENING -->"
)
VOICE_SUBJECT = "matière\n<!-- VOICE -->\nà l'oral\n<!-- /VOICE -->\n"


def test_voice_blocks_dropped_for_text() -> None:
    out = prompt_service.render_system_text(VOICE_PROMPT, VOICE_SUBJECT, "P", "O", MODE, OPENING)
    assert out == "a\nb matière P O MODE OPENING"


def test_voice_blocks_of_both_files_kept_for_voice_without_markers() -> None:
    out = prompt_service.render_system_text(
        VOICE_PROMPT, VOICE_SUBJECT, "P", "O", MODE, OPENING, voice=True
    )
    assert out == "a\nvoix\n\nb matière\nà l'oral P O MODE OPENING"


def test_a_modes_own_voice_block_is_kept_or_dropped_like_the_others() -> None:
    mode = "socle\n<!-- VOICE -->\nà l'oral ici\n<!-- /VOICE -->\n"
    assert prompt_service.render_system_text(PROMPT, SUBJECT, "P", "O", mode, OPENING).endswith(
        "socle t OPENING u"
    )
    spoken = prompt_service.render_system_text(
        PROMPT, SUBJECT, "P", "O", mode, OPENING, voice=True
    )
    assert "à l'oral ici" in spoken and "<!-- VOICE -->" not in spoken


def test_unclosed_voice_block_raises() -> None:
    with pytest.raises(PromptUnavailable):
        prompt_service.render_system_text(
            "<!-- VOICE -->\nx <!-- SUBJECT --> <!-- COURSE_PACK --> <!-- CURRICULUM -->"
            " <!-- MODE --> <!-- MODE_OPENING -->",
            "",
            "P",
            "O",
            MODE,
            OPENING,
        )
    with pytest.raises(PromptUnavailable):
        prompt_service.render_system_text(
            PROMPT, "<!-- VOICE -->\nnever closed", "P", "O", MODE, OPENING
        )


def test_prompt_without_voice_block_renders_unchanged() -> None:
    out = prompt_service.render_system_text(
        PROMPT, SUBJECT, "PACK", "OVERVIEW", MODE, OPENING, voice=True
    )
    assert out == "p SUBJ s PACK q OVERVIEW r MODE t OPENING u"


def _real_rendering(voice: bool, mode: str = "parcours") -> str:
    from app.services import curriculum_render
    from app.services.prompts import PromptLibrary
    from scripts.chapter_files import DEFAULT_CHAPTER_DIR, load_chapter_dir

    prompts = PromptLibrary(get_settings().prompts_dir)
    chapter = load_chapter_dir(DEFAULT_CHAPTER_DIR, "mathematics", prompts)
    return prompt_service.render_system_text(
        prompts.tutor(),
        prompts.subject("mathematics"),
        chapter.pack,
        curriculum_render.overview(chapter.curriculum, mode),  # type: ignore[arg-type]
        prompts.mode(mode),  # type: ignore[arg-type]
        prompts.mode_opening(mode),  # type: ignore[arg-type]
        voice=voice,
    )


def test_text_rendering_is_byte_stable() -> None:
    """The text-mode cached prefix for chapter 1 must not move by accident: voice
    blocks never reach it. Regenerate the fixture only for an intended change to a
    prompt, the pack or the curriculum."""
    import hashlib
    from pathlib import Path

    expected = (Path(__file__).parents[1] / "fixtures" / "render" / "system_text_sha.txt").read_text().strip()
    text = _real_rendering(voice=False)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == expected
    assert "à voix haute" not in text.lower()
    assert "## La matière : mathématiques" in text


def test_voice_rendering_carries_both_voice_blocks() -> None:
    text = _real_rendering(voice=True)
    assert "Quand on se parle à voix haute" in text
    assert "Les mathématiques à voix haute" in text
    assert "<!-- VOICE -->" not in text and "<!-- /VOICE -->" not in text


def test_a_marker_inside_the_pack_is_left_as_text() -> None:
    pack = "Mon cours <!-- CURRICULUM --> et <!-- MODE --> collés par l'élève"
    out = prompt_service.render_system_text(PROMPT, SUBJECT, pack, "OVERVIEW", MODE, OPENING)
    assert out == f"p SUBJ s {pack} q OVERVIEW r MODE t OPENING u"
    assert out.count("OVERVIEW") == 1
    # The pack's own `<!-- MODE -->` survives as literal text, unsubstituted.
    assert out.count("<!-- MODE -->") == 1


def test_discussion_rendering_is_byte_stable() -> None:
    """The discussion prefix is a second cached prefix per chapter (007 §1.1)."""
    import hashlib
    from pathlib import Path

    fixture = Path(__file__).parents[1] / "fixtures" / "render" / "system_text_sha_discussion.txt"
    text = _real_rendering(voice=False, mode="discussion")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == fixture.read_text().strip()
    assert "## La discussion" in text
    assert "start_section" not in text
    assert "complete_section" not in text
