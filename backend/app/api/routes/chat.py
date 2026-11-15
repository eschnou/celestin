"""Chat controller: HTTP and SSE framing only (design 3.5).

A parcours turn posts the learner's message; the server reads the live séance and
stores the turn when it ends, cut by the split rule (spec 018 D1, D3). A turn that
ends early stores nothing: a turn the learner stopped is reported by the browser
(`POST /api/seance/report`, D7). A discussion's turn has its own route
(`app/api/routes/discussion.py`, 007 design 3.9).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    AiReady,
    CurriculumCacheDep,
    ReposDep,
    SeanceServiceDep,
    StudentDep,
    TutorServiceDep,
    open_lesson,
)
from app.api.schemas.chat import ChatRequest
from app.api.schemas.events import TurnEnd, TurnEvent
from app.api.sse import turn_response
from app.services.conversations import entries_from_events

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat", dependencies=[AiReady])
async def chat(
    payload: ChatRequest,
    request: Request,
    tutor: TutorServiceDep,
    user: StudentDep,
    curricula: CurriculumCacheDep,
    repos: ReposDep,
    seances: SeanceServiceDep,
) -> StreamingResponse:
    # Raised here, before the response starts, so they can still be HTTP statuses.
    def prepare():
        chapter, ctx = open_lesson(user, payload.course_id, payload.chapter_id, repos, curricula)
        turn, read = seances.open_turn(user.id, chapter, ctx.progress, payload.message)
        # Only the turn's ids and counts outlive this: the parsed transcript is dropped with `read`.
        return ctx, turn, tutor.build_input(chapter, read, ctx)

    ctx, turn, items = await run_in_threadpool(prepare)

    async def store(produced: list[TurnEvent], _: TurnEnd) -> None:
        """One write, after the turn ended (spec 018 D3). A provider failure, a
        disconnect or a stop never reaches here (D7)."""
        await run_in_threadpool(seances.store, turn, [*turn.added, *entries_from_events(produced)])

    return turn_response(tutor, items, ctx, request, on_complete=store)
