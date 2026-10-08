from __future__ import annotations

import pytest
from httpx import AsyncClient

from pathlib import Path

from app.config import Settings
from app.main import create_app


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "model": "gpt-6.1-sol",
        "authoring_model": "gpt-6.1-sol",
        "prompts_unavailable": [],
        "subjects": ["mathematics", "sciences", "languages", "general"],
        "authoring_active": 0,
        "ai_configured": True,
        "voice": True,
        "voice_model": "gpt-realtime-2.1",
        "dictation": True,
    }


async def test_unknown_route_404(client: AsyncClient) -> None:
    assert (await client.get("/api/nope")).status_code == 404


async def test_request_id_header(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.headers["x-request-id"]


async def test_request_id_echoed(client: AsyncClient) -> None:
    r = await client.get("/api/health", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def _settings(**overrides: object) -> Settings:
    base = dict(
        openai_api_key="k",
        session_secret="test-secret-long-enough",
        database_url="sqlite://",
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_app_starts_without_a_key_and_says_so() -> None:
    """Spec 013 R7.1: a missing key is a state to configure in the settings screen, not a refusal."""
    app = create_app(_settings(openai_api_key=""), engine=_engine())
    assert app.state.hub.configured is False


def test_the_deprecated_call_timeout_is_ignored_with_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Spec 016 R3.3."""
    with caplog.at_level("WARNING"):
        create_app(_settings(authoring_call_timeout_s=300), engine=_engine())
        create_app(_settings(), engine=_engine())
    ignored = [r for r in caplog.records if r.getMessage() == "setting_ignored"]
    assert len(ignored) == 1 and ignored[0].setting == "AUTHORING_CALL_TIMEOUT_S"  # type: ignore[attr-defined]


def test_app_refuses_to_start_without_session_secret() -> None:
    from app.config import MissingSessionSecret

    with pytest.raises(MissingSessionSecret):
        create_app(_settings(session_secret="short"))


def test_app_refuses_to_start_on_an_outdated_schema() -> None:
    """004 NFR 4.4.1: an empty database names the command to run."""
    from app.domain.errors import SchemaOutdated

    with pytest.raises(SchemaOutdated) as exc:
        create_app(_settings())
    assert "alembic upgrade head" in str(exc.value)


def _engine():
    from app.db.base import Base, make_engine

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def _prompts_copy(tmp_path: Path) -> Path:
    import shutil

    copy = tmp_path / "prompts"
    shutil.copytree(Path(__file__).resolve().parents[2] / "prompts", copy)
    return copy


def test_app_refuses_to_start_without_a_subject_prompt(tmp_path: Path) -> None:
    from app.domain.errors import PromptInvalid

    prompts = _prompts_copy(tmp_path)
    (prompts / "subjects" / "sciences.fr.md").unlink()
    with pytest.raises(PromptInvalid, match="sciences.fr.md"):
        create_app(_settings(prompts_dir=prompts), engine=_engine())


async def test_health_reports_prompts_broken_after_startup(tmp_path: Path) -> None:
    """The operator's only diagnostic must not read healthy for a tutor that cannot
    teach a subject."""
    from httpx import ASGITransport, AsyncClient

    prompts = _prompts_copy(tmp_path)
    app = create_app(_settings(prompts_dir=prompts), engine=_engine())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.get("/api/health")).json()["status"] == "ok"
        (prompts / "templates" / "sciences.pack.fr.md").unlink()
        broken = (await ac.get("/api/health")).json()
    assert broken["status"] == "degraded"
    assert broken["prompts_unavailable"] == ["templates/sciences.pack.fr.md"]


async def test_shutdown_waits_for_the_ledger_writes_in_flight(settings: Settings, db_engine) -> None:
    """Spec 015: a row handed over just before the process stops is written, not lost."""
    import threading
    from datetime import UTC, datetime

    from app.db.repositories import Period
    from app.domain.usage import UsageEntry

    app = create_app(settings, engine=db_engine)
    release, written = threading.Event(), threading.Event()
    repo = app.state.repos.ai_usage
    real_add = repo.add

    def slow_add(entry: UsageEntry) -> None:
        release.wait(2)
        real_add(entry)
        written.set()

    app.state.usage_recorder._write = slow_add  # noqa: SLF001
    user = app.state.repos.users.create("a@x.be", "Ana", "h")
    async with app.router.lifespan_context(app):
        app.state.usage_recorder.record(UsageEntry(datetime.now(UTC), user.id, "tutor", "tutor_turn", "m", "h", "ok"))
        assert not written.is_set()
        release.set()
    assert written.is_set()
    assert app.state.repos.ai_usage.summary(Period()).totals.calls == 1
