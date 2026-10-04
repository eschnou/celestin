"""Dependency wiring.

`create_app` is the composition root: it builds the prompt library, the
repositories and the LLM clients once and puts them on `app.state`. These resolve from there, so object
lifetime equals app lifetime and nothing is cached process-wide — which matters
for the provider client, since it owns a connection pool bound to an event loop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.db.repositories import Repositories
from app.domain.mode import DEFAULT_MODE, Mode
from app.domain.errors import (
    AiNotConfigured,
    DictationRateLimited,
    Forbidden,
    NotAuthenticated,
    NotFound,
    VoiceRateLimited,
    WorkRateLimited,
)
from app.domain.progress import Progress
from app.domain.user import ROLES, Role, User
from app.providers.base import LLMClient, RealtimeClient
from app.providers.hub import ProviderHub
from app.services.auth_service import AuthService
from app.domain.chapter import CourseRecord, LessonChapter, OwnedChapter
from app.services.authoring.runner import AuthoringRunner
from app.services.documents import DocumentService
from app.services.chapters import CurriculumCache, to_lesson_chapter
from app.services.discussion import DiscussionService
from app.services.ai_settings import AiSettingsService
from app.services.prompts import PromptLibrary
from app.services.tools.context import TurnContext
from app.services.tutor_service import TutorService
from app.services.dictation import DictationService
from app.services.work_reading import WorkReader
from app.services.voice_service import VoiceService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_authoring(request: Request) -> AuthoringRunner:
    return request.app.state.authoring


def get_documents(request: Request) -> DocumentService:
    return request.app.state.documents


def get_curriculum_cache(request: Request) -> CurriculumCache:
    return request.app.state.curricula


def get_prompts(request: Request) -> PromptLibrary:
    return request.app.state.prompts


PromptsDep = Annotated[PromptLibrary, Depends(get_prompts)]


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


def get_repos(request: Request) -> Repositories:
    return request.app.state.repos


ReposDep = Annotated[Repositories, Depends(get_repos)]


def get_hub(request: Request) -> ProviderHub:
    return request.app.state.hub


HubDep = Annotated[ProviderHub, Depends(get_hub)]


def get_ai_settings(request: Request) -> AiSettingsService:
    return request.app.state.ai_settings


AiSettingsDep = Annotated[AiSettingsService, Depends(get_ai_settings)]


def get_realtime(request: Request) -> RealtimeClient:
    return request.app.state.realtime


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
CurriculumCacheDep = Annotated[CurriculumCache, Depends(get_curriculum_cache)]
AuthoringDep = Annotated[AuthoringRunner, Depends(get_authoring)]
DocumentsDep = Annotated[DocumentService, Depends(get_documents)]


def get_tutor_service(
    settings: SettingsDep,
    prompts: PromptsDep,
    llm: Annotated[LLMClient, Depends(get_llm)],
) -> TutorService:
    return TutorService(llm=llm, prompts=prompts, settings=settings)


TutorServiceDep = Annotated[TutorService, Depends(get_tutor_service)]


def get_voice_service(
    settings: SettingsDep,
    prompts: PromptsDep,
    realtime: Annotated[RealtimeClient, Depends(get_realtime)],
    hub: HubDep,
) -> VoiceService:
    return VoiceService(realtime=realtime, prompts=prompts, settings=settings, ai=hub)


VoiceServiceDep = Annotated[VoiceService, Depends(get_voice_service)]


def get_dictation_service(settings: SettingsDep, hub: HubDep) -> DictationService:
    return DictationService(hub.transcriber, settings, hub)


DictationServiceDep = Annotated[DictationService, Depends(get_dictation_service)]


def get_discussion_service(settings: SettingsDep, repos: ReposDep) -> DiscussionService:
    return DiscussionService(repos=repos, settings=settings)


DiscussionServiceDep = Annotated[DiscussionService, Depends(get_discussion_service)]


COOKIE_NAME = "celestin_session"


def client_host(request: Request, settings: Settings) -> str:
    """The client address, for rate-limit keys. Never logged."""
    host = request.client.host if request.client else "unknown"
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            host = forwarded.split(",")[0].strip()
    return host


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def session_token(request: Request) -> str | None:
    """The cookie for the browser app, or a bearer for everything else (004 §3.1)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(COOKIE_NAME)


def current_user(request: Request, auth: AuthServiceDep) -> User:
    token = session_token(request)
    user = auth.authenticate(token) if token else None
    if user is None:
        raise NotAuthenticated()
    # What the error handler, the SSE stream and the DTOs read (spec 010 §4.1): no
    # second session lookup to know the language.
    request.state.locale = user.locale
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    """The only way into a route. A test refuses any route without this marker
    (R2.4), so admitting a role is always an explicit decision."""

    def _guard(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise Forbidden()
        return user

    _guard.__celestin_roles__ = roles  # type: ignore[attr-defined]
    return _guard


StudentDep = Annotated[User, Depends(require_roles("student"))]
AnyUserDep = Annotated[User, Depends(require_roles(*ROLES))]
AdminDep = Annotated[User, Depends(require_roles("admin"))]


def require_ai(request: Request, _user: StudentDep) -> None:
    """Refuse a route that calls the provider while no AI provider is configured (specs 013 R7, 014 R8.4). Behind
    `StudentDep`, so a visitor who is not signed in learns nothing about the configuration. The
    framework has read the body by now; nothing is stored or processed."""
    if not request.app.state.hub.configured:
        raise AiNotConfigured()


AiReady = Depends(require_ai)


def voice_session_budget(request: Request, user: StudentDep) -> User:
    """Applied to the minting route only: one allowance per session, per user."""
    if not request.app.state.voice_limiter.allow(user.id):
        raise VoiceRateLimited()
    return user


VoiceBudgetDep = Annotated[User, Depends(voice_session_budget)]


def dictation_budget(request: Request, user: StudentDep) -> User:
    """One allowance per recording, per user: each one is a call to the speech model."""
    if not request.app.state.dictation_limiter.allow(user.id):
        raise DictationRateLimited()
    return user


DictationBudgetDep = Annotated[User, Depends(dictation_budget)]


def get_work_reader(
    settings: SettingsDep, prompts: PromptsDep, documents: DocumentsDep, hub: HubDep
) -> WorkReader:
    return WorkReader(hub.authoring_llm, documents, prompts, settings, hub)


WorkReaderDep = Annotated[WorkReader, Depends(get_work_reader)]


def work_budget(request: Request, user: StudentDep) -> User:
    """One allowance per photo, per user: each one is a call to the vision model."""
    if not request.app.state.work_limiter.allow(user.id):
        raise WorkRateLimited()
    return user


WorkBudgetDep = Annotated[User, Depends(work_budget)]


def owned_course(user: User, course_id: str, repos: Repositories) -> CourseRecord:
    """The course, if the user owns it; otherwise 404, never 403 (005 design 3.3)."""
    course = repos.courses.get_owned(user.id, course_id)
    if course is None:
        raise NotFound()
    return course


def owned_chapter(
    user: User, course_id: str, chapter_id: str, repos: Repositories, *, source: bool = False
) -> OwnedChapter:
    """The chapter with its content (the pasted text only with `source`), if the
    user owns the course and the chapter is in it; otherwise 404."""
    owned = repos.chapters.get_owned(user.id, course_id, chapter_id, source=source)
    if owned is None:
        raise NotFound()
    return owned


def lesson_chapter(
    user: User, course_id: str, chapter_id: str, repos: Repositories, cache: CurriculumCache
) -> LessonChapter:
    """The chapter as a lesson: 404 unless owned, 409 until it has content."""
    return to_lesson_chapter(owned_chapter(user, course_id, chapter_id, repos), cache)


def load_context(
    user: User, chapter: LessonChapter, repos: Repositories, mode: Mode = DEFAULT_MODE
) -> TurnContext:
    """The stored progress as a turn context, the store bound for the section
    tools (004 design 3.6).

    A discussion reads the progress and never writes it: `save` stays None, which
    is the second lock behind not declaring the section tools (007 §3.6)."""
    record = repos.progress.load(user.id, chapter.id)
    progress = record.progress if record else Progress()
    save = None
    if mode == "parcours":
        save = lambda p: repos.progress.save(user.id, chapter.id, p, version=chapter.version)  # noqa: E731
    return TurnContext.from_progress(
        chapter.curriculum,
        list(progress.done),
        progress.active,
        save=save,
        user_id=user.id,
        chapter_id=chapter.id,
        mode=mode,
        pack=chapter.pack,
        locale=user.locale,
        language=chapter.language,
    )


def open_lesson(
    user: User,
    course_id: str,
    chapter_id: str,
    repos: Repositories,
    cache: CurriculumCache,
    mode: Mode = DEFAULT_MODE,
) -> tuple[LessonChapter, TurnContext]:
    """Everything a chat or voice request needs before touching the model: the
    ownership check, the content and the stored progress, in one threadpool hop."""
    chapter = lesson_chapter(user, course_id, chapter_id, repos, cache)
    return chapter, load_context(user, chapter, repos, mode)
