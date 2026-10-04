"""Chat controller: HTTP and SSE framing only (design 3.5).

The parcours keeps its wire shape: the browser owns the transcript and posts it
back whole. A discussion's transcript lives on the server instead — see
`app/api/routes/discussion.py` (007 design 3.9).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import AiReady, CurriculumCacheDep, ReposDep, StudentDep, TutorServiceDep, open_lesson
from app.api.schemas.chat import ChatRequest
from app.api.sse import turn_response

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
) -> StreamingResponse:
    # Raised here, before the response starts, so they can still be HTTP statuses.
    chapter, ctx = await run_in_threadpool(
        open_lesson, user, payload.course_id, payload.chapter_id, repos, curricula
    )
    items = tutor.build_input(chapter, payload.history, ctx)
    return turn_response(tutor, items, ctx, request)
