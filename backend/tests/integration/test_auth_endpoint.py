"""004 design 3.1: register, login, logout, me, through the cookie and the bearer."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import SAME_ORIGIN, build_app

REGISTER = {"email": "Lea@Example.be", "password": "mot-de-passe-solide", "name": "Léa"}


async def test_register_sets_cookie_and_me_reads_it(anon_client: AsyncClient) -> None:
    r = await anon_client.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert r.status_code == 201
    body = r.json()["user"]
    assert body["email"] == "lea@example.be" and body["name"] == "Léa" and body["role"] == "student"
    cookie = r.headers["set-cookie"]
    assert "celestin_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie.replace("SameSite=Lax", "SameSite=lax")
    assert "Secure" not in cookie  # cookie_secure=False in tests
    me = await anon_client.get("/api/auth/me")  # httpx keeps the cookie jar
    assert me.status_code == 200 and me.json()["user"]["id"] == body["id"]


async def test_secure_flag_follows_settings(settings, db_engine) -> None:
    from httpx import ASGITransport

    app = build_app(settings, db_engine, cookie_secure=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert "Secure" in r.headers["set-cookie"]


async def test_me_without_session_is_401(anon_client: AsyncClient) -> None:
    r = await anon_client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "not_authenticated"


async def test_login_logout_cycle(anon_client: AsyncClient) -> None:
    await anon_client.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    anon_client.cookies.clear()
    bad = await anon_client.post(
        "/api/auth/login", json={"email": "lea@example.be", "password": "faux"}, headers=SAME_ORIGIN
    )
    assert bad.status_code == 401 and bad.json()["code"] == "invalid_credentials"
    unknown = await anon_client.post(
        "/api/auth/login", json={"email": "nobody@example.be", "password": "faux"}, headers=SAME_ORIGIN
    )
    assert unknown.status_code == 401 and unknown.json()["message"] == bad.json()["message"]
    ok = await anon_client.post(
        "/api/auth/login", json={"email": "lea@example.be", "password": "mot-de-passe-solide"}, headers=SAME_ORIGIN
    )
    assert ok.status_code == 200
    assert (await anon_client.get("/api/auth/me")).status_code == 200
    out = await anon_client.post("/api/auth/logout", headers=SAME_ORIGIN)
    assert out.status_code == 204 and "celestin_session=" in out.headers["set-cookie"]
    assert (await anon_client.get("/api/auth/me")).status_code == 401


async def test_bearer_works_too(anon_client: AsyncClient) -> None:
    r = await anon_client.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    token = r.cookies["celestin_session"]
    anon_client.cookies.clear()
    me = await anon_client.get("/api/auth/me", headers={"authorization": f"Bearer {token}"})
    assert me.status_code == 200


async def test_email_taken_and_weak_password(anon_client: AsyncClient) -> None:
    await anon_client.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    taken = await anon_client.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert taken.status_code == 409 and taken.json()["code"] == "email_taken"
    weak = await anon_client.post(
        "/api/auth/register", json={**REGISTER, "email": "x@example.be", "password": "court"}, headers=SAME_ORIGIN
    )
    assert weak.status_code == 422 and weak.json()["code"] == "weak_password"
    assert "6 caractères" in weak.json()["message"]


async def test_invalid_email_is_422(anon_client: AsyncClient) -> None:
    r = await anon_client.post("/api/auth/register", json={**REGISTER, "email": "pas-un-email"}, headers=SAME_ORIGIN)
    assert r.status_code == 422


async def test_login_rate_limited(settings, db_engine) -> None:
    from httpx import ASGITransport

    from app.main import create_app

    app = create_app(settings.model_copy(update={"auth_attempts_per_window": 2}), engine=db_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = {"email": "lea@example.be", "password": "faux"}
        codes = [
            (await ac.post("/api/auth/login", json=body, headers=SAME_ORIGIN)).status_code for _ in range(3)
        ]
    assert codes == [401, 401, 429]


async def test_cross_origin_register_is_refused(anon_client: AsyncClient) -> None:
    r = await anon_client.post(
        "/api/auth/register", json=REGISTER, headers={"origin": "https://evil.example", "sec-fetch-site": "cross-site"}
    )
    assert r.status_code == 403


async def test_passwords_never_logged(anon_client: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("DEBUG"):
        await anon_client.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert "mot-de-passe-solide" not in caplog.text
    assert "lea@example.be" not in caplog.text


async def test_logout_clears_a_dead_cookie(anon_client: AsyncClient) -> None:
    """004 §5: an expired or unknown cookie must still be cleared, or the browser
    keeps sending it forever."""
    r = await anon_client.post(
        "/api/auth/logout", headers={**SAME_ORIGIN, "cookie": "celestin_session=not-a-real-token"}
    )
    assert r.status_code == 204
    assert "celestin_session=" in r.headers["set-cookie"]


async def test_cookie_outlives_the_idle_window(anon_client: AsyncClient) -> None:
    """R1.6: a session renewed by use must not be dropped by the browser first."""
    r = await anon_client.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    settings = anon_client.app.state.settings  # type: ignore[attr-defined]
    assert f"Max-Age={settings.session_absolute_days * 86400}" in r.headers["set-cookie"]
    assert settings.session_absolute_days > settings.session_idle_days


async def test_register_rate_limited_per_email(settings, db_engine) -> None:
    """R1.8: a distributed guess is still bounded per address."""
    from httpx import ASGITransport

    app = build_app(settings, db_engine, auth_attempts_per_window=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        first = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
        second = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
        third = await ac.post("/api/auth/register", json=REGISTER, headers=SAME_ORIGIN)
    assert (first.status_code, second.status_code) == (201, 409)
    assert third.status_code == 429


async def test_duplicate_registration_loses_to_the_constraint(repos) -> None:
    """The check-then-insert race closes on the unique index (004 §5)."""
    from app.domain.errors import EmailTaken

    repos.users.create("lea@example.be", "Léa", "hash")
    with pytest.raises(EmailTaken):
        repos.users.create("lea@example.be", "Léa", "hash")


async def test_failed_login_is_logged_without_the_address(
    anon_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        await anon_client.post(
            "/api/auth/login", json={"email": "nobody@example.be", "password": "faux"}, headers=SAME_ORIGIN
        )
    record = next(r for r in caplog.records if r.getMessage() == "auth_login_failed")
    assert record.reason == "unknown_email"  # type: ignore[attr-defined]
    assert "nobody@example.be" not in caplog.text


# --- the interface language (spec 010 R2) --------------------------------------------


async def test_register_stores_the_language_the_visitor_was_reading(anon_client: AsyncClient) -> None:
    english = await anon_client.post(
        "/api/auth/register",
        json={**REGISTER, "email": "ann@example.be"},
        headers={**SAME_ORIGIN, "accept-language": "en-GB,en;q=0.9"},
    )
    assert english.status_code == 201 and english.json()["user"]["locale"] == "en"
    anon_client.cookies.clear()
    french = await anon_client.post(
        "/api/auth/register",
        json={**REGISTER, "email": "lea@example.be"},
        headers={**SAME_ORIGIN, "accept-language": "fr-BE,fr;q=0.9"},
    )
    assert french.json()["user"]["locale"] == "fr"
    anon_client.cookies.clear()
    silent = await anon_client.post(
        "/api/auth/register", json={**REGISTER, "email": "tim@example.be"}, headers=SAME_ORIGIN
    )
    assert silent.json()["user"]["locale"] == "fr"
    anon_client.cookies.clear()
    unsupported = await anon_client.post(
        "/api/auth/register",
        json={**REGISTER, "email": "jan@example.be"},
        headers={**SAME_ORIGIN, "accept-language": "de-DE,de;q=0.9"},
    )
    assert unsupported.json()["user"]["locale"] == "fr"
    anon_client.cookies.clear()
    flemish = await anon_client.post(  # spec 017 R1.3
        "/api/auth/register",
        json={**REGISTER, "email": "ward@example.be"},
        headers={**SAME_ORIGIN, "accept-language": "nl-BE,nl;q=0.9,fr;q=0.5"},
    )
    assert flemish.json()["user"]["locale"] == "nl"


async def test_sign_in_and_me_return_the_stored_language(anon_client: AsyncClient) -> None:
    await anon_client.post(
        "/api/auth/register", json=REGISTER, headers={**SAME_ORIGIN, "accept-language": "en"}
    )
    anon_client.cookies.clear()
    # The account's language wins over whatever the browser says now.
    login = await anon_client.post(
        "/api/auth/login",
        json={"email": "lea@example.be", "password": REGISTER["password"]},
        headers={**SAME_ORIGIN, "accept-language": "fr-BE"},
    )
    assert login.json()["user"]["locale"] == "en"
    me = await anon_client.get("/api/auth/me")
    assert me.json()["user"]["locale"] == "en"


async def test_patch_me_changes_the_language(client: AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).json()["user"]["locale"] == "fr"
    r = await client.patch("/api/auth/me", json={"locale": "en"})
    assert r.status_code == 200 and r.json()["user"]["locale"] == "en"
    assert (await client.get("/api/auth/me")).json()["user"]["locale"] == "en"
    r = await client.patch("/api/auth/me", json={"locale": "nl"})
    assert r.status_code == 200 and r.json()["user"]["locale"] == "nl"
    r = await client.patch("/api/auth/me", json={"locale": "fr"})
    assert r.json()["user"]["locale"] == "fr"


async def test_patch_me_with_nothing_changes_nothing(client: AsyncClient) -> None:
    r = await client.patch("/api/auth/me", json={})
    assert r.status_code == 200 and r.json()["user"]["locale"] == "fr"


async def test_patch_me_refuses_what_it_does_not_know(client: AsyncClient) -> None:
    unsupported = await client.patch("/api/auth/me", json={"locale": "de"})
    assert unsupported.status_code == 422
    # Nor can a body name another account or another field.
    other = await client.patch("/api/auth/me", json={"locale": "en", "id": "someone-else"})
    assert other.status_code == 422
    assert (await client.patch("/api/auth/me", json={"name": "Hacker"})).status_code == 422
    assert (await client.get("/api/auth/me")).json()["user"]["locale"] == "fr"


async def test_patch_me_needs_a_session(anon_client: AsyncClient) -> None:
    r = await anon_client.patch("/api/auth/me", json={"locale": "en"}, headers=SAME_ORIGIN)
    assert r.status_code == 401 and r.json()["code"] == "not_authenticated"


async def test_patch_me_acts_on_the_callers_account_only(client: AsyncClient) -> None:
    from tests.conftest import sign_in

    _, other_headers = sign_in(client.app, email="other@example.be", name="Other")  # type: ignore[attr-defined]
    await client.patch("/api/auth/me", json={"locale": "en"})
    other = await client.get("/api/auth/me", headers=other_headers)
    assert other.json()["user"]["locale"] == "fr"
