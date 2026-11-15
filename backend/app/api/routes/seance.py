"""Séance controller: HTTP only (spec 018).

Three routes. The lesson reads its live séance before it mounts (D6), the cahier
reads every séance of the chapter (D8), and the browser reports a parcours turn the
server did not see to the end (D7): a spoken one, whose speech never reaches the
server (same deviation as 007 D1), or one the learner stopped. Every route goes
through `lesson_chapter`: 404 for another student's chapter, 409 until it has content.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    CurriculumCacheDep,
    ReposDep,
    SeanceReportBudgetDep,
    SeanceServiceDep,
    StudentDep,
    lesson_chapter,
    load_context,
)
from app.api.schemas.chat import ProgressDTO, ToolEntry
from app.api.schemas.seance import (
    NotebookResponse,
    SeanceDTO,
    SeanceReportRequest,
    SeanceResponse,
    SeanceSummary,
)
from app.api.stored import stored_entry
from app.services import conversations
from app.services.seance import MODE
from app.services.tools.context import StoredView

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/courses/{course_id}/chapters/{chapter_id}/seance")
async def read_seance(
    course_id: str,
    chapter_id: str,
    user: StudentDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    seances: SeanceServiceDep,
    response: Response,
) -> SeanceResponse:
    """The live séance, or null, with what the lesson starts from: the progress and the
    sections' card counts, read together. A pure read apart from the lazy
    `content_changed` close: a full séance rolls over on the next turn, not here."""

    def work() -> SeanceResponse:
        chapter = lesson_chapter(user, course_id, chapter_id, repos, curricula)
        record = seances.live(user.id, chapter)
        progress = load_context(user, chapter, repos).progress  # repaired, as the turn sees it
        seance = None
        if record is not None:
            view = StoredView(chapter.curriculum, progress)
            seance = SeanceDTO(
                id=record.id,
                section_id=record.section_id,
                entries=[
                    stored_entry(entry, user.locale, MODE, view)
                    for entry in conversations.stored_entries(record)
                    # A refused call was never shown: the browser did not record it either.
                    if not isinstance(entry, ToolEntry) or entry.ok
                ],
            )
        return SeanceResponse(
            seance=seance,
            progress=ProgressDTO.from_progress(progress),
            seances={
                section: SeanceSummary(cards=cards)
                for section, cards in seances.card_counts(user.id, chapter).items()
            },
        )

    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(work)


@router.get("/courses/{course_id}/chapters/{chapter_id}/notebook")
async def read_notebook(
    course_id: str,
    chapter_id: str,
    user: StudentDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    seances: SeanceServiceDep,
    response: Response,
) -> NotebookResponse:
    """The cahier: what was shown and said, per section in path order (D8)."""

    def work() -> NotebookResponse:
        chapter = lesson_chapter(user, course_id, chapter_id, repos, curricula)
        return NotebookResponse.model_validate({"sections": seances.notebook(user.id, chapter)})

    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(work)


@router.post("/seance/report", status_code=204)
async def report_turn(
    payload: SeanceReportRequest,
    user: SeanceReportBudgetDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    seances: SeanceServiceDep,
) -> None:
    """A parcours turn the browser reports, stored with the split rule like a text turn
    (D3, D7): a spoken one, or one the learner stopped, as far as it went. The one write
    without a model call (D10): rate limited per student (`429 seance_report_rate`),
    validated (`422`: the shape and the cards here, the section ids and the tools by the
    service), and refused once the chapter holds `seance_max_rows` séances (`409 seance_full`)."""

    def work() -> None:
        chapter = lesson_chapter(user, payload.course_id, payload.chapter_id, repos, curricula)
        progress = load_context(user, chapter, repos).progress
        stored = seances.store_reported(user.id, chapter, progress, list(payload.entries))
        log.info(
            "seance_reported",
            extra={"user_id": user.id, "chapter_id": chapter.id, "added": len(payload.entries), "rows": len(stored)},
        )

    await run_in_threadpool(work)
