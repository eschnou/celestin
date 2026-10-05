"""Photographed work controller: one photo of the student's own handwriting, read into text."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import AiReady, ReposDep, WorkBudgetDep, WorkReaderDep, owned_course
from app.api.schemas.work import WorkReadResponse
from app.domain.errors import DocumentInvalid

router = APIRouter()

# The one thing the transcription model is asked to say when the photo holds no writing.
_NOTHING = ("[rien de lisible]", "[nothing legible]")


@router.post("/courses/{course_id}/work", response_model=WorkReadResponse, dependencies=[AiReady])
async def read_work(
    course_id: str,
    user: WorkBudgetDep,
    reader: WorkReaderDep,
    repos: ReposDep,
    photo: Annotated[UploadFile, File(description="One photo (JPEG, PNG or WebP) of the student's work.")],
) -> WorkReadResponse:
    # The course gives the language the work is written in, and is the student's own (404 otherwise).
    course = await run_in_threadpool(owned_course, user, course_id, repos)
    data = await photo.read()
    if not data:
        raise DocumentInvalid("empty")
    text = await reader.read(data, course.language, user.id, course.id)
    return WorkReadResponse(text="" if text in _NOTHING else text)
