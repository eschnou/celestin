"""Courses and chapters as the services see them (005 design 3.3, 4.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app.domain.curriculum import Curriculum
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.subject import Subject


AuthoringState = Literal["idle", "generating", "failed"]
Stage = Literal["transcription", "pack", "curriculum"]
# The two stages whose output is one long generation the student waits for (spec 016). A transcription is many short
# calls in parallel: its progress is the page count.
COUNTED_STAGES: tuple[Stage, ...] = ("pack", "curriculum")
SourceKind = Literal["text", "document"]


@dataclass(frozen=True)
class LessonChapter:
    """Everything a turn or a voice session needs from a chapter: its content, the
    subject whose prompt frames it, and the content version progress is saved against."""

    id: str
    subject: Subject
    title: str
    pack: str
    curriculum: Curriculum
    version: int = 0
    # The course's language: the model path takes it beside the subject (spec 011).
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE


@dataclass(frozen=True)
class CourseRecord:
    id: str
    user_id: str
    name: str
    subject: Subject
    created_at: datetime
    updated_at: datetime
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE


@dataclass(frozen=True)
class ChapterRecord:
    """A chapter row. The heavy columns (`source_text`, `pack`, `curriculum`) are
    loaded only when asked for; lists and pages never need them."""

    id: str
    course_id: str
    position: int
    title: str | None
    section_count: int
    content_version: int
    authoring_state: AuthoringState
    authoring_error: str | None
    created_at: datetime
    updated_at: datetime
    content_updated_at: datetime | None
    source_kind: SourceKind = "text"
    authoring_stage: Stage | None = None
    pages_done: int = 0
    page_count: int = 0
    authoring_received_chars: int = 0
    authoring_progress_at: datetime | None = None
    source_text: str | None = None
    pack: str | None = None
    curriculum: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return self.content_version > 0

    @property
    def live_received_chars(self) -> int:
        """Characters of the pack or path received so far; 0 outside those two stages of a running preparation
        (spec 016)."""
        running = self.authoring_state == "generating" and self.authoring_stage in COUNTED_STAGES
        return self.authoring_received_chars if running else 0

    def quiet_seconds(self, now: datetime) -> int | None:
        """Seconds since the running preparation last moved; None when it is not running or has not reported."""
        if self.authoring_state != "generating" or self.authoring_progress_at is None:
            return None
        return max(0, int((now - self.authoring_progress_at).total_seconds()))

    @property
    def needs_document(self) -> bool:
        """Failed before its transcription was stored: the document is not kept, so
        only a new upload can go on (006 R3.4)."""
        return self.authoring_state == "failed" and self.authoring_stage == "transcription"


@dataclass(frozen=True)
class OwnedChapter:
    course: CourseRecord
    chapter: ChapterRecord


@dataclass(frozen=True)
class CourseWithChapters:
    course: CourseRecord
    chapters: list[ChapterRecord]


@dataclass
class RunUsage:
    """What one authoring run cost, accumulated across stages and attempts."""

    attempts_transcription: int = 0
    attempts_pack: int = 0
    attempts_curriculum: int = 0
    transcription_ms: int = 0
    pack_ms: int = 0
    curriculum_ms: int = 0
    # The transcription stage's share of the tokens above, priced with its own model.
    transcription_input_tokens: int = 0
    transcription_cached_tokens: int = 0
    transcription_output_tokens: int = 0
    transcription_cost_usd: float = 0.0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_estimate_usd: float = 0.0

    def add_tokens(self, usage: dict[str, Any]) -> None:
        counts = token_counts(usage)
        self.input_tokens += counts["input_tokens"]
        self.cached_tokens += counts["cached_tokens"]
        self.output_tokens += counts["output_tokens"]
        self.reasoning_tokens += counts["reasoning_tokens"]

    def add_transcription_tokens(self, usage: dict[str, Any]) -> None:
        self.add_tokens(usage)
        counts = token_counts(usage)
        self.transcription_input_tokens += counts["input_tokens"]
        self.transcription_cached_tokens += counts["cached_tokens"]
        self.transcription_output_tokens += counts["output_tokens"]


def token_counts(usage: dict[str, Any]) -> dict[str, int]:
    """The four token counts of a Responses `usage` payload, missing ones as zero."""
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cached_tokens": int((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "reasoning_tokens": int((usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0),
    }
