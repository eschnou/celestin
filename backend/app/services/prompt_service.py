"""Prompt assembly.

Pure given its inputs (NFR 4.1.4), so it is directly unit-testable.

Order is load-bearing for cost (design 7): the developer message carrying the
tutor prompt, the subject prompt, the pack and the curriculum overview comes first
and ends with an explicit cache breakpoint, so everything that varies per request
sits behind it (005 design 3.4).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.domain.curriculum import Curriculum
from app.domain.errors import PromptUnavailable
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.mode import DEFAULT_MODE, Mode
from app.domain.progress import Progress
from app.services import curriculum_render

SUBJECT_MARKER = "<!-- SUBJECT -->"
PACK_MARKER = "<!-- COURSE_PACK -->"
CURRICULUM_MARKER = "<!-- CURRICULUM -->"
MODE_MARKER = "<!-- MODE -->"
MODE_OPENING_MARKER = "<!-- MODE_OPENING -->"
_REQUIRED = (SUBJECT_MARKER, PACK_MARKER, CURRICULUM_MARKER, MODE_MARKER, MODE_OPENING_MARKER)
_MARKERS = re.compile("|".join(re.escape(m) for m in _REQUIRED))
VOICE_START = "<!-- VOICE -->\n"
VOICE_END = "<!-- /VOICE -->\n"


def _voice_block(prompt_text: str, voice: bool) -> str:
    """Keep the block without its markers for a voice session; drop the block, its
    markers and the blank line after it for text, so the text prefix is byte-stable
    (003 design 3.5)."""
    start = prompt_text.find(VOICE_START)
    if start < 0:
        return prompt_text
    end = prompt_text.find(VOICE_END, start)
    if end < 0:
        raise PromptUnavailable()
    body = prompt_text[start + len(VOICE_START) : end]
    after = end + len(VOICE_END)
    if voice:
        return prompt_text[:start] + body + prompt_text[after:]
    if prompt_text.startswith("\n", after):
        after += 1
    return prompt_text[:start] + prompt_text[after:]


def render_system_text(
    tutor_text: str,
    subject_text: str,
    pack_text: str,
    overview_text: str,
    mode_text: str,
    opening_text: str,
    *,
    voice: bool = False,
) -> str:
    """The tutor prompt with the subject prompt, the pack, the overview and the mode's
    two layers in place. Each prompt file keeps or drops its own voice block."""
    if any(marker not in tutor_text for marker in _REQUIRED):
        raise PromptUnavailable()
    text = _voice_block(tutor_text, voice)
    values = {
        SUBJECT_MARKER: _voice_block(subject_text, voice).rstrip("\n"),
        PACK_MARKER: pack_text,
        CURRICULUM_MARKER: overview_text,
        MODE_MARKER: _voice_block(mode_text, voice).rstrip("\n"),
        MODE_OPENING_MARKER: _voice_block(opening_text, voice).rstrip("\n"),
    }
    # One pass over the tutor prompt only: a marker written inside the pack (student
    # material), the subject prompt or a mode file is left as text, never substituted.
    return _MARKERS.sub(lambda match: values[match.group(0)], text)


def build(
    tutor_text: str,
    subject_text: str,
    pack_text: str,
    curriculum: Curriculum,
    progress: Progress,
    history_items: list[dict[str, Any]],
    mode_text: str,
    opening_text: str,
    mode: Mode = DEFAULT_MODE,
    now: datetime | None = None,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> list[dict[str, Any]]:
    """Developer message first, then the mapped transcript, then the state of the
    path and the time (002 design 3.7). Both change every turn, so they go last."""
    developer: dict[str, Any] = {
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": render_system_text(
                    tutor_text,
                    subject_text,
                    pack_text,
                    curriculum_render.overview(curriculum, mode, language),
                    mode_text,
                    opening_text,
                ),
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }
    state: dict[str, Any] = {
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": curriculum_render.state_message(curriculum, progress, now, mode, language),
            }
        ],
    }
    return [developer, *history_items, state]
