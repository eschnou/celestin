from __future__ import annotations

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.api.deps import HubDep, PromptsDep, ReposDep
from app.domain.subject import available_subjects

router = APIRouter()


@router.get("/health")
async def health(
    prompts: PromptsDep, repos: ReposDep, hub: HubDep
) -> dict[str, object]:
    """Prompt files are re-read on every call: a subject prompt or template deleted
    or broken after startup must be visible here (005 design 3.13)."""
    unavailable, active = await run_in_threadpool(lambda: (prompts.unavailable(), repos.runs.active()))
    config = hub.config
    return {
        "status": "degraded" if unavailable else "ok",
        # The models in force (spec 014 R8.3); null while no AI provider is configured.
        "model": config.tutor.model if config else None,
        "authoring_model": config.authoring.model if config else None,
        "prompts_unavailable": unavailable,
        "subjects": [info.id for info in available_subjects()],
        "authoring_active": active,
        # No AI provider yet means no AI at all, voice included (the mic stays inert). Voice also needs a
        # Realtime-capable connection (spec 014 R10).
        "ai_configured": hub.configured,
        "voice": hub.voice_available,
        "voice_model": config.voice.model if config and config.voice else None,
        # The composer's microphone: a speech-to-text model on a connection that is usable (independent of voice).
        "dictation": hub.dictation_available,
    }
