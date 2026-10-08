from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.locale import locale_of
from app.api.middleware import BodyLimitMiddleware, SameOriginMiddleware
from app.api.ratelimit import SlidingWindow
from app.api.routes import admin, auth, chat, courses, dictation, discussion, health, setup, usage, voice, work
from app.config import Settings, get_settings
from app.db.base import make_engine, make_session_factory
from app.db.repositories import Repositories
from app.db.schema import check_schema
from app.providers.base import ConnectionProbe
from app.providers.hub import ClientFactory, ProviderHub, build_clients
from app.providers.recording import UsageRecorder
from app.providers.openai_probe import OpenAIConnectionProbe
from app.services.auth_service import AuthService, PasswordHasher
from app.services.authoring.agent import AuthoringAgent
from app.services.authoring.runner import AuthoringRunner
from app.services.documents import DocumentService
from app.services.chapters import CurriculumCache
from app.services.cipher import Cipher
from app.services.ai_settings import AiSettingsService
from app.services.prompts import PromptLibrary
from app.services.voice_service import VoiceSessionScopes
from app.domain.errors import TutorError
from app.logging_config import configure_logging, request_id_var
from app.secret_files import load_secrets


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = request_id
        return response


log = logging.getLogger(__name__)

PURGE_INTERVAL_S = 3600.0


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Expired sessions are swept at startup and hourly; the engine is disposed
    on shutdown. Tests drive the app without a lifespan and call purge directly."""

    async def sweep() -> None:
        while True:
            try:
                await asyncio.to_thread(app.state.auth.purge_expired)
                # Said at start and every hour until the first administrator exists (spec 013 R1.6).
                if await asyncio.to_thread(app.state.auth.setup_required):
                    log.warning("setup_pending", extra={"path": "/setup"})
            except Exception:  # noqa: BLE001 - a failed sweep must not kill the loop
                log.exception("sessions_purge_failed")
            await asyncio.sleep(PURGE_INTERVAL_S)

    # 005 design 3.9: runs left running by a previous process never finish.
    await asyncio.to_thread(app.state.authoring.fail_orphans)
    task = asyncio.create_task(sweep())
    try:
        yield
    finally:
        await app.state.authoring.shutdown()
        await app.state.usage_recorder.drain()
        app.state.documents.shutdown()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        app.state.engine.dispose()


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    *,
    probe: ConnectionProbe | None = None,
    client_factory: ClientFactory | None = None,
) -> FastAPI:
    """`engine` is for tests: an injected engine already carries the schema, so
    the migration check is skipped. Production always goes through the check. `probe` is the
    check of a provider connection (specs 013, 014) and `client_factory` the builder of the provider clients,
    both replaced by fakes in tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    # The session secret and the encryption key: from the environment or generated on first boot
    # (spec 013). Stops the start, naming the file, when one cannot be used.
    secrets = load_secrets(settings)
    if settings.authoring_call_timeout_s is not None:
        log.warning("setting_ignored", extra={"setting": "AUTHORING_CALL_TIMEOUT_S"})

    app = FastAPI(
        title="Professor Célestin",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    # Composition root: everything the routes resolve is built here, once.
    app.state.settings = settings
    if engine is None:
        engine = make_engine(settings.database_url)
        check_schema(engine)
    app.state.engine = engine
    app.state.repos = Repositories.from_factory(make_session_factory(engine))
    app.state.auth = AuthService(
        app.state.repos,
        PasswordHasher(settings.argon2_memory_kib, settings.argon2_time, settings.argon2_parallelism),
        settings,
        secret=secrets.session_secret,
    )
    app.state.login_limiter = SlidingWindow(settings.auth_attempts_per_window, settings.auth_window_s)
    app.state.register_limiter = SlidingWindow(settings.auth_attempts_per_window, settings.auth_window_s)
    # 005: every prompt and template of an available subject loads now, or startup
    # stops naming the file, rather than on the first learner message.
    app.state.prompts = PromptLibrary(settings.prompts_dir)
    app.state.prompts.check()
    app.state.curricula = CurriculumCache()
    # The AI clients live behind the hub, whose configuration can change at runtime (specs 013, 014): the
    # state holds its proxies, so nothing below captures a client that a new configuration would orphan.
    # Every client the hub builds records its calls into the usage ledger (spec 015).
    app.state.usage_recorder = UsageRecorder(app.state.repos.ai_usage.add)
    app.state.hub = hub = ProviderHub(settings, client_factory or build_clients, app.state.usage_recorder)
    # The configuration in force: the environment's, else what an admin stored (keys encrypted).
    app.state.ai_settings = AiSettingsService(
        app.state.repos.app_settings,
        Cipher(secrets.encryption_key) if secrets.encryption_key else None,
        hub,
        probe or OpenAIConnectionProbe(),
        settings,
    )
    app.state.ai_settings.load()
    app.state.llm = hub.llm
    app.state.realtime = hub.realtime
    app.state.voice_limiter = SlidingWindow(settings.voice_sessions_per_hour)
    # One report per session, and a session needs a minting: twice the mints an hour, to be generous.
    app.state.voice_usage_limiter = SlidingWindow(settings.voice_sessions_per_hour * 2)
    app.state.voice_scopes = VoiceSessionScopes()  # what each minted session was for (spec 015)
    app.state.dictation_limiter = SlidingWindow(settings.dictation_per_hour)
    app.state.work_limiter = SlidingWindow(settings.work_per_hour)
    app.state.authoring_llm = hub.authoring_llm
    app.state.authoring = AuthoringRunner(
        AuthoringAgent(app.state.authoring_llm, app.state.prompts, settings, hub), app.state.repos, settings, hub
    )
    app.state.documents = DocumentService(settings)  # the worker pool starts on first upload

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        BodyLimitMiddleware,
        max_bytes=settings.max_body_bytes,
        upload_max_bytes=settings.document_max_bytes,
        audio_max_bytes=settings.dictation_max_bytes,
        work_max_bytes=settings.work_max_bytes,
    )
    app.add_middleware(SameOriginMiddleware, allowed_origins=settings.cors_origins)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["content-type", "authorization"],
        )

    @app.exception_handler(TutorError)
    async def _tutor_error(request: Request, exc: TutorError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body(locale_of(request)))

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(setup.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(usage.router, prefix="/api")
    app.include_router(courses.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(discussion.router, prefix="/api")
    app.include_router(voice.router, prefix="/api")
    app.include_router(dictation.router, prefix="/api")
    app.include_router(work.router, prefix="/api")
    return app
