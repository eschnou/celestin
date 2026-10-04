"""Specs 013 R5–R6, 014 R1–R3, R8, R12: the admin's AI provider routes and the stored settings at startup."""

from __future__ import annotations

import json
import logging
import stat
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import Engine

from app.api.deps import get_llm
from app.main import create_app
from app.providers.base import Completed, ModelVisibility, ProbeResult, TextDelta
from tests.conftest import LESSON, SAME_ORIGIN, http_client, sign_in
from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.fake_probe import FakeProbe

KEY = "sk-live-0123456789abcd"
GROQ_KEY = "gsk_fake_0123456789abcd"
GROQ = "https://api.groq.com/openai/v1"
OPENAI = "https://api.openai.com/v1"
OSS = "openai/gpt-oss-120b"
URL = "/api/admin/ai"


def openai_body(key: str | None = KEY, **role_over: dict) -> dict:
    roles = {"tutor": {}, "authoring": {}, "transcription": {}, **role_over}
    return {"default": {"base_url": OPENAI, "api_key": key}, "roles": roles}


def groq_body(**over: dict) -> dict:
    body = {
        "default": {"base_url": GROQ, "api_key": GROQ_KEY},
        "roles": {
            "tutor": {"model": OSS},
            "authoring": {"model": OSS, "reasoning_effort": "low"},
            "transcription": {"model": "qwen/qwen3.8-27b"},
        },
    }
    body.update(over)
    return body


@pytest.fixture
def secrets_dir(tmp_path: Path) -> Path:
    return tmp_path / "secrets"


@pytest.fixture
def settings_keyless(settings, secrets_dir):
    """No key in the environment, a secrets directory: the instance the image starts."""
    return settings.model_copy(update={"openai_api_key": "", "secrets_dir": secrets_dir})


@pytest.fixture
def probe() -> FakeProbe:
    return FakeProbe()


@pytest.fixture
def app(settings_keyless, db_engine: Engine, probe: FakeProbe):
    return create_app(settings_keyless, engine=db_engine, probe=probe)


def client_as(app, role: str) -> AsyncClient:
    _, headers = sign_in(app, email=f"{role}@example.be", name=role.title(), role=role, lesson=role == "student")
    return http_client(app, headers)


@pytest.fixture
async def admin(app):
    async with client_as(app, "admin") as ac:
        yield ac


@pytest.mark.parametrize(
    "method, url, body",
    [
        ("GET", URL, None),
        ("PUT", URL, openai_body()),
        ("GET", f"{URL}/models", None),
        ("POST", f"{URL}/test", {"live": False}),
    ],
)
async def test_only_an_admin_may_touch_the_settings(app, method, url, body) -> None:
    for role in ("student", "parent"):
        async with client_as(app, role) as ac:
            r = await ac.request(method, url, json=body)
        assert r.status_code == 403 and r.json()["code"] == "forbidden"
    async with http_client(app) as anon:
        assert (await anon.request(method, url, json=body)).status_code == 401


async def test_the_old_key_routes_are_gone(admin) -> None:
    assert (await admin.get("/api/admin/openai-key")).status_code == 404


async def test_the_view_of_a_keyless_instance(admin) -> None:
    r = await admin.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["can_store"] is True and body["configured"] is False and body["voice_available"] is False
    assert body["default"]["base_url"] == {"value": OPENAI, "source": "default"}
    assert body["default"]["api_style"] == {"value": "responses", "source": "default"}
    assert body["default"]["key"] == {"source": "none", "last4": None, "unreadable": False}
    assert body["roles"]["tutor"]["model"] == {"value": "gpt-6.1-sol", "source": "default"}
    assert body["roles"]["tutor"]["reasoning_effort"] == {"value": None, "source": "default"}
    assert body["roles"]["authoring"]["reasoning_effort"] == {"value": "medium", "source": "default"}
    assert body["roles"]["voice"]["voice_transcription_model"]["value"] == "gpt-4o-mini-transcribe"
    assert body["roles"]["tutor"]["uses_default"] is True and body["roles"]["tutor"]["own_connection"] is None
    assert body["roles"]["tutor"]["resolved"] is False


async def test_saving_applies_without_echoing_a_key(admin, app, probe, secrets_dir, db_engine, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        put = await admin.put(URL, json=groq_body())
        got = await admin.get(URL)
        tested = await admin.post(f"{URL}/test", json={})
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["configured"] is True and body["voice_available"] is False  # Groq is not a Realtime server we know
    assert body["default"]["base_url"] == {"value": GROQ, "source": "stored"}
    assert body["default"]["key"] == {"source": "stored", "last4": GROQ_KEY[-4:], "unreadable": False}
    assert body["roles"]["tutor"]["model"] == {"value": OSS, "source": "stored"}
    assert body["roles"]["authoring"]["reasoning_effort"] == {"value": "low", "source": "stored"}
    assert got.json() == body
    ciphertext = json.loads(app.state.repos.app_settings.get("ai_settings"))["default"]["key"]["ct"]
    for response in (put, got, tested):
        assert GROQ_KEY not in response.text and ciphertext not in response.text
    assert GROQ_KEY not in caplog.text
    assert GROQ_KEY.encode() not in Path(db_engine.url.database).read_bytes()
    assert [c.host for c, _ in probe.calls][0] == "api.groq.com"
    assert stat.S_IMODE((secrets_dir / "encryption_key").stat().st_mode) == 0o600
    assert app.state.hub.config.tutor.model == OSS


async def test_health_follows_the_effective_models(admin, app) -> None:
    async with http_client(app) as anon:
        assert (await anon.get("/api/health")).json()["model"] is None
        await admin.put(URL, json=groq_body())
        body = (await anon.get("/api/health")).json()
    assert body["ai_configured"] is True and body["model"] == OSS and body["authoring_model"] == OSS
    assert body["voice"] is False and body["voice_model"] is None


async def test_a_saved_configuration_opens_the_gated_routes_without_a_restart(app, admin) -> None:
    llm = FakeLLM([[TextDelta("Bonjour"), Completed()]])
    app.dependency_overrides[get_llm] = lambda: llm
    async with client_as(app, "student") as student:
        refused = await student.post("/api/chat", json={**LESSON, "history": []})
        assert refused.status_code == 503 and refused.json()["code"] == "ai_not_configured"
        assert (await admin.put(URL, json=openai_body())).status_code == 200
        opened = await student.post("/api/chat", json={**LESSON, "history": []})
        assert opened.status_code == 200 and "Bonjour" in opened.text
        health = (await student.get("/api/health")).json()
        assert health["ai_configured"] is True and health["voice"] is True
        # Back to no key: the same route refuses again.
        assert (await admin.put(URL, json=openai_body(key=None) | {"default": {"base_url": OPENAI, "clear_key": True}})).status_code == 200
        assert (await student.post("/api/chat", json={**LESSON, "history": []})).status_code == 503


async def test_a_role_connection_round_trips(admin) -> None:
    body = groq_body()
    body["roles"]["transcription"] = {
        "model": "vision",
        "connection": {"base_url": "http://localhost:11434/v1", "api_style": "responses", "structured": "json"},
    }
    r = await admin.put(URL, json=body)
    assert r.status_code == 200
    role = r.json()["roles"]["transcription"]
    assert role["uses_default"] is False
    assert role["own_connection"]["base_url"] == {"value": "http://localhost:11434/v1", "source": "stored"}
    assert role["own_connection"]["structured"]["value"] == "json" and role["own_connection"]["key"]["source"] == "none"
    assert r.json()["roles"]["tutor"]["uses_default"] is True


async def test_a_rejected_key_is_a_422_and_changes_nothing(admin, probe) -> None:
    await admin.put(URL, json=groq_body())
    probe.result = ProbeResult("rejected")
    body = groq_body()
    body["default"] = {"base_url": GROQ, "api_key": "gsk_other_000000"}
    r = await admin.put(URL, json=body)
    assert r.status_code == 422 and r.json()["code"] == "ai_key_rejected"
    assert (await admin.get(URL)).json()["default"]["key"]["last4"] == GROQ_KEY[-4:]


async def test_an_unreachable_server_is_a_502_and_changes_nothing(admin, probe) -> None:
    probe.result = ProbeResult("unreachable")
    r = await admin.put(URL, json=groq_body())
    assert r.status_code == 502 and r.json()["code"] == "provider_unavailable"
    assert (await admin.get(URL)).json()["configured"] is False


@pytest.mark.parametrize(
    "default",
    [
        {"base_url": ""},
        {"base_url": "ftp://x.test"},
        {"base_url": "https://user:pw@x.test/v1"},
        {"base_url": GROQ, "api_key": "two words"},
        {"base_url": GROQ, "api_key": "x" * 300},
        {"base_url": GROQ, "api_key": "x" * 5000},
    ],
)
async def test_an_invalid_connection_is_a_422(admin, probe, default) -> None:
    r = await admin.put(URL, json={"default": default, "roles": {}})
    assert r.status_code == 422 and r.json()["code"] == "invalid_ai_settings"
    assert default.get("api_key", "-") not in r.text or "api_key" not in default  # a key is never echoed back
    assert probe.calls == []


async def test_an_invalid_model_effort_or_unknown_field_is_a_422(admin, probe) -> None:
    for body in (
        {"default": {"base_url": GROQ}, "roles": {"tutor": {"model": "x" * 2000}}},
        {"default": {"base_url": GROQ}, "roles": {"tutor": {"reasoning_effort": "extreme"}}},
        {"default": {"base_url": GROQ}, "roles": {"nobody": {}}},
        {"default": {"base_url": GROQ, "extra": 1}, "roles": {}},
    ):
        assert (await admin.put(URL, json=body)).status_code == 422
    assert probe.calls == []


async def test_environment_settings_are_read_only(settings, db_engine, secrets_dir, probe) -> None:
    env = settings.model_copy(update={"openai_api_key": "sk-env-98765432", "secrets_dir": secrets_dir, "openai_model": "env-model"})
    app = create_app(env, engine=db_engine, probe=probe)
    async with client_as(app, "admin") as admin:
        view = (await admin.get(URL)).json()
        assert view["default"]["key"] == {"source": "environment", "last4": "5432", "unreadable": False}
        assert view["roles"]["tutor"]["model"] == {"value": "env-model", "source": "environment"}
        r = await admin.put(URL, json=openai_body(key="sk-other-key", tutor={"model": "mine"}))
        assert r.status_code == 409 and r.json()["code"] == "setting_from_environment"
        assert (await admin.put(URL, json=openai_body(key=None, tutor={"model": "env-model"}))).status_code == 200
        assert (await admin.post(f"{URL}/test", json={})).status_code == 200
    assert probe.calls[-1][0].api_key == "sk-env-98765432"


async def test_an_instance_without_a_secrets_directory_cannot_store_a_key(settings, db_engine, probe) -> None:
    app = create_app(settings.model_copy(update={"openai_api_key": ""}), engine=db_engine, probe=probe)
    async with client_as(app, "admin") as admin:
        assert (await admin.get(URL)).json()["can_store"] is False
        r = await admin.put(URL, json=groq_body())
        assert r.status_code == 409 and r.json()["code"] == "storage_unavailable" and probe.calls == []
        keyless = {"default": {"base_url": "http://localhost:11434/v1"}, "roles": {"tutor": {"model": "qwen3:8b"}}}
        assert (await admin.put(URL, json=keyless)).json()["configured"] is True  # a local server needs no key


async def test_models_are_listed_from_the_slots_connection(admin, probe) -> None:
    await admin.put(URL, json=groq_body())
    probe.result = ProbeResult("ok", available=["a-model", "b-model"])
    r = await admin.get(f"{URL}/models", params={"slot": "tutor"})
    assert r.status_code == 200 and r.json() == {"status": "ok", "ids": ["a-model", "b-model"], "limited": False}
    assert probe.calls[-1][0].host == "api.groq.com"
    assert (await admin.get(f"{URL}/models", params={"slot": "nobody"})).status_code == 422


async def test_the_test_action_reports_each_role(admin, probe) -> None:
    await admin.put(URL, json=openai_body())
    probe.result = ProbeResult("ok", models=[ModelVisibility("gpt-6.1-sol", True), ModelVisibility("gpt-realtime-2.1", None)])
    r = await admin.post(f"{URL}/test", json={})
    assert r.status_code == 200
    assert r.json() == {
        "roles": [
            {"role": "tutor", "connection": "ok", "limited": False, "model_visible": True, "live": None},
            {"role": "authoring", "connection": "ok", "limited": False, "model_visible": True, "live": None},
            {"role": "transcription", "connection": "ok", "limited": False, "model_visible": True, "live": None},
            {"role": "voice", "connection": "ok", "limited": False, "model_visible": None, "live": None},
        ]
    }


async def test_the_test_action_without_a_configuration_is_the_needs_config_refusal(admin) -> None:
    r = await admin.post(f"{URL}/test", json={})
    assert r.status_code == 503 and r.json()["code"] == "ai_not_configured"


async def test_the_changes_are_throttled_per_admin(settings_keyless, db_engine, probe) -> None:
    app = create_app(settings_keyless.model_copy(update={"auth_attempts_per_window": 2}), engine=db_engine, probe=probe)
    async with client_as(app, "admin") as admin:
        statuses = [(await admin.put(URL, json=groq_body())).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]


async def test_a_cookie_session_from_another_site_is_refused(app, probe) -> None:
    sign_in(app, email="admin@example.be", name="Admin", role="admin", lesson=False)
    async with http_client(app) as ac:
        login = await ac.post("/api/auth/login", json={"email": "admin@example.be", "password": "mot-de-passe-solide"}, headers=SAME_ORIGIN)
        assert login.status_code == 200
        r = await ac.put(URL, json=groq_body(), headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403 and r.json()["code"] == "cross_origin" and probe.calls == []


# ------------------------------------------------------------------ at startup


async def stored_app(settings, db_engine, probe):
    """An app whose administrator has stored a Groq configuration, to be restarted over the same database."""
    app = create_app(settings, engine=db_engine, probe=probe)
    async with client_as(app, "admin") as admin:
        assert (await admin.put(URL, json=groq_body())).status_code == 200
    return app


async def test_a_stored_configuration_is_in_force_after_a_restart(settings_keyless, db_engine, probe) -> None:
    await stored_app(settings_keyless, db_engine, probe)
    second = create_app(settings_keyless, engine=db_engine, probe=probe)
    assert second.state.hub.configured is True and second.state.hub.config.tutor.model == OSS
    async with client_as(second, "admin") as admin:
        assert (await admin.get(URL)).json()["default"]["base_url"]["source"] == "stored"


async def test_the_environment_wins_at_startup(settings_keyless, db_engine, probe) -> None:
    await stored_app(settings_keyless, db_engine, probe)
    second = create_app(
        settings_keyless.model_copy(update={"openai_model": "env-model", "openai_api_key": "gsk-env-98765432"}),
        engine=db_engine, probe=probe,
    )
    config = second.state.hub.config
    assert config.tutor.model == "env-model" and config.authoring.model == OSS and config.tutor.connection.api_key == "gsk-env-98765432"


async def test_a_tampered_key_is_unreadable_not_a_crash(settings_keyless, db_engine, probe, caplog) -> None:
    first = create_app(settings_keyless, engine=db_engine, probe=probe)
    async with client_as(first, "admin") as admin:
        assert (await admin.put(URL, json=openai_body())).status_code == 200
    document = json.loads(first.state.repos.app_settings.get("ai_settings"))
    document["default"]["key"]["ct"] = document["default"]["key"]["ct"][:-4] + "AAAA"
    first.state.repos.app_settings.put("ai_settings", json.dumps(document), None)
    with caplog.at_level(logging.INFO):
        second = create_app(settings_keyless, engine=db_engine, probe=probe)
    assert second.state.hub.configured is False and KEY not in caplog.text
    async with client_as(second, "admin") as admin:
        assert (await admin.get(URL)).json()["default"]["key"]["unreadable"] is True


async def test_a_lost_encryption_key_makes_the_stored_key_unreadable_and_signs_nobody_out(
    settings_keyless, db_engine, probe, secrets_dir
) -> None:
    first = create_app(settings_keyless, engine=db_engine, probe=probe)
    async with client_as(first, "admin") as admin:
        assert (await admin.put(URL, json=openai_body())).status_code == 200
    _, headers = sign_in(first, email="lea@example.be", lesson=False)
    (secrets_dir / "encryption_key").unlink()
    second = create_app(settings_keyless, engine=db_engine, probe=probe)
    assert second.state.hub.configured is False
    async with http_client(second, headers) as ac:
        assert (await ac.get("/api/auth/me")).status_code == 200  # the session secret is another file


async def test_a_lost_session_secret_signs_everyone_out_and_keeps_the_stored_key(
    settings_keyless, db_engine, probe, secrets_dir
) -> None:
    keyless_and_secretless = settings_keyless.model_copy(update={"session_secret": ""})
    first = create_app(keyless_and_secretless, engine=db_engine, probe=probe)
    async with http_client(first) as ac:
        setup = await ac.post("/api/setup", json={"email": "ada@example.be", "name": "Ada", "password": "mot-de-passe-solide"}, headers=SAME_ORIGIN)
        assert setup.status_code == 201 and (await ac.get("/api/auth/me")).status_code == 200
        assert (await ac.put(URL, json=groq_body())).status_code == 200
        (secrets_dir / "session_secret").unlink()
        second = create_app(keyless_and_secretless, engine=db_engine, probe=probe)
        async with http_client(second) as ac2:
            ac2.cookies.update(ac.cookies)
            assert (await ac2.get("/api/auth/me")).status_code == 401  # the old cookie no longer verifies
    assert second.state.hub.configured is True  # the stored configuration is still readable


async def test_a_key_stored_by_spec_013_still_works_after_the_upgrade(settings_keyless, db_engine, probe, secrets_dir) -> None:
    """The legacy row alone, as a 013 instance left it: no `ai_settings`, nothing for the admin to do."""
    from app.secret_files import load_secrets
    from app.services.ai_resolution import LEGACY_CONTEXT
    from app.services.cipher import Cipher

    cipher = Cipher(load_secrets(settings_keyless).encryption_key)  # type: ignore[arg-type]
    row = json.dumps({"v": 1, "ct": cipher.encrypt(KEY, context=LEGACY_CONTEXT), "last4": KEY[-4:]})
    from app.db.base import make_session_factory
    from app.db.repositories import Repositories

    Repositories.from_factory(make_session_factory(db_engine)).app_settings.put("openai_api_key", row, None)
    app = create_app(settings_keyless, engine=db_engine, probe=probe)
    assert app.state.hub.configured is True and app.state.hub.config.tutor.connection.api_key == KEY
    async with client_as(app, "admin") as admin:
        view = (await admin.get(URL)).json()
    assert view["default"]["key"] == {"source": "stored", "last4": KEY[-4:], "unreadable": False}


# ------------------------------------------------------------------ the live checks


async def test_the_live_checks_run_when_asked_and_report_each_role(settings_keyless, db_engine, probe) -> None:
    from app.domain.errors import ProviderOutputInvalid
    from tests.fixtures.fake_clients import PassingFactory

    factory = PassingFactory(authoring=[ProviderOutputInvalid("no schema")])
    app = create_app(settings_keyless, engine=db_engine, probe=probe, client_factory=factory)
    async with client_as(app, "admin") as admin:
        assert (await admin.put(URL, json=openai_body())).status_code == 200
        plain = (await admin.post(f"{URL}/test", json={})).json()
        assert [r["live"] for r in plain["roles"]] == [None] * 4
        live = (await admin.post(f"{URL}/test", json={"live": True})).json()
    assert {r["role"]: r["live"] for r in live["roles"]} == {
        "tutor": {"status": "ok", "code": None},
        "authoring": {"status": "failed", "code": "schema_unsupported"},
        "transcription": {"status": "ok", "code": None},
        "voice": {"status": "ok", "code": None},
    }
    assert "Ping" not in str(live) and "no schema" not in str(live)  # nothing the provider said


async def test_the_live_checks_leave_voice_out_when_it_is_off(settings_keyless, db_engine, probe) -> None:
    from tests.fixtures.fake_clients import PassingFactory

    app = create_app(
        settings_keyless.model_copy(update={"voice_enabled": False}), engine=db_engine, probe=probe,
        client_factory=PassingFactory(),
    )
    async with client_as(app, "admin") as admin:
        assert (await admin.put(URL, json=openai_body())).status_code == 200
        live = (await admin.post(f"{URL}/test", json={"live": True})).json()
    assert [r["role"] for r in live["roles"]] == ["tutor", "authoring", "transcription"]


async def test_the_live_checks_are_throttled_like_everything_else_here(settings_keyless, db_engine, probe) -> None:
    from tests.fixtures.fake_clients import PassingFactory

    app = create_app(
        settings_keyless.model_copy(update={"auth_attempts_per_window": 2}), engine=db_engine, probe=probe,
        client_factory=PassingFactory(),
    )
    async with client_as(app, "admin") as admin:
        await admin.put(URL, json=openai_body())
        statuses = [(await admin.post(f"{URL}/test", json={"live": True})).status_code for _ in range(2)]
    assert statuses == [200, 429]
