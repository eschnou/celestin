"""Courses, chapters, their content and the lesson view (005 design 3.12).

Controllers only: validate, resolve ownership, call repositories, map to DTOs.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    AiReady,
    AuthoringDep,
    CurriculumCacheDep,
    DocumentsDep,
    PromptsDep,
    ReposDep,
    SettingsDep,
    StudentDep,
    load_context,
    owned_chapter,
    owned_course,
)
from app.api.schemas.chapter import ChapterResponse
from app.api.schemas.chat import ProgressDTO
from app.api.schemas.courses import (
    ChapterContent,
    ChapterRefDTO,
    ChapterRow,
    ChapterState,
    ChapterView,
    CourseDetail,
    CoursesResponse,
    CourseSummary,
    CreateCourseRequest,
    CurriculumFullDTO,
    Limits,
    RenameCourseRequest,
    SaveCurriculumRequest,
    SavePackRequest,
    SectionFullDTO,
    SourceRequest,
    SubjectDTO,
    SubjectsResponse,
)
from app.config import Settings
from app.db.repositories import ProgressRecord, Repositories
from app.domain.chapter import ChapterRecord, CourseRecord, CourseWithChapters, OwnedChapter
from app.domain.content import validate_content
from app.domain.errors import ContentInvalid, DocumentInvalid, NotFound, SourceLength
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.messages import has_message, render
from app.domain.pack import ContentIssue
from app.domain.language import require_language
from app.domain.subject import SUBJECTS, available_subjects, require_available, require_offered
from app.domain.user import User
from app.services.chapters import CurriculumCache, to_lesson_chapter
from app.services.documents import DOCUMENT_TYPES, Document, DocumentService
from app.services.prompts import PromptLibrary

log = logging.getLogger(__name__)
router = APIRouter()

def authoring_message(chapter: ChapterRecord, locale: Locale = DEFAULT_LOCALE) -> str | None:
    """The failure of a chapter's preparation, by code and stage (006 design 5), in the
    student's language. Before its transcription is stored a run cannot be retried (the
    pages are not kept, 006 R3.4), so those codes say to upload the document again."""
    if chapter.authoring_state != "failed":
        return None
    code = chapter.authoring_error or "internal"
    if chapter.needs_document and has_message(f"transcription.{code}"):
        return render(f"transcription.{code}", locale)
    key = f"authoring.{code}"
    return render(key if has_message(key) else "authoring.internal", locale)


# ------------------------------------------------------------------- mapping


def display_title(position: int, title: str | None, locale: Locale = DEFAULT_LOCALE) -> str:
    """How a chapter is named to the student: the course numbers its chapters by
    position, so reordering them renumbers them and the model never writes a number.
    The number's word is the interface's; the title is the course's and passes through."""
    if title:
        return render("chapter.title", locale, position=position, title=title)
    return render("chapter.untitled", locale, position=position)


def _rows(
    chapters: list[ChapterRecord], records: dict[str, ProgressRecord], locale: Locale
) -> list[ChapterRow]:
    """Chapter states from stored progress. No repair against the curriculum is
    needed here: every content change deletes the chapter's progress (005 R5.5)."""
    last_id = max(records, key=lambda cid: records[cid].updated_at) if records else None
    rows = []
    for chapter in chapters:
        record = records.get(chapter.id)
        done = min(len(record.progress.done), chapter.section_count) if record else 0
        state = _state(chapter, record, done)
        rows.append(
            ChapterRow(
                id=chapter.id,
                position=chapter.position,
                title=chapter.title,
                ready=chapter.ready,
                section_count=chapter.section_count,
                done_count=done,
                state=state,
                last=chapter.id == last_id,
                authoring_state=chapter.authoring_state,
                authoring_message=authoring_message(chapter, locale),
                authoring_stage=chapter.authoring_stage,  # kept on failure: where it stopped
                pages_done=chapter.pages_done,
                page_count=chapter.page_count,
            )
        )
    return rows


def _state(chapter: ChapterRecord, record: ProgressRecord | None, done: int) -> ChapterState:
    if not chapter.ready or record is None or (done == 0 and record.progress.active is None):
        return "not_started"
    if done >= chapter.section_count:
        return "done"
    return "in_progress"


def _summary(entry: CourseWithChapters, rows: list[ChapterRow], locale: Locale) -> CourseSummary:
    course = entry.course
    last = next((row for row in rows if row.last and row.title), None)
    return CourseSummary(
        id=course.id,
        name=course.name,
        subject=course.subject,
        subject_label=SUBJECTS[course.subject].label(locale),
        language=course.language,
        chapters_total=len(rows),
        chapters_done=sum(1 for row in rows if row.state == "done"),
        last_chapter=ChapterRefDTO(id=last.id, title=last.title or "") if last else None,
        generating=sum(1 for row in rows if row.authoring_state == "generating"),
    )


def _progress_for(user: User, entries: list[CourseWithChapters], repos: Repositories) -> dict[str, ProgressRecord]:
    ids = [chapter.id for entry in entries for chapter in entry.chapters if chapter.ready]
    return repos.progress.for_chapters(user.id, ids)


# ------------------------------------------------------------------ subjects


@router.get("/subjects", response_model=SubjectsResponse)
async def subjects(user: StudentDep, settings: SettingsDep) -> SubjectsResponse:
    return SubjectsResponse(
        subjects=[SubjectDTO(id=info.id, label=info.label(user.locale), languages=list(info.languages)) for info in available_subjects()],
        limits=Limits(
            chapter_text_min_chars=settings.chapter_text_min_chars,
            chapter_text_max_chars=settings.chapter_text_max_chars,
            pack_max_chars=settings.pack_max_chars,
            document_max_bytes=settings.document_max_bytes,
            document_max_pages=settings.document_max_pages,
            document_min_pixels=settings.document_min_pixels,
            document_types=list(DOCUMENT_TYPES),
        ),
    )


# ------------------------------------------------------------------- courses


def _list(user: User, repos: Repositories) -> CoursesResponse:
    entries = repos.courses.list_for_user(user.id)
    records = _progress_for(user, entries, repos)
    summaries = []
    for entry in entries:
        own = {c.id: records[c.id] for c in entry.chapters if c.id in records}
        activity = max([entry.course.updated_at, *(r.updated_at for r in own.values())])
        summaries.append(
            (activity, _summary(entry, _rows(entry.chapters, own, user.locale), user.locale))
        )
    summaries.sort(key=lambda pair: pair[0], reverse=True)
    return CoursesResponse(courses=[summary for _, summary in summaries])


@router.get("/courses", response_model=CoursesResponse)
async def list_courses(user: StudentDep, repos: ReposDep, response: Response) -> CoursesResponse:
    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(_list, user, repos)


@router.post("/courses", response_model=CourseSummary, status_code=201)
async def create_course(
    payload: CreateCourseRequest, user: StudentDep, repos: ReposDep, settings: SettingsDep
) -> CourseSummary:
    subject = require_available(payload.subject)
    language = require_language(payload.language)
    require_offered(subject, language)
    course = await run_in_threadpool(
        repos.courses.create,
        user.id,
        payload.name,
        subject,
        settings.max_courses_per_student,
        language=language,
    )
    log.info(
        "course_created",
        extra={"user_id": user.id, "course_id": course.id, "subject": subject, "language": language},
    )
    return _summary(CourseWithChapters(course, []), [], user.locale)  # a new course has no chapter yet


def _detail(user: User, course_id: str, repos: Repositories) -> CourseDetail:
    entry = repos.courses.detail(user.id, course_id)
    if entry is None:
        raise NotFound()
    rows = _rows(entry.chapters, _progress_for(user, [entry], repos), user.locale)
    return CourseDetail(**_summary(entry, rows, user.locale).model_dump(), chapters=rows)


def _summary_of(user: User, course_id: str, repos: Repositories) -> CourseSummary:
    return CourseSummary(**_detail(user, course_id, repos).model_dump(exclude={"chapters"}))


@router.get("/courses/{course_id}", response_model=CourseDetail)
async def course_detail(course_id: str, user: StudentDep, repos: ReposDep, response: Response) -> CourseDetail:
    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(_detail, user, course_id, repos)


@router.patch("/courses/{course_id}", response_model=CourseSummary)
async def rename_course(
    course_id: str, payload: RenameCourseRequest, user: StudentDep, repos: ReposDep
) -> CourseSummary:
    if await run_in_threadpool(repos.courses.rename, user.id, course_id, payload.name) is None:
        raise NotFound()
    log.info("course_renamed", extra={"user_id": user.id, "course_id": course_id})
    return await run_in_threadpool(_summary_of, user, course_id, repos)


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(course_id: str, user: StudentDep, repos: ReposDep) -> Response:
    if not await run_in_threadpool(repos.courses.delete, user.id, course_id):
        raise NotFound()
    log.info("course_deleted", extra={"user_id": user.id, "course_id": course_id})
    return Response(status_code=204)


# ------------------------------------------------------------------ chapters


def _source(text: str, settings: Settings) -> str:
    text = text.strip()
    if not settings.chapter_text_min_chars <= len(text) <= settings.chapter_text_max_chars:
        raise SourceLength(settings.chapter_text_min_chars, settings.chapter_text_max_chars)
    return text


def _row(chapter: ChapterRecord, record: ProgressRecord | None, locale: Locale) -> ChapterRow:
    """The row as the run started, built from the record the runner returned rather
    than re-read, so a run that finishes instantly cannot make the answer say idle.
    `last` belongs to the course page, which the client refetches."""
    (row,) = _rows([chapter], {}, locale)
    if record is None:
        return row
    done = min(len(record.progress.done), chapter.section_count)
    return row.model_copy(update={"done_count": done, "state": _state(chapter, record, done)})


# Optional so that an empty form is refused with the French « vide » message, not a 422 from FastAPI.
Files = Annotated[list[UploadFile] | None, File(description="Un PDF, ou des photos dans l'ordre des pages.")]


async def _document(
    files: list[UploadFile] | None, documents: DocumentService, user: User, course: CourseRecord,
    chapter_id: str | None,
) -> Document:
    """The uploaded files as page images, or a French refusal. The body is already
    capped by the middleware; nothing is kept, and file names are never logged."""
    extra = {"user_id": user.id, "course_id": course.id, "chapter_id": chapter_id}
    started = time.monotonic()
    files = files or []
    try:
        data = [await upload.read() for upload in files]
    finally:
        for upload in files:
            await upload.close()
    try:
        document = await documents.prepare(data)
    except DocumentInvalid as exc:
        log.info("document_refused", extra={**extra, "code": exc.code, "reason": exc.reason, "files": len(data)})
        raise
    log.info(
        "document_received",
        extra={**extra, "kind": document.kind, "files": len(data), "bytes": document.bytes_in,
               "pages": len(document.pages), "render_ms": round((time.monotonic() - started) * 1000)},
    )
    return document


@router.post("/courses/{course_id}/chapters", response_model=ChapterRow, status_code=202, dependencies=[AiReady])
async def add_chapter(
    course_id: str, user: StudentDep, repos: ReposDep, authoring: AuthoringDep, documents: DocumentsDep,
    files: Files = None,
) -> ChapterRow:
    """The chapter exists at once, `generating`; its pages are read, then it is
    prepared, in the background (006 R1, 005 R2.3)."""
    course = await run_in_threadpool(owned_course, user, course_id, repos)
    await authoring.check_can_start(user, course, None)
    document = await _document(files, documents, user, course, None)
    chapter = await authoring.start_document(user, course, None, document)
    log.info(
        "chapter_created",
        extra={"user_id": user.id, "course_id": course_id, "chapter_id": chapter.id, "pages": len(document.pages)},
    )
    return _row(chapter, None, user.locale)  # a new chapter has no progress


@router.put("/courses/{course_id}/chapters/{chapter_id}/document", response_model=ChapterRow, status_code=202, dependencies=[AiReady])
async def replace_document(
    course_id: str, chapter_id: str, user: StudentDep, repos: ReposDep, authoring: AuthoringDep,
    documents: DocumentsDep, files: Files = None,
) -> ChapterRow:
    """A new document for the chapter. The current content stays in use until the
    new one is prepared (006 R5)."""
    owned = await run_in_threadpool(owned_chapter, user, course_id, chapter_id, repos)
    await authoring.check_can_start(user, owned.course, owned.chapter)
    document = await _document(files, documents, user, owned.course, chapter_id)
    chapter = await authoring.start_document(user, owned.course, owned.chapter, document)
    return _row(chapter, await run_in_threadpool(repos.progress.load, user.id, chapter_id), user.locale)


@router.put("/courses/{course_id}/chapters/{chapter_id}/source", response_model=ChapterRow, status_code=202, dependencies=[AiReady])
async def edit_source(
    course_id: str, chapter_id: str, payload: SourceRequest, user: StudentDep, repos: ReposDep,
    settings: SettingsDep, authoring: AuthoringDep,
) -> ChapterRow:
    """A new run on new text. The current content stays in use until it succeeds
    (005 R5.4)."""
    owned = await run_in_threadpool(owned_chapter, user, course_id, chapter_id, repos, source=True)
    chapter = await authoring.start_source_edit(user, owned, _source(payload.source_text, settings))
    return _row(chapter, await run_in_threadpool(repos.progress.load, user.id, chapter_id), user.locale)


@router.post("/courses/{course_id}/chapters/{chapter_id}/retry", response_model=ChapterRow, status_code=202, dependencies=[AiReady])
async def retry_chapter(
    course_id: str, chapter_id: str, user: StudentDep, repos: ReposDep, authoring: AuthoringDep
) -> ChapterRow:
    owned = await run_in_threadpool(owned_chapter, user, course_id, chapter_id, repos, source=True)
    chapter = await authoring.start_retry(user, owned)
    return _row(chapter, await run_in_threadpool(repos.progress.load, user.id, chapter_id), user.locale)


def _view(user: User, course_id: str, chapter_id: str, repos: Repositories, cache: CurriculumCache) -> ChapterView:
    owned = owned_chapter(user, course_id, chapter_id, repos)
    chapter = to_lesson_chapter(owned, cache)
    progress = load_context(user, chapter, repos).progress  # repaired, as the turn sees it
    overview = ChapterResponse.model_validate(chapter.curriculum, from_attributes=True)
    return ChapterView(
        **{**overview.model_dump(), "title": display_title(owned.chapter.position, overview.title, user.locale)},
        position=owned.chapter.position,
        course_id=owned.course.id,
        course_name=owned.course.name,
        subject=owned.course.subject,
        language=owned.course.language,
        progress=ProgressDTO.from_progress(progress),
    )


@router.get("/courses/{course_id}/chapters/{chapter_id}", response_model=ChapterView)
async def chapter_view(
    course_id: str,
    chapter_id: str,
    user: StudentDep,
    repos: ReposDep,
    curricula: CurriculumCacheDep,
    response: Response,
) -> ChapterView:
    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(_view, user, course_id, chapter_id, repos, curricula)


def _content(owned: OwnedChapter, has_progress: bool, locale: Locale) -> ChapterContent:
    chapter = owned.chapter
    curriculum = None
    if chapter.curriculum is not None:
        sections = chapter.curriculum.get("sections", [])
        curriculum = CurriculumFullDTO(
            title=chapter.curriculum.get("title", ""),
            sections=[SectionFullDTO(**section, index=i) for i, section in enumerate(sections, start=1)],
        )
    return ChapterContent(
        id=chapter.id,
        course_id=owned.course.id,
        subject=owned.course.subject,
        language=owned.course.language,
        position=chapter.position,
        version=chapter.content_version,
        ready=chapter.ready,
        title=chapter.title,
        pack=chapter.pack,
        curriculum=curriculum,
        source_text=chapter.source_text or "",
        source_kind=chapter.source_kind,
        page_count=chapter.page_count,
        authoring_state=chapter.authoring_state,
        authoring_message=authoring_message(chapter, locale),
        has_progress=has_progress,
    )


def _load_content(user: User, course_id: str, chapter_id: str, repos: Repositories) -> ChapterContent:
    owned = owned_chapter(user, course_id, chapter_id, repos, source=True)
    return _content(owned, repos.progress.load(user.id, chapter_id) is not None, user.locale)


@router.get("/courses/{course_id}/chapters/{chapter_id}/content", response_model=ChapterContent)
async def chapter_content(
    course_id: str, chapter_id: str, user: StudentDep, repos: ReposDep, response: Response
) -> ChapterContent:
    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(_load_content, user, course_id, chapter_id, repos)


def _save(
    user: User,
    course_id: str,
    chapter_id: str,
    version: int,
    kind: str,
    repos: Repositories,
    prompts: PromptLibrary,
    settings: Settings,
    *,
    pack: str | None = None,
    curriculum: dict | None = None,
) -> ChapterContent:
    """One edit, pack or path: the edited part replaces the stored one, the whole is
    validated together (template, curriculum rules, references), then adopted."""
    owned = owned_chapter(user, course_id, chapter_id, repos, source=True)
    stored = owned.chapter
    if stored.pack is None or stored.curriculum is None:
        raise ContentInvalid(
            [ContentIssue("chapitre", "ce chapitre n'a pas encore de contenu", "chapter.no_content")]
        )
    data = {**(curriculum if curriculum is not None else stored.curriculum), "id": chapter_id}
    subject, language = owned.course.subject, owned.course.language
    content, issues = validate_content(
        pack if pack is not None else stored.pack,
        data,
        prompts.template(subject, language),
        settings.pack_max_chars,
        prompts.other_templates(subject, language),
    )
    if content is None:
        raise ContentInvalid(issues)
    had_progress = repos.progress.load(user.id, chapter_id) is not None
    adopted = repos.chapters.adopt_content(chapter_id, content, expected_version=version)
    log.info(
        "chapter_content_saved",
        extra={
            "user_id": user.id,
            "course_id": course_id,
            "chapter_id": chapter_id,
            "kind": kind,
            "version": adopted.content_version,
            "progress_reset": had_progress,
        },
    )
    return _content(OwnedChapter(owned.course, adopted), False, user.locale)


@router.put("/courses/{course_id}/chapters/{chapter_id}/pack", response_model=ChapterContent)
async def save_pack(
    course_id: str, chapter_id: str, payload: SavePackRequest, user: StudentDep, repos: ReposDep,
    prompts: PromptsDep, settings: SettingsDep,
) -> ChapterContent:
    return await run_in_threadpool(
        lambda: _save(user, course_id, chapter_id, payload.version, "pack", repos, prompts, settings, pack=payload.pack)
    )


@router.put("/courses/{course_id}/chapters/{chapter_id}/curriculum", response_model=ChapterContent)
async def save_curriculum(
    course_id: str, chapter_id: str, payload: SaveCurriculumRequest, user: StudentDep, repos: ReposDep,
    prompts: PromptsDep, settings: SettingsDep,
) -> ChapterContent:
    curriculum = payload.curriculum.model_dump()
    return await run_in_threadpool(
        lambda: _save(
            user, course_id, chapter_id, payload.version, "curriculum", repos, prompts, settings, curriculum=curriculum
        )
    )


@router.delete("/courses/{course_id}/chapters/{chapter_id}", status_code=204)
async def delete_chapter(course_id: str, chapter_id: str, user: StudentDep, repos: ReposDep) -> Response:
    if not await run_in_threadpool(repos.chapters.delete, user.id, course_id, chapter_id):
        raise NotFound()
    log.info("chapter_deleted", extra={"user_id": user.id, "course_id": course_id, "chapter_id": chapter_id})
    return Response(status_code=204)


@router.delete("/courses/{course_id}/chapters/{chapter_id}/progress", status_code=204)
async def reset_progress(course_id: str, chapter_id: str, user: StudentDep, repos: ReposDep) -> Response:
    def reset() -> None:
        if not repos.chapters.owns(user.id, course_id, chapter_id):
            raise NotFound()
        repos.progress.clear(user.id, chapter_id)

    await run_in_threadpool(reset)
    log.info("progress_reset", extra={"user_id": user.id, "chapter_id": chapter_id})
    return Response(status_code=204)
