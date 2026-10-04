"""Spec 013 R1 to R3: the first-run state, `POST /api/setup`, registration while it lasts."""

from __future__ import annotations

import asyncio
import logging

import pytest
from httpx import AsyncClient

from app.main import create_app
from tests.conftest import SAME_ORIGIN, http_client, occupy

REGISTER = {"email": "lea@example.be", "password": "mot-de-passe-solide", "name": "Léa"}
SETUP = {"email": "Ada@Example.be", "password": "mot-de-passe-solide", "name": "Ada"}


async def test_a_fresh_instance_says_it_needs_setup(fresh_client: AsyncClient) -> None:
    r = await fresh_client.get("/api/auth/config")
    assert r.status_code == 200 and r.json() == {"registration": "open", "setup_required": True}


async def test_an_instance_with_an_account_does_not(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/api/auth/config")).json()["setup_required"] is False


async def test_setup_creates_the_admin_and_signs_them_in(fresh_client: AsyncClient) -> None:
    r = await fresh_client.post("/api/setup", json=SETUP, headers=SAME_ORIGIN)
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["email"] == "ada@example.be" and user["name"] == "Ada" and user["role"] == "admin"
    assert "celestin_session=" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    me = await fresh_client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["user"]["role"] == "admin"
    assert (await fresh_client.get("/api/auth/config")).json()["setup_required"] is False
    assert (await fresh_client.get("/api/admin/users")).status_code == 200  # an admin, truly


async def test_setup_stores_the_language_the_visitor_was_reading(fresh_client: AsyncClient) -> None:
    r = await fresh_client.post("/api/setup", json=SETUP, headers={**SAME_ORIGIN, "accept-language": "en-GB"})
    assert r.json()["user"]["locale"] == "en"


async def test_the_second_call_is_refused_for_good(fresh_client: AsyncClient) -> None:
    await fresh_client.post("/api/setup", json=SETUP, headers=SAME_ORIGIN)
    fresh_client.cookies.clear()
    other = {"email": "eve@example.be", "password": "mot-de-passe-solide", "name": "Eve"}
    r = await fresh_client.post("/api/setup", json=other, headers=SAME_ORIGIN)
    assert r.status_code == 409 and r.json()["code"] == "setup_done"
    assert "set-cookie" not in r.headers


async def test_two_simultaneous_calls_create_one_admin(settings, db_engine) -> None:
    app = create_app(settings, engine=db_engine)
    async with http_client(app) as ac:
        results = await asyncio.gather(
            ac.post("/api/setup", json=SETUP, headers=SAME_ORIGIN),
            ac.post(
                "/api/setup",
                json={**SETUP, "email": "eve@example.be", "name": "Eve"},
                headers=SAME_ORIGIN,
            ),
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    assert app.state.repos.users.counts().total == 1


async def test_a_weak_password_is_a_422_and_the_instance_stays_pending(fresh_client: AsyncClient) -> None:
    r = await fresh_client.post("/api/setup", json={**SETUP, "password": "court"}, headers=SAME_ORIGIN)
    assert r.status_code == 422 and r.json()["code"] == "weak_password"
    assert (await fresh_client.get("/api/auth/config")).json()["setup_required"] is True


async def test_setup_is_throttled_like_registration(settings, db_engine) -> None:
    app = create_app(settings.model_copy(update={"auth_attempts_per_window": 2}), engine=db_engine)
    async with http_client(app) as ac:
        bad = {**SETUP, "password": "court"}
        statuses = [(await ac.post("/api/setup", json=bad, headers=SAME_ORIGIN)).status_code for _ in range(3)]
    assert statuses == [422, 422, 429]


async def test_setup_refuses_a_cross_origin_post(fresh_client: AsyncClient) -> None:
    r = await fresh_client.post("/api/setup", json=SETUP, headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403 and r.json()["code"] == "cross_origin"
    assert (await fresh_client.get("/api/auth/config")).json()["setup_required"] is True


async def test_an_instance_with_users_but_no_admin_refuses_setup(anon_client: AsyncClient) -> None:
    r = await anon_client.post("/api/setup", json=SETUP, headers=SAME_ORIGIN)
    assert r.status_code == 409 and r.json()["code"] == "setup_done"


@pytest.mark.parametrize("mode", ["open", "closed", "verification"])
async def test_registration_is_refused_while_setup_is_pending(settings, db_engine, mode) -> None:
    app = create_app(settings.model_copy(update={"registration_mode": mode}), engine=db_engine)
    async with http_client(app) as ac:
        r = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert r.status_code == 409 and r.json()["code"] == "setup_required"
    assert app.state.repos.users.by_email("lea@example.be") is None


async def test_login_while_pending_is_the_usual_refusal(fresh_client: AsyncClient) -> None:
    r = await fresh_client.post(
        "/api/auth/login", json={"email": "ada@example.be", "password": "mot-de-passe-solide"}, headers=SAME_ORIGIN
    )
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"


async def test_registration_works_once_setup_is_done(settings, db_engine) -> None:
    app = create_app(settings, engine=db_engine)
    async with http_client(app) as ac:
        await ac.post("/api/setup", json=SETUP, headers=SAME_ORIGIN)
        ac.cookies.clear()
        r = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert r.status_code == 201 and r.json()["user"]["role"] == "student"


async def test_creating_an_admin_by_script_ends_the_pending_state(settings, db_engine) -> None:
    app = create_app(settings, engine=db_engine)
    assert app.state.auth.setup_required() is True
    occupy(app.state.repos)  # what scripts.create_admin and scripts.seed do: create a user directly
    assert app.state.auth.setup_required() is False


async def test_setup_pending_is_logged_until_the_first_account(settings, db_engine, caplog) -> None:
    app = create_app(settings, engine=db_engine)
    with caplog.at_level(logging.INFO):
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0.05)  # the sweep runs once at start
        pending = [r for r in caplog.records if r.message == "setup_pending"]
        assert len(pending) == 1 and pending[0].path == "/setup"  # type: ignore[attr-defined]
        caplog.clear()
        occupy(app.state.repos)
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0.05)
        assert not [r for r in caplog.records if r.message == "setup_pending"]


async def test_setup_completed_logs_the_id_and_nothing_personal(fresh_client: AsyncClient, caplog) -> None:
    with caplog.at_level(logging.INFO):
        r = await fresh_client.post("/api/setup", json=SETUP, headers=SAME_ORIGIN)
    record = next(rec for rec in caplog.records if rec.message == "setup_completed")
    assert record.user_id == r.json()["user"]["id"]  # type: ignore[attr-defined]
    assert "ada@example.be" not in caplog.text.lower() and "mot-de-passe" not in caplog.text
