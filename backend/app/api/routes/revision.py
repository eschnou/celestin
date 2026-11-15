"""Révision controller: HTTP and SSE framing only (spec 020).

Three routes. The page reads the course's chapters, the live révision and the latest
self-assessments in one call; « Commencer la révision » / « Nouvelle révision » posts the
chosen chapters and gets the same body back; a turn names its révision, and is appended
once, after it ended, with its results, as a discussion's is. Every route resolves the course through `owned_course`: 404 for another
student's course, never 403.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    AiReady,
    ReposDep,
    RevisionServiceDep,
    StudentDep,
    TutorServiceDep,
    owned_course,
    revision_context,
)
from app.api.schemas.events import TurnEnd, TurnEvent
from app.api.schemas.revision import (
    RevisionChapterDTO,
    RevisionDTO,
    RevisionResultDTO,
    RevisionSectionDTO,
    RevisionTurnRequest,
    RevisionView,
    StartRevisionRequest,
)
from app.api.sse import turn_response
from app.api.stored import stored_entry
from app.db.repositories import ConversationRecord
from app.domain.chapter import CourseRecord
from app.domain.locale import Locale
from app.domain.user import User
from app.services import conversations
from app.services.conversations import entries_from_events
from app.services.revision import MODE, CourseChapter, RevisionService, scope_versions
from app.services.tools.context import StoredView

log = logging.getLogger(__name__)
router = APIRouter()


def _dto(conversation: ConversationRecord, chapters: list[CourseChapter], locale: Locale) -> RevisionDTO:
    view = StoredView(chapters={c.record.id: c.lesson.curriculum for c in chapters if c.lesson is not None})
    return RevisionDTO(
        id=conversation.id,
        chapter_ids=list(scope_versions(conversation)),
        entries=[stored_entry(entry, locale, MODE, view) for entry in conversations.stored_entries(conversation)],
        entry_count=conversation.entry_count,
        created_at=conversation.created_at,
    )


def _chapter(chapter: CourseChapter) -> RevisionChapterDTO:
    record, lesson, progress = chapter.record, chapter.lesson, chapter.progress
    sections = [
        RevisionSectionDTO(
            id=s.id, index=s.index, kind=s.kind, title=s.title, state=progress.state_of(s.id)
        )
        for s in (lesson.curriculum.sections if lesson is not None else ())
    ]
    return RevisionChapterDTO(
        id=record.id,
        position=record.position,
        title=record.title,
        ready=lesson is not None,
        section_count=len(sections),
        done_count=sum(1 for s in sections if s.state == "done"),
        skipped_count=sum(1 for s in sections if s.state == "skipped"),
        sections=sections,
    )


def _view(
    user: User,
    course: CourseRecord,
    revisions: RevisionService,
    chapters: list[CourseChapter],
    live: ConversationRecord | None,
) -> RevisionView:
    """The page's one read, from the chapters already loaded: the GET's answer, and the POST's."""
    results = revisions.results(user.id, course, chapters)
    return RevisionView(
        revision=_dto(live, chapters, user.locale) if live is not None else None,
        chapters=[_chapter(c) for c in chapters],
        results=[
            RevisionResultDTO(chapter_id=chapter_id, section_id=section_id, outcome=noted.outcome, at=noted.at)
            for (chapter_id, section_id), noted in results.items()
        ],
    )


@router.get("/courses/{course_id}/revision")
async def read_revision(
    course_id: str, user: StudentDep, repos: ReposDep, revisions: RevisionServiceDep, response: Response
) -> RevisionView:
    """The live révision or null, every chapter of the course with its sections' states, and the latest
    self-assessment per section. A pure read apart from the lazy `content_changed` close."""

    def work() -> RevisionView:
        course = owned_course(user, course_id, repos)
        chapters = revisions.chapters(user.id, course)
        return _view(user, course, revisions, chapters, revisions.live(user.id, course, chapters))

    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(work)


@router.post("/courses/{course_id}/revision", status_code=201)
async def start_revision(
    course_id: str,
    payload: StartRevisionRequest,
    user: StudentDep,
    repos: ReposDep,
    revisions: RevisionServiceDep,
) -> RevisionView:
    """« Commencer la révision » and « Nouvelle révision »: the live one is closed as `replaced` and a new empty
    one starts on the chosen chapters. Progress and the paths are untouched. The answer is the page's read (the
    GET's body), built from the chapters the start already read, so the page needs no second read."""

    def work() -> RevisionView:
        course = owned_course(user, course_id, repos)
        conversation, chapters = revisions.start(user.id, course, list(payload.chapter_ids))
        return _view(user, course, revisions, chapters, conversation)

    return await run_in_threadpool(work)


@router.post("/revision/turn", dependencies=[AiReady])
async def revision_turn(
    payload: RevisionTurnRequest,
    request: Request,
    tutor: TutorServiceDep,
    user: StudentDep,
    repos: ReposDep,
    revisions: RevisionServiceDep,
) -> StreamingResponse:
    # Everything that can fail on our side fails before the stream opens, so it can still be an HTTP status.
    def prepare():
        course = owned_course(user, payload.course_id, repos)
        opened = revisions.open_revision(user.id, course, payload.revision_id)
        read, added = revisions.turn_entries(opened.conversation, payload.message)
        ctx = revision_context(user, course, opened)
        return opened.conversation, ctx, added, tutor.build_revision_input(course.subject, read, ctx)

    conversation, ctx, added, items = await run_in_threadpool(prepare)

    async def store(produced: list[TurnEvent], _: TurnEnd) -> None:
        """One write, after the turn ended, with the turn's results: a provider failure or a disconnect never
        reaches here, so nothing half-finished is stored, and no result without its call (D6)."""
        entries = [*added, *entries_from_events(produced)]
        await run_in_threadpool(revisions.append, conversation, entries)

    return turn_response(tutor, items, ctx, request, on_complete=store)
