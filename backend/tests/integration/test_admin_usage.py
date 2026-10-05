"""Spec 015 R6, §3.6: the administrator's routes over the usage ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import Engine

from app.domain.usage import UsageEntry
from app.main import create_app
from tests.conftest import http_client, sign_in

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
BASE = "/api/admin/usage"
MARKER = "course-name-marker-5521"


def entry(user_id: str, minutes: int = 0, **fields) -> UsageEntry:
    base = dict(
        created_at=T0 + timedelta(minutes=minutes), user_id=user_id, role="tutor", feature="tutor_turn",
        model="m1", provider="api.test", status="ok",
    )
    return UsageEntry(**{**base, **fields})


@pytest.fixture
def app(settings, db_engine: Engine):
    return create_app(settings, engine=db_engine)


@pytest.fixture
def world(app) -> dict:
    """Two students (one with a course named with a marker), an admin and some calls."""
    ana, _ = sign_in(app, email="ana@x.be", name="Ana", lesson=False)
    elo, _ = sign_in(app, email="elo@x.be", name="Élodie", lesson=False)
    root, _ = sign_in(app, email="root@x.be", name="Root", role="admin", lesson=False)
    repos = app.state.repos
    course = repos.courses.create(ana["id"], MARKER, "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    add = repos.ai_usage.add
    add(entry(ana["id"], 0, course_id=course.id, chapter_id=chapter.id, correlation_id="turn1", input_tokens=100, output_tokens=10, cost_usd=0.5))
    add(entry(ana["id"], 1, correlation_id="turn1", input_tokens=50, cached_tokens=20, output_tokens=5))
    add(entry(ana["id"], 2, role="authoring", feature="authoring", model="m2", provider="other.test", status="failed", error_code="provider_timeout"))
    add(entry(elo["id"], 3, input_tokens=500, output_tokens=9, cost_usd=1.0))
    add(entry(root["id"], 4, feature="ai_test", status="cancelled"))
    return {"ana": ana, "elo": elo, "root": root, "course": course.id, "chapter": chapter.id}


async def admin_client(app) -> AsyncClient:
    _, headers = sign_in(app, email="root@x.be", name="Root", role="admin", lesson=False)
    return http_client(app, headers)


ROUTES = ["/summary", "/users", "/users/someone", "/calls"]


@pytest.mark.parametrize("path", ROUTES)
async def test_only_an_admin_reads_the_ledger(app, world, path: str) -> None:
    for role in ("student", "parent"):
        _, headers = sign_in(app, email=f"{role}@x.be", name=role, role=role, lesson=False)
        async with http_client(app, headers) as client:
            r = await client.get(BASE + path)
        assert r.status_code == 403 and r.json()["code"] == "forbidden"
    async with http_client(app) as anon:
        assert (await anon.get(BASE + path)).status_code == 401


async def test_the_summary(app, world) -> None:
    async with await admin_client(app) as client:
        body = (await client.get(f"{BASE}/summary")).json()
    assert body["totals"] == {
        "calls": 5, "input_tokens": 650, "cached_tokens": 20, "output_tokens": 24, "reasoning_tokens": 0,
        "cost_usd": 1.5, "costed_calls": 2,
    }
    assert body["models"] == ["m1", "m2"]


async def test_a_period_without_any_reported_cost_says_so(app, world) -> None:
    since = (T0 + timedelta(minutes=1)).isoformat()
    until = (T0 + timedelta(minutes=3)).isoformat()
    async with await admin_client(app) as client:
        totals = (await client.get(f"{BASE}/summary", params={"since": since, "until": until})).json()["totals"]
    assert (totals["calls"], totals["cost_usd"], totals["costed_calls"]) == (2, None, 0)


async def test_per_user_totals_sort_and_page(app, world) -> None:
    async with await admin_client(app) as client:
        body = (await client.get(f"{BASE}/users")).json()
        assert body["total"] == 3
        assert body["users"][0]["name"] == "Ana" and body["users"][0]["calls"] == 3
        assert {u["name"] for u in body["users"]} == {"Ana", "Élodie", "Root"}  # ties are broken by id: not by name
        ana = body["users"][0]
        assert (ana["input_tokens"], ana["cached_tokens"], ana["cost_usd"], ana["costed_calls"], ana["enabled"]) == (150, 20, 0.5, 1, True)
        by_tokens = (await client.get(f"{BASE}/users", params={"order": "input_tokens"})).json()["users"]
        assert [u["name"] for u in by_tokens][:2] == ["Élodie", "Ana"]
        by_cost = (await client.get(f"{BASE}/users", params={"order": "cost", "direction": "asc"})).json()["users"]
        assert [u["name"] for u in by_cost] == ["Ana", "Élodie", "Root"]  # no reported cost last
        page = (await client.get(f"{BASE}/users", params={"order": "input_tokens", "limit": 1, "offset": 1})).json()
        assert page["total"] == 3 and [u["name"] for u in page["users"]] == ["Ana"]
        found = (await client.get(f"{BASE}/users", params={"q": "ÉLO"})).json()
        assert [u["name"] for u in found["users"]] == ["Élodie"] and found["total"] == 1
        assert (await client.get(f"{BASE}/users", params={"q": "%"})).json()["users"] == []


async def test_a_disabled_user_stays_listed(app, world) -> None:
    app.state.auth.set_enabled(type("A", (), {"id": world["root"]["id"], "role": "admin"})(), world["ana"]["id"], False)
    async with await admin_client(app) as client:
        users = (await client.get(f"{BASE}/users")).json()["users"]
    assert {u["name"]: u["enabled"] for u in users}["Ana"] is False


async def test_the_detail_of_a_user(app, world) -> None:
    async with await admin_client(app) as client:
        body = (await client.get(f"{BASE}/users/{world['ana']['id']}")).json()
    assert body["user"]["email"] == "ana@x.be" and body["totals"]["calls"] == 3
    assert [(r["role"], r["calls"]) for r in body["by_role"]] == [("authoring", 1), ("tutor", 2)]
    assert [(m["model"], m["provider"], m["calls"]) for m in body["by_model"]] == [
        ("m1", "api.test", 2), ("m2", "other.test", 1)]


async def test_a_user_with_no_calls_has_zeros_and_empty_lists(app, world) -> None:
    _, _ = sign_in(app, email="new@x.be", name="New", lesson=False)
    new = app.state.repos.users.by_email("new@x.be").user
    async with await admin_client(app) as client:
        body = (await client.get(f"{BASE}/users/{new.id}")).json()
    assert body["totals"]["calls"] == 0 and body["totals"]["cost_usd"] is None
    assert body["by_role"] == [] and body["by_model"] == []


async def test_an_unknown_user_is_404(app, world) -> None:
    async with await admin_client(app) as client:
        r = await client.get(f"{BASE}/users/nobody")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


async def test_the_calls_newest_first_with_every_filter(app, world) -> None:
    ana = world["ana"]["id"]
    async with await admin_client(app) as client:
        calls = lambda **p: client.get(f"{BASE}/calls", params=p)  # noqa: E731
        body = (await calls()).json()
        assert [c["feature"] for c in body["calls"]] == ["ai_test", "tutor_turn", "authoring", "tutor_turn", "tutor_turn"]
        assert body["has_more"] is False
        assert [c["id"] for c in (await calls(user_id=ana)).json()["calls"]] and len((await calls(user_id=ana)).json()["calls"]) == 3
        assert len((await calls(role="authoring")).json()["calls"]) == 1
        assert len((await calls(feature="ai_test")).json()["calls"]) == 1
        assert len((await calls(model="m2")).json()["calls"]) == 1
        assert len((await calls(status="failed")).json()["calls"]) == 1
        assert len((await calls(correlation_id="turn1")).json()["calls"]) == 2
        assert len((await calls(user_id=ana, status="ok", correlation_id="turn1")).json()["calls"]) == 2
        paged = (await calls(limit=2)).json()
        assert len(paged["calls"]) == 2 and paged["has_more"] is True
        last = (await calls(limit=2, offset=4)).json()
        assert len(last["calls"]) == 1 and last["has_more"] is False


async def test_a_call_row_holds_the_documented_fields(app, world) -> None:
    async with await admin_client(app) as client:
        calls = (await client.get(f"{BASE}/calls", params={"correlation_id": "turn1", "limit": 5})).json()["calls"]
    with_course = calls[-1]
    assert with_course["user_name"] == "Ana" and with_course["course_id"] == world["course"]
    assert (with_course["course_subject"], with_course["course_language"]) == ("mathematics", "fr")
    assert (with_course["input_tokens"], with_course["cost_usd"], with_course["ttft_ms"]) == (100, 0.5, None)
    assert calls[0]["cost_usd"] is None and calls[0]["cached_tokens"] == 20


async def test_no_course_or_chapter_name_is_ever_answered(app, world) -> None:
    async with await admin_client(app) as client:
        for path in ("/summary", "/users", f"/users/{world['ana']['id']}", "/calls"):
            r = await client.get(BASE + path)
            assert r.status_code == 200 and MARKER not in r.text


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/calls", {"role": "root"}),
        ("/calls", {"feature": "everything"}),
        ("/calls", {"status": "weird"}),
        ("/calls", {"limit": 0}),
        ("/calls", {"limit": 201}),
        ("/calls", {"offset": -1}),
        ("/calls", {"correlation_id": "x" * 33}),
        ("/calls", {"model": "x" * 201}),
        ("/users", {"order": "email"}),
        ("/users", {"direction": "up"}),
        ("/users", {"q": "x" * 101}),
        ("/summary", {"since": "2026-03-01T00:00:00"}),  # no offset
        ("/summary", {"since": "yesterday"}),
        ("/summary", {"since": "2026-03-02T00:00:00Z", "until": "2026-03-01T00:00:00Z"}),
        ("/summary", {"since": "2026-03-01T00:00:00Z", "until": "2026-03-01T00:00:00Z"}),
    ],
)
async def test_invalid_input_is_a_422_not_an_empty_list(app, world, path: str, params: dict) -> None:
    async with await admin_client(app) as client:
        r = await client.get(BASE + path, params=params)
    assert r.status_code == 422


async def test_an_offset_in_the_period_is_honoured(app, world) -> None:
    """14:02+02:00 is 12:02 UTC: it keeps the calls from minute 2 on."""
    async with await admin_client(app) as client:
        r = await client.get(f"{BASE}/summary", params={"since": "2026-03-01T14:02:00+02:00"})
    assert r.json()["totals"]["calls"] == 3
