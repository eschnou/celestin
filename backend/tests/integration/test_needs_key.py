"""Specs 013 R7, 014 R8.4: an instance with no AI provider configured starts, and refuses what needs it."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.api.deps import get_llm, get_realtime, require_ai
from app.main import create_app
from app.providers.base import Completed, TextDelta
from app.providers.hub import Clients, ProviderHub
from app.services.ai_settings import load_ai_config
from app.services.authoring.agent import AuthoringAgent
from app.services.authoring.runner import AuthoringRunner
from app.services.documents import DocumentService
from tests.conftest import CHAPTER_ID, COURSE_ID, LESSON, _client_for, http_client, iter_api_routes, sign_in
from tests.fixtures.fake_completion import FakeCompletion
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM
from tests.fixtures.fake_realtime import ExplodingRealtime
from tests.integration.test_courses_endpoint import AUTHOR, READ, SOURCE, photos

COURSE = "{course_id}"
CHAPTER = "{chapter_id}"
CHAPTER_URL = f"/api/courses/{COURSE}/chapters/{CHAPTER}"
CH = CHAPTER_URL.format(course_id=COURSE_ID, chapter_id=CHAPTER_ID)

# The nine routes that call the provider (spec 013 design 3.8): method, path template, request arguments.
# One table: the requests are made against the template filled with the fixture's ids, and the set of
# gated routes is read from the same templates.
AI_ROUTES = [
    ("POST", "/api/chat", {"json": {**LESSON, "history": []}}),
    ("POST", "/api/discussion/turn", {"json": {**LESSON, "conversation_id": "a" * 32, "message": "salut"}}),
    ("POST", "/api/voice/session", {"json": {**LESSON, "history": []}}),
    ("POST", f"/api/courses/{COURSE}/work", {"files": [("photo", ("w.jpg", b"x", "image/jpeg"))]}),
    ("POST", "/api/dictation", {"files": [("audio", ("d.webm", b"x", "audio/webm"))], "data": {"language": "fr"}}),
    ("POST", f"/api/courses/{COURSE}/chapters", {"files": photos()}),
    ("PUT", f"{CHAPTER_URL}/document", {"files": photos()}),
    ("PUT", f"{CHAPTER_URL}/source", {"json": {"source_text": SOURCE}}),
    ("POST", f"{CHAPTER_URL}/retry", {}),
]
GATED = {(method, path) for method, path, _ in AI_ROUTES}


def filled(path: str) -> str:
    return path.format(course_id=COURSE_ID, chapter_id=CHAPTER_ID)


@pytest.fixture
def no_key(settings):
    return settings.model_copy(update={"openai_api_key": ""})


def build(no_key, db_engine, locale: str = "fr"):
    """A signed-in student on an app with no key, whose provider fakes fail the test if they are called."""
    app = create_app(no_key, engine=db_engine)
    app.dependency_overrides[get_llm] = lambda: ExplodingLLM(AssertionError("the provider was called"))
    app.dependency_overrides[get_realtime] = lambda: ExplodingRealtime(AssertionError("the provider was called"))
    # One account per language: a user keeps the language they were created with.
    return _client_for(app, anonymous=False, locale=locale, email=f"{locale}@example.be")


def test_an_app_with_no_key_starts_unconfigured(no_key, db_engine) -> None:
    app = create_app(no_key, engine=db_engine)
    assert app.state.hub.configured is False


def test_an_app_with_a_key_is_configured(settings, db_engine) -> None:
    assert create_app(settings, engine=db_engine).state.hub.configured is True


def test_a_key_of_only_spaces_is_no_key(settings, db_engine) -> None:
    assert create_app(settings.model_copy(update={"openai_api_key": "   "}), engine=db_engine).state.hub.configured is False


@pytest.mark.parametrize("locale, fragment", [("fr", "pas encore configuré"), ("en", "isn't set up yet")])
@pytest.mark.parametrize("method, path, kwargs", AI_ROUTES, ids=[f"{m} {p.split('/api')[1]}" for m, p, _ in AI_ROUTES])
async def test_a_route_that_needs_the_provider_is_refused_in_both_languages(
    no_key, db_engine, method, path, kwargs, locale, fragment
) -> None:
    async with build(no_key, db_engine, locale) as client:
        r = await client.request(method, filled(path), **kwargs)
    assert r.status_code == 503 and r.json()["code"] == "ai_not_configured", r.text
    assert fragment in r.json()["message"]


async def test_nothing_is_stored_by_a_refused_upload(no_key, db_engine) -> None:
    client = build(no_key, db_engine)
    before = client.app.state.repos.courses.list_for_user(client.user["id"])[0]
    async with client:
        r = await client.post(f"/api/courses/{client.course_id}/chapters", files=photos())
    assert r.status_code == 503
    after = client.app.state.repos.courses.list_for_user(client.user["id"])[0]
    assert len(after.chapters) == len(before.chapters)


async def test_auth_comes_before_the_refusal(no_key, db_engine) -> None:
    app = create_app(no_key, engine=db_engine)
    _, parent = sign_in(app, email="p@example.be", name="Parent", role="parent", lesson=False)
    _, admin = sign_in(app, email="admin@example.be", name="Admin", role="admin", lesson=False)
    async with http_client(app) as anon:
        assert (await anon.post("/api/chat", json={**LESSON, "history": []})).status_code == 401
        assert (await anon.post("/api/chat", json={**LESSON, "history": []}, headers=admin)).status_code == 403
        assert (await anon.post("/api/chat", json={**LESSON, "history": []}, headers=parent)).status_code == 403


async def test_what_does_not_call_the_provider_still_works(no_key, db_engine) -> None:
    client = build(no_key, db_engine)
    async with client:
        assert (await client.get("/api/auth/me")).status_code == 200
        assert (await client.get("/api/courses")).status_code == 200
        assert (await client.get(f"/api/courses/{client.course_id}")).status_code == 200
        assert (await client.get(f"{CH}")).status_code == 200
        assert (await client.get(f"{CH}/content")).status_code == 200
        assert (await client.delete(f"{CH}/progress")).status_code == 204
        assert (await client.get("/api/health")).status_code == 200


async def test_health_reports_the_state(no_key, settings, db_engine) -> None:
    async with build(no_key, db_engine) as client:
        body = (await client.get("/api/health")).json()
    assert body["ai_configured"] is False and body["voice"] is False
    app2 = create_app(settings, engine=db_engine)
    async with _client_for(app2, anonymous=True) as ac:
        body = (await ac.get("/api/health")).json()
    assert body["ai_configured"] is True and body["voice"] is True


async def test_voice_stays_off_when_it_is_disabled_even_with_a_key(settings, db_engine) -> None:
    app = create_app(settings.model_copy(update={"voice_enabled": False}), engine=db_engine)
    async with _client_for(app, anonymous=True) as ac:
        body = (await ac.get("/api/health")).json()
    assert body["ai_configured"] is True and body["voice"] is False


async def test_a_configuration_applied_later_opens_the_same_routes_without_a_restart(no_key, settings, db_engine) -> None:
    app = create_app(no_key, engine=db_engine)
    llm = FakeLLM([[TextDelta("Bonjour"), Completed()]])
    app.dependency_overrides[get_llm] = lambda: llm
    async with _client_for(app, anonymous=False) as client:
        refused = await client.post("/api/chat", json={**LESSON, "history": []})
        assert refused.status_code == 503 and llm.rounds_used == 0
        app.state.hub.apply(load_ai_config(settings))
        opened = await client.post("/api/chat", json={**LESSON, "history": []})
    assert opened.status_code == 200 and "Bonjour" in opened.text and llm.rounds_used == 1


def _has_require_ai(dependant) -> bool:
    return dependant.call is require_ai or any(_has_require_ai(sub) for sub in dependant.dependencies)


def test_exactly_the_nine_routes_are_gated(settings, db_engine) -> None:
    app = create_app(settings, engine=db_engine)
    gated = {(m, path) for path, route in iter_api_routes(app) if _has_require_ai(route.dependant) for m in route.methods}
    assert gated == GATED


async def test_a_key_removed_during_a_run_fails_it_retryably(settings, db_engine) -> None:
    """The first provider call (reading the pages) takes the key away; the next resolves no client."""
    app = create_app(settings, engine=db_engine)
    hub: ProviderHub  # the hub below replaces the app's: its factory hands out the scripted authoring client

    class DropsTheKey(FakeCompletion):
        async def complete(self, **kwargs):  # noqa: ANN003
            result = await super().complete(**kwargs)
            if len(self.calls) == 1:
                hub.apply(None)
            return result

    fake = DropsTheKey([READ, *AUTHOR])
    config = load_ai_config(settings)
    app.state.hub = hub = ProviderHub(
        settings, lambda s, c: Clients(config=c, tutor=None, authoring=fake, transcription=fake, realtime=None)  # type: ignore[arg-type]
    )
    hub.apply(config)
    app.state.authoring = AuthoringRunner(
        AuthoringAgent(hub.authoring_llm, app.state.prompts, settings, hub), app.state.repos, settings, hub
    )
    app.state.documents = DocumentService(settings, executor=ThreadPoolExecutor(1))
    async with _client_for(app, anonymous=False) as client:
        course_id = (await client.post("/api/courses", json={"name": "Maths bis", "subject": "mathematics"})).json()["id"]
        chapter_id = (await client.post(f"/api/courses/{course_id}/chapters", files=photos())).json()["id"]
        await app.state.authoring.wait_idle()
        (row,) = (await client.get(f"/api/courses/{course_id}")).json()["chapters"]
        assert row["authoring_state"] == "failed" and not row["ready"]
        assert hub.configured is False
        hub.apply(config)
        retried = await client.post(f"/api/courses/{course_id}/chapters/{chapter_id}/retry")
        assert retried.status_code == 202
        await app.state.authoring.wait_idle()
        (row,) = (await client.get(f"/api/courses/{course_id}")).json()["chapters"]
        assert row["ready"], row
