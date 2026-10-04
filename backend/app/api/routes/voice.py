"""Voice controller (003 design 3.1): mint, execute one tool, log usage."""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    AiReady,
    CurriculumCacheDep,
    DiscussionServiceDep,
    HubDep,
    ReposDep,
    StudentDep,
    VoiceBudgetDep,
    VoiceServiceDep,
    open_lesson,
)
from app.api.schemas.voice import (
    VoiceSessionRequest,
    VoiceSessionResponse,
    VoiceToolRequest,
    VoiceToolResponse,
    VoiceUsageReport,
)
from app.domain.errors import NotFound, VoiceDisabled

log = logging.getLogger(__name__)
router = APIRouter(prefix="/voice")


@router.post("/session", response_model=VoiceSessionResponse, status_code=201, dependencies=[AiReady])
async def create_session(
    payload: VoiceSessionRequest,
    hub: HubDep,
    service: VoiceServiceDep,
    user: VoiceBudgetDep,
    curricula: CurriculumCacheDep,
    repos: ReposDep,
    discussions: DiscussionServiceDep,
) -> JSONResponse:
    if not hub.voice_available:  # voice enabled, a voice model and a Realtime-capable connection (spec 014)
        raise VoiceDisabled()

    def prepare():
        chapter, ctx = open_lesson(
            user, payload.course_id, payload.chapter_id, repos, curricula, payload.mode
        )
        if payload.mode != "discussion":
            return chapter, ctx, payload.history
        # A discussion is seeded from its stored conversation, not from a posted
        # transcript: the server owns what was said (007 R4.4).
        if payload.conversation_id is None:
            raise NotFound()
        conversation = discussions.open_conversation(user.id, chapter, payload.conversation_id)
        return chapter, ctx, discussions.stored_entries(conversation)

    chapter, ctx, entries = await run_in_threadpool(prepare)
    result = await service.create_session(chapter, entries, ctx)
    log.info("voice_session_issued", extra={"session_id": result.session_id, "user_id": user.id})
    return JSONResponse(
        status_code=201,
        content=result.model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/tool", response_model=VoiceToolResponse)
async def execute_tool(
    payload: VoiceToolRequest,
    service: VoiceServiceDep,
    user: StudentDep,
    curricula: CurriculumCacheDep,
    repos: ReposDep,
) -> VoiceToolResponse:
    started = time.monotonic()
    _, ctx = await run_in_threadpool(
        open_lesson, user, payload.course_id, payload.chapter_id, repos, curricula, payload.mode
    )
    result = await run_in_threadpool(service.execute_tool, payload.name, payload.arguments, ctx)
    log.info(
        "voice_tool",
        extra={
            "session_id": payload.session_id,
            "user_id": user.id,
            "mode": payload.mode,
            "tool": payload.name,
            "ok": result.event is not None,
            "event": (result.event or {}).get("event"),
            "section_active": result.progress.active,
            "ms": round((time.monotonic() - started) * 1000),
        },
    )
    return result


@router.post("/usage", status_code=204)
async def report_usage(
    request: Request, service: VoiceServiceDep, user: StudentDep, repos: ReposDep
) -> Response:
    """Never fails the caller: `sendBeacon` cannot retry (003 design 3.1)."""
    try:
        report = VoiceUsageReport.model_validate(json.loads(await request.body()))
    except (ValueError, ValidationError) as exc:
        log.warning("voice_usage_malformed", extra={"detail": str(exc)[:200]})
        return Response(status_code=204)
    cost = service.log_usage(report, user.id)
    try:
        await run_in_threadpool(repos.voice_usage.add, user.id, report, cost)
    except Exception:  # noqa: BLE001 - a beacon cannot retry; the log line survives
        log.exception("voice_usage_not_stored")
    return Response(status_code=204)
