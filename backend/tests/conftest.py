from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine

from app.config import Settings
from app.db.base import Base, make_engine, make_session_factory
from app.db.repositories import Repositories
from app.providers.base import ToolCallRequested
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must never inherit the developer's real key or overrides."""
    for name in list(os.environ):
        if name.startswith((
            "OPENAI_", "TUTOR_", "COURSE_", "MAX_", "CORS_", "DEBUG_", "VOICE_", "TRUST_",
            "DATABASE_", "SESSION_", "COOKIE_", "ARGON2_", "AUTH_", "PROMPTS_", "CHAPTER_", "PACK_",
            "AUTHORING_", "DOCUMENT_", "TRANSCRIPTION_", "DISCUSSION_", "AI_",
        )):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def french_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The launch subjects offered in French only: the state before a subject is written in
    another language (spec 011 R1.7)."""
    from dataclasses import replace

    from app.domain import subject

    for key in ("mathematics", "sciences", "languages", "general"):
        monkeypatch.setitem(subject.SUBJECTS, key, replace(subject.SUBJECTS[key], languages=("fr",)))


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        session_secret="test-secret-long-enough",
        cookie_secure=False,
        database_url="sqlite://",
        # Fast hashing in tests; production uses the OWASP minimum.
        argon2_memory_kib=8192,
        argon2_time=1,
        _env_file=None,
    )


@pytest.fixture
def db_engine(tmp_path: Path) -> Engine:
    """One SQLite file per test, schema from the models. A file rather than
    `sqlite://`: an in-memory database shares one connection across threads, so a
    background authoring run and a request could interleave their transactions,
    which production (a connection per session) never does."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def repos(db_engine: Engine) -> Repositories:
    return Repositories.from_factory(make_session_factory(db_engine))


COURSE_ID = "c0" * 16
CHAPTER_ID = "5e" * 16
LESSON = {"course_id": COURSE_ID, "chapter_id": CHAPTER_ID}


def sign_in(
    app,
    email: str = "lea@example.be",
    name: str = "Léa",
    role: str = "student",
    lesson: bool = True,
    locale: str = "fr",
    language: str = "fr",
) -> tuple[dict, dict]:
    """Create a user directly, give the first student chapter 1 as a ready lesson
    at `LESSON` unless told otherwise, and open a session. Returns (user dict, auth
    headers). A bearer is used so the same-origin check does not apply to test
    POSTs. A second student gets the same content under fresh ids."""
    repos = app.state.repos
    stored = repos.users.by_email(email)
    if stored is None:
        user = repos.users.create(email, name, app.state.auth.hasher.hash("mot-de-passe-solide"), role, locale)  # type: ignore[arg-type]
    else:
        user = stored.user
    if lesson and role == "student":
        seed_lesson(app, user.id, language)
    token = app.state.auth.open_session(user)
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "locale": user.locale}, {
        "authorization": f"Bearer {token}"
    }


ENGLISH_LESSON_DIR = FIXTURES / "chapters" / "sequences_en"
DUTCH_LESSON_DIR = FIXTURES / "chapters" / "rijen_nl"


def seed_lesson(app, user_id: str, language: str = "fr") -> tuple[str, str]:
    """Chapter 1 as a ready chapter of « Mathématiques 5e » (or, for `en`, the English
    sequences fixture in « Mathematics Year 5 »). The fixed ids go to the first owner;
    anyone else gets generated ones."""
    from scripts.seed import COURSE_NAME, install_chapter

    repos = app.state.repos
    fixed = repos.courses.get_owned(user_id, COURSE_ID) is not None or _free(repos, COURSE_ID)
    extra: dict = {
        "en": {"directory": ENGLISH_LESSON_DIR, "course_name": "Mathematics Year 5", "language": "en"},
        "nl": {"directory": DUTCH_LESSON_DIR, "course_name": "Wiskunde 5e jaar", "language": "nl"},
    }.get(language, {"course_name": COURSE_NAME})
    return install_chapter(
        repos,
        app.state.prompts,
        app.state.settings,
        user_id=user_id,
        course_id=COURSE_ID if fixed else None,
        chapter_id=CHAPTER_ID if fixed else None,
        **extra,
    )


def _free(repos, course_id: str) -> bool:
    from sqlalchemy import select

    from app.db.models import CourseRow

    with repos.courses._factory() as s:
        return s.scalar(select(CourseRow.id).where(CourseRow.id == course_id)) is None


def seed_progress(app, user_id: str, chapter_id: str, done: list[str], active: str | None) -> None:
    from app.domain.progress import Progress

    app.state.repos.progress.save(user_id, chapter_id, Progress(done=frozenset(done), active=active))


def iter_api_routes(app):
    """Every `(path, APIRoute)` of the app. FastAPI 0.141 nests an included router behind one
    `_IncludedRouter`, so `app.routes` alone no longer lists them: walk into it."""
    from fastapi.routing import APIRoute

    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route.path, route
        elif hasattr(route, "original_router"):
            prefix = route.include_context.prefix
            for inner in route.original_router.routes:
                if isinstance(inner, APIRoute):
                    yield prefix + inner.path, inner


SAME_ORIGIN = {"sec-fetch-site": "same-origin"}


def http_client(app, headers: dict | None = None) -> AsyncClient:
    """A client on `app` as it is: nobody signed in unless `headers` carry a bearer."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers or {})


def occupy(repos: Repositories) -> None:
    """Give the instance an account, so it is not waiting for its first administrator (spec 013):
    until then registration is refused. The password is not a hash: nobody signs in as this one."""
    repos.users.create("idle@example.be", "Idle", "not-a-hash", role="parent")


def build_app(settings: Settings, engine: Engine, **overrides: object):
    """An app on an instance that already has an account (see `occupy`): registration is open. The
    tests of the first-run state build theirs with `create_app` and leave it empty."""
    app = create_app(settings.model_copy(update=overrides) if overrides else settings, engine=engine)
    occupy(app.state.repos)
    return app


def _client_for(
    app, anonymous: bool, email: str = "lea@example.be", locale: str = "fr", language: str = "fr"
) -> AsyncClient:
    user, headers = ({}, {}) if anonymous else sign_in(app, email=email, locale=locale, language=language)
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)
    ac.app = app  # type: ignore[attr-defined]
    ac.user = user  # type: ignore[attr-defined]
    # A second student gets the same chapter under fresh ids; the tests that need
    # them (another student's conversation) read them here rather than guessing.
    owned = app.state.repos.courses.list_for_user(user["id"]) if user else []
    ac.course_id = owned[0].course.id if owned else COURSE_ID  # type: ignore[attr-defined]
    ac.chapter_id = (  # type: ignore[attr-defined]
        owned[0].chapters[0].id if owned and owned[0].chapters else CHAPTER_ID
    )
    return ac


@pytest.fixture
async def client(settings: Settings, db_engine: Engine) -> AsyncIterator[AsyncClient]:
    """Signed in as a student by default (004). Use `anon_client` for the public view."""
    app = create_app(settings, engine=db_engine)
    async with _client_for(app, anonymous=False) as ac:
        yield ac


@pytest.fixture
async def anon_client(settings: Settings, db_engine: Engine) -> AsyncIterator[AsyncClient]:
    """Nobody signed in, on an instance that already has an account."""
    app = create_app(settings, engine=db_engine)
    occupy(app.state.repos)
    async with _client_for(app, anonymous=True) as ac:
        yield ac


@pytest.fixture
async def fresh_client(settings: Settings, db_engine: Engine) -> AsyncIterator[AsyncClient]:
    """Nobody signed in, on an instance with no account at all: waiting for its first administrator."""
    app = create_app(settings, engine=db_engine)
    async with _client_for(app, anonymous=True) as ac:
        yield ac


CARD: dict = {
    "kind": "explanation",
    "title": "Somme d'une SG",
    "blocks": [{"type": "text", "text": "Voici la formule."}],
}


def tool_call(name: str, args: dict, call_id: str = "c1") -> ToolCallRequested:
    return ToolCallRequested(call_id=call_id, name=name, arguments_json=json.dumps(args))


def sse_frames(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE response body into (event name, data) pairs."""
    out = []
    for block in text.split("\n\n"):
        if not block.startswith("event: "):
            continue
        name, data = block.split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


@pytest.fixture
def make_client(settings: Settings, db_engine: Engine):
    """An app whose LLM is a scripted fake, so tests never touch the network."""
    from app.api.deps import get_llm

    def _factory(
        llm: object,
        anonymous: bool = False,
        email: str = "lea@example.be",
        locale: str = "fr",
        language: str = "fr",
        **overrides: object,
    ) -> tuple[AsyncClient, object]:
        app = create_app(
            settings.model_copy(update=overrides) if overrides else settings, engine=db_engine
        )
        app.dependency_overrides[get_llm] = lambda: llm
        return _client_for(app, anonymous, email, locale, language), llm

    return _factory


def use_fake_authoring(app, script: list, delay_s: float = 0.0):
    """Replace the authoring runner's provider with a scripted fake, and read uploaded
    documents in a thread rather than a process pool. Returns the fake;
    `await app.state.authoring.wait_idle()` lets started runs finish."""
    from concurrent.futures import ThreadPoolExecutor

    from app.services.authoring.agent import AuthoringAgent
    from app.services.authoring.runner import AuthoringRunner
    from app.services.documents import DocumentService
    from tests.fixtures.fake_completion import FakeCompletion

    fake = FakeCompletion(script, delay_s=delay_s)
    agent = AuthoringAgent(fake, app.state.prompts, app.state.settings, app.state.hub)  # type: ignore[arg-type]
    app.state.authoring = AuthoringRunner(agent, app.state.repos, app.state.settings, app.state.hub)
    app.state.documents = DocumentService(app.state.settings, executor=ThreadPoolExecutor(1))
    return fake


@pytest.fixture
def make_voice_client(settings: Settings, db_engine: Engine):
    """An app whose Realtime provider is a fake, so minting never touches the network."""
    from app.api.deps import get_realtime

    def _factory(
        realtime: object, anonymous: bool = False, locale: str = "fr", **overrides: object
    ) -> AsyncClient:
        app = create_app(
            settings.model_copy(update=overrides) if overrides else settings, engine=db_engine
        )
        app.dependency_overrides[get_realtime] = lambda: realtime
        return _client_for(app, anonymous, locale=locale)

    return _factory


@pytest.fixture
def snapshot_declarations() -> str:
    """The board tool declarations as they were before the section tools existed.
    Delete the file and rerun to regenerate after an intended change."""
    from app.services.tools import registry

    path = FIXTURES / "board_declarations.json"
    if not path.exists():
        path.write_text(
            json.dumps(registry.declarations()[:2], ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    return path.read_text(encoding="utf-8")



@pytest.fixture
def make_dictation_client(settings: Settings, db_engine: Engine):
    """An app whose speech-to-text provider is a fake, so a recording never touches the network."""
    from app.api.deps import get_dictation_service
    from app.services.dictation import DictationService

    def _factory(
        transcriber: object, anonymous: bool = False, locale: str = "fr", **overrides: object
    ) -> AsyncClient:
        effective = settings.model_copy(update=overrides) if overrides else settings
        app = create_app(effective, engine=db_engine)
        app.dependency_overrides[get_dictation_service] = lambda: DictationService(
            transcriber, effective, app.state.hub  # type: ignore[arg-type]
        )
        return _client_for(app, anonymous, locale=locale)

    return _factory


@pytest.fixture
def make_work_client(settings: Settings, db_engine: Engine):
    """An app whose vision model is a scripted fake, so a photo never touches the network. The documents
    service, the prompts and the limits are the app's own."""
    from app.api.deps import get_work_reader
    from app.services.work_reading import WorkReader

    def _factory(
        completion: object, anonymous: bool = False, locale: str = "fr", **overrides: object
    ) -> AsyncClient:
        effective = settings.model_copy(update=overrides) if overrides else settings
        app = create_app(effective, engine=db_engine)
        app.dependency_overrides[get_work_reader] = lambda: WorkReader(
            completion, app.state.documents, app.state.prompts, effective, app.state.hub  # type: ignore[arg-type]
        )
        return _client_for(app, anonymous, locale=locale)

    return _factory
