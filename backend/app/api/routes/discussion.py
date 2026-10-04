"""Discussion controller: HTTP and SSE framing only (007 design 3.9).

Three routes and one rule. A turn names its conversation instead of carrying the
transcript, so the server is the source of truth for what was said; and the turn
is appended once, after it ended, so a conversation is either advanced by a
complete turn or left exactly as it was.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    AiReady,
    CurriculumCacheDep,
    DiscussionServiceDep,
    ReposDep,
    StudentDep,
    TutorServiceDep,
    lesson_chapter,
    open_lesson,
)
from app.api.schemas.discussion import (
    ConversationDTO,
    ConversationResponse,
    DiscussionTurnRequest,
    StoredEntry,
    VoiceTurnRequest,
)
from app.api.schemas.events import TurnEnd, TurnEvent
from app.api.sse import turn_response
from app.db.repositories import ConversationRecord
from app.services.discussion import DiscussionService, entries_from_events

log = logging.getLogger(__name__)
router = APIRouter()

MODE = "discussion"


def _dto(
    conversation: ConversationRecord, discussions: DiscussionService, locale: Locale
) -> ConversationDTO:
    return ConversationDTO(
        id=conversation.id,
        chapter_id=conversation.chapter_id,
        entries=[StoredEntry.of(entry, locale) for entry in discussions.stored_entries(conversation)],
        entry_count=conversation.entry_count,
        created_at=conversation.created_at,
    )


@router.get("/courses/{course_id}/chapters/{chapter_id}/discussion")
async def read_discussion(
    course_id: str,
    chapter_id: str,
    user: StudentDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    discussions: DiscussionServiceDep,
) -> ConversationResponse:
    """The live conversation, or null. A pure read: a first open sees null and
    posts, which is the same call « Nouvelle conversation » makes."""

    def work() -> ConversationRecord | None:
        chapter = lesson_chapter(user, course_id, chapter_id, repos, curricula)
        return discussions.live(user.id, chapter)

    conversation = await run_in_threadpool(work)
    return ConversationResponse(
        conversation=_dto(conversation, discussions, user.locale) if conversation else None
    )


@router.post("/courses/{course_id}/chapters/{chapter_id}/discussion", status_code=201)
async def start_discussion(
    course_id: str,
    chapter_id: str,
    user: StudentDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    discussions: DiscussionServiceDep,
) -> ConversationResponse:
    """« Nouvelle conversation »: the live one is closed as `replaced` and a new
    empty one starts. Progress and the path are untouched."""

    def work() -> ConversationRecord:
        chapter = lesson_chapter(user, course_id, chapter_id, repos, curricula)
        return discussions.start(user.id, chapter)

    return ConversationResponse(conversation=_dto(await run_in_threadpool(work), discussions, user.locale))


@router.post("/discussion/turn", dependencies=[AiReady])
async def discussion_turn(
    payload: DiscussionTurnRequest,
    request: Request,
    tutor: TutorServiceDep,
    user: StudentDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    discussions: DiscussionServiceDep,
) -> StreamingResponse:
    # Everything that can fail on our side fails before the stream opens, so it
    # can still be an HTTP status.
    def prepare():
        chapter, ctx = open_lesson(
            user, payload.course_id, payload.chapter_id, repos, curricula, MODE
        )
        conversation = discussions.open_conversation(user.id, chapter, payload.conversation_id)
        read, added = discussions.turn_entries(conversation, payload.message)
        return conversation, ctx, added, tutor.build_input(chapter, read, ctx)

    conversation, ctx, added, items = await run_in_threadpool(prepare)

    async def store(produced: list[TurnEvent], _: TurnEnd) -> None:
        """One write, after the turn ended (007 §3.8). A provider failure or a
        disconnect never reaches here, so nothing half-finished is stored."""
        entries = [*added, *entries_from_events(produced)]
        await run_in_threadpool(discussions.append, conversation, entries)

    return turn_response(tutor, items, ctx, request, on_complete=store)


@router.post("/discussion/voice/turn", status_code=204)
async def record_voice_turn(
    payload: VoiceTurnRequest,
    user: StudentDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    discussions: DiscussionServiceDep,
) -> None:
    """A spoken turn, reported by the browser (007 deviation D1): the model's
    speech reaches the browser over WebRTC and never the server."""

    def work() -> None:
        chapter = lesson_chapter(user, payload.course_id, payload.chapter_id, repos, curricula)
        conversation = discussions.open_conversation(user.id, chapter, payload.conversation_id)
        discussions.append(conversation, list(payload.entries))

    await run_in_threadpool(work)
