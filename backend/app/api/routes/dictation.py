"""Dictation controller: one recording, transcribed to text for the composer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import AiReady, DictationBudgetDep, DictationServiceDep, HubDep
from app.api.schemas.dictation import DictationResponse
from app.domain.errors import DictationDisabled, InvalidAudio, InvalidLanguage
from app.domain.language import is_course_language

router = APIRouter()


@router.post("/dictation", response_model=DictationResponse, dependencies=[AiReady])
async def dictate(
    user: DictationBudgetDep,
    hub: HubDep,
    service: DictationServiceDep,
    audio: Annotated[UploadFile, File(description="One recording, as the browser's MediaRecorder made it.")],
    # The course's language, or none: a chapter that mixes two languages (a language course) is better
    # transcribed without a hint than with the wrong one.
    language: Annotated[str | None, Form()] = None,
    duration_ms: Annotated[int | None, Form(ge=0, le=3_600_000)] = None,
) -> DictationResponse:
    if not hub.dictation_available:
        raise DictationDisabled()
    if language is not None and not is_course_language(language):
        raise InvalidLanguage()
    data = await audio.read()
    if not data:
        raise InvalidAudio()
    text = await service.dictate(
        audio=data,
        content_type=audio.content_type,
        language=language,
        duration_ms=duration_ms,
        user_id=user.id,
    )
    return DictationResponse(text=text)
