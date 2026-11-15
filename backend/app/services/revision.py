"""Stored révisions (spec 020): several chapters of one course, rehearsed together.

A sibling of `discussion.py`, sharing `conversations.py`: a révision is a `conversations`
row, with the discussion's caps and append policy (a stopped or failed turn stores nothing),
named by its course instead of a chapter. What differs:

- **Its scope is fixed when it starts** (D2): a set of the course's ready chapters, stored as
  `[{chapter_id, content_version}]` in course order, bounded by `revision_max_pack_chars`
  (the prompt carries every chosen pack) and by a daily quota.
- **One live révision per student and course** (D6), « Nouvelle révision » closing it
  `replaced`. A révision one of whose chapters changed version or was deleted is closed
  `content_changed`, lazily, when it is next read.
- **Nothing here moves the path** (D4): the progress of each chapter is read, never written,
  and what a révision writes is the student's self-assessment of a section
  (`revision_results`), with the turn's transcript, from its stored `record_result` calls (D6).

What the model reads takes the course language only; nothing here knows the interface's.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.api.schemas.chat import Entry, ToolEntry
from app.config import Settings
from app.db.repositories import ConversationRecord, Repositories
from app.domain import progress as progress_domain
from app.domain.chapter import ChapterRecord, CourseRecord, LessonChapter, OwnedChapter
from app.domain.errors import (
    ChapterNotReady,
    ChapterUnavailable,
    ConversationBusy,
    NotFound,
    RevisionBusy,
    RevisionClosed,
    RevisionFull,
    RevisionNoChapter,
    RevisionQuota,
    RevisionStarted,
    RevisionTooLarge,
)
from app.domain.mode import Mode
from app.domain.progress import Progress
from app.domain.revision import OUTCOMES, NewResult, Outcome, Results, RevisionChapter, RevisionScope
from app.services import conversations
from app.services.chapters import CurriculumCache, to_lesson_chapter

log = logging.getLogger(__name__)

MODE: Mode = "revision"


@dataclass(frozen=True)
class CourseChapter:
    """A chapter of the course as a révision reads it: its row, the lesson when it is ready
    (None otherwise, or when its stored content no longer validates) and the student's
    progress on it, repaired against its path (empty when it is not ready)."""

    record: ChapterRecord
    lesson: LessonChapter | None
    progress: Progress


@dataclass(frozen=True)
class OpenRevision:
    """What a révision turn starts from: the row, its scope (the chosen chapters, what was
    noted before) and what this révision noted so far, latest per section."""

    conversation: ConversationRecord
    scope: RevisionScope
    noted: dict[tuple[str, str], Outcome]


def scope_versions(conversation: ConversationRecord) -> dict[str, int]:
    """chapter id -> the content version the révision was started on."""
    return {str(item["chapter_id"]): int(item["content_version"]) for item in conversation.scope or []}


class RevisionService:
    def __init__(self, repos: Repositories, settings: Settings, curricula: CurriculumCache) -> None:
        self._repos = repos
        self._settings = settings
        self._curricula = curricula

    # ------------------------------------------------------------------ chapters

    def chapters(self, user_id: str, course: CourseRecord, ids: Iterable[str] | None = None) -> list[CourseChapter]:
        """The chapters of the course, in course order, with what a révision reads of them: every one (the page, a
        start), or those of `ids` only (a turn reads its scope; an id that is gone is simply absent)."""
        records = self._repos.chapters.with_content(course.id, ids)
        stored = self._repos.progress.for_chapters(user_id, [c.id for c in records if c.ready])
        out = []
        for record in records:
            lesson: LessonChapter | None = None
            progress = Progress()
            if record.ready:
                try:
                    lesson = to_lesson_chapter(OwnedChapter(course=course, chapter=record), self._curricula)
                except (ChapterNotReady, ChapterUnavailable):
                    lesson = None
            if lesson is not None and record.id in stored:
                saved = stored[record.id].progress
                progress = progress_domain.normalise(
                    list(saved.done), saved.active, lesson.curriculum, saved.skipped
                )
            out.append(CourseChapter(record, lesson, progress))
        return out

    def results(self, user_id: str, course: CourseRecord, chapters: list[CourseChapter]) -> Results:
        """The latest self-assessment per section, every révision of the course, current content versions only."""
        versions = {c.record.id: c.record.content_version for c in chapters if c.lesson is not None}
        every, _ = self._repos.revision_results.latest(user_id, course.id, versions)
        return every

    # ---------------------------------------------------------------- révisions

    def _stale(self, chapters: list[CourseChapter]) -> Callable[[ConversationRecord], bool]:
        """Whether a chapter of a révision was deleted, changed version or no longer reads (D6), against `chapters`
        (a chapter of the scope missing from them was deleted)."""
        current = {c.record.id: c for c in chapters}

        def stale(conversation: ConversationRecord) -> bool:
            for chapter_id, version in scope_versions(conversation).items():
                chapter = current.get(chapter_id)
                if chapter is None or chapter.lesson is None or chapter.record.content_version != version:
                    return True
            return not conversation.scope

        return stale

    def live(self, user_id: str, course: CourseRecord, chapters: list[CourseChapter]) -> ConversationRecord | None:
        """The live révision, or None. One whose chapters changed is closed here rather than continued: its packs
        are gone. Lazy, so a content edit or a chapter deletion need not know about révisions."""
        found = self._repos.conversations.live_revision(user_id, course.id)
        return conversations.live_row(self._repos, found, self._stale(chapters), "revision_closed")

    def start(
        self, user_id: str, course: CourseRecord, chapter_ids: list[str]
    ) -> tuple[ConversationRecord, list[CourseChapter]]:
        """A new empty révision on the chosen chapters, closing the live one as `replaced` (D6), and every chapter
        of the course as it read them (the page's answer is built from them). Refused without a chapter (422), for
        a chapter not in the course (404), not ready (409), over the pack budget (422) and past the daily quota
        (429)."""
        wanted = list(dict.fromkeys(chapter_ids))
        if not wanted:
            raise RevisionNoChapter()
        chapters = self.chapters(user_id, course)
        known = {c.record.id: c for c in chapters}
        if any(chapter_id not in known for chapter_id in wanted):
            raise NotFound()
        chosen = [c for c in chapters if c.record.id in wanted]  # course order, whatever order was posted
        for chapter in chosen:
            if not chapter.record.ready:
                raise ChapterNotReady()
            if chapter.lesson is None:
                raise ChapterUnavailable()
        size = sum(len(c.lesson.pack) for c in chosen if c.lesson is not None)
        maximum = self._settings.revision_max_pack_chars
        if size > maximum:
            log.info(
                "revision_too_large",
                extra={"user_id": user_id, "course_id": course.id, "chapters": len(chosen), "pack_chars": size},
            )
            raise RevisionTooLarge(maximum, size)
        per_day = self._settings.revision_sessions_per_day
        conversations.check_quota(self._repos, user_id, MODE, per_day, RevisionQuota, course_id=course.id)
        scope = [{"chapter_id": c.record.id, "content_version": c.record.content_version} for c in chosen]
        try:
            conversation = self._repos.conversations.start_revision(user_id, course.id, scope)
        except ConversationBusy:  # another tab started one at the same instant
            raise RevisionBusy() from None
        log.info(
            "revision_started",
            extra={
                "conversation_id": conversation.id,
                "user_id": user_id,
                "course_id": course.id,
                "chapters": len(chosen),
                "pack_chars": size,
            },
        )
        return conversation, chapters

    def open_revision(self, user_id: str, course: CourseRecord, revision_id: str) -> OpenRevision:
        """The révision a turn names, ready to be continued, with its scope: only the chosen chapters are read.
        Unknown or another student's (or another course's) is a 404; closed, changed or full a 409."""
        conversation = self._repos.conversations.get_revision(user_id, course.id, revision_id)
        if conversation is None:
            raise NotFound()
        if not conversation.live:
            raise RevisionClosed(conversation.closed_reason or "replaced")
        chapters = self.chapters(user_id, course, scope_versions(conversation))
        if conversations.live_row(self._repos, conversation, self._stale(chapters), "revision_closed") is None:
            raise RevisionClosed("content_changed")
        if conversations.is_full(conversation, self._settings):
            raise RevisionFull()
        return self._open(user_id, course, conversation, chapters)

    def _open(
        self, user_id: str, course: CourseRecord, conversation: ConversationRecord, chapters: list[CourseChapter]
    ) -> OpenRevision:
        current = {c.record.id: c for c in chapters}
        chosen: list[RevisionChapter] = []
        for chapter_id in scope_versions(conversation):
            chapter = current[chapter_id]
            assert chapter.lesson is not None  # `_stale` said every chapter of the scope reads
            chosen.append(
                RevisionChapter(
                    number=chapter.record.position,
                    id=chapter.record.id,
                    title=chapter.lesson.title,
                    version=chapter.record.content_version,
                    pack=chapter.lesson.pack,
                    curriculum=chapter.lesson.curriculum,
                    progress=chapter.progress,
                )
            )
        versions = {c.id: c.version for c in chosen}
        earlier, here = self._repos.revision_results.latest(user_id, course.id, versions, conversation_id=conversation.id)
        scope = RevisionScope(id=conversation.id, course_id=course.id, chapters=tuple(chosen), earlier=earlier)
        return OpenRevision(conversation, scope, {key: noted.outcome for key, noted in here.items()})

    # -------------------------------------------------------------------- turns

    def turn_entries(
        self, conversation: ConversationRecord, message: str | None
    ) -> tuple[list[Entry], list[Entry]]:
        """`(what the model reads, what the turn adds)`. `message is None` opens the révision, only while it is
        empty: Célestin speaks first."""
        stored = conversations.stored_entries(conversation)
        added = conversations.opening(stored, message, RevisionStarted)
        return [*stored, *added], added

    def append(self, conversation: ConversationRecord, entries: list[Entry]) -> None:
        """One write, after the turn ended: the discussion's policy (a stopped or failed turn stores nothing), with
        the turn's results read from its stored `record_result` calls, in the same transaction (D6: a result never
        exists without its stored call). Another turn stored first is the révision's `409 conversation_busy`."""
        results = turn_results(conversation, entries)
        try:
            conversations.append(self._repos, self._settings, conversation, entries, results)
        except ConversationBusy:
            raise RevisionBusy() from None
        for result in results:
            log.info(
                "revision_result",
                extra={
                    "user_id": conversation.user_id,
                    "course_id": conversation.course_id,
                    "chapter_id": result.chapter_id,
                    "section_id": result.section_id,
                    "outcome": result.outcome,
                },
            )


def turn_results(conversation: ConversationRecord, entries: list[Entry]) -> list[NewResult]:
    """The self-assessments a turn's entries record, in order: one per successful `record_result` call, against the
    content version the révision holds for its chapter."""
    versions = scope_versions(conversation)
    out = []
    for entry in entries:
        if conversations.is_ok_call(entry, "record_result") and isinstance(entry, ToolEntry):
            chapter_id, outcome = entry.chapter_id, entry.arguments.get("outcome")
            if chapter_id in versions and outcome in OUTCOMES:
                section_id = str(entry.arguments.get("section_id", ""))
                out.append(NewResult(chapter_id, section_id, outcome, versions[chapter_id]))
    return out
