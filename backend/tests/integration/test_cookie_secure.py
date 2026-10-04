"""Spec 013 R8: COOKIE_SECURE=true|false|auto, over HTTP and HTTPS, behind a trusted proxy or not."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import SAME_ORIGIN, build_app

REGISTER = {"email": "lea@example.be", "password": "mot-de-passe-solide", "name": "Léa"}


async def cookies_of(settings, db_engine, *, base_url="http://test", headers=None, **overrides) -> tuple[str, str]:
    """The Set-Cookie of a registration and of the logout that follows it."""
    app = build_app(settings, db_engine, **overrides)
    sent = {**SAME_ORIGIN, **(headers or {})}
    async with AsyncClient(transport=ASGITransport(app=app), base_url=base_url) as ac:
        registered = await ac.post("/api/auth/register", json=REGISTER, headers=sent)
        assert registered.status_code == 201
        out = await ac.post("/api/auth/logout", headers=sent)
    return registered.headers["set-cookie"], out.headers["set-cookie"]


@pytest.mark.parametrize("value, secure", [(True, True), (False, False)])
async def test_true_and_false_ignore_the_scheme(settings, db_engine, value, secure) -> None:
    issued, cleared = await cookies_of(settings, db_engine, base_url="https://test", cookie_secure=value)
    assert ("Secure" in issued) is secure and ("Secure" in cleared) is secure


@pytest.mark.parametrize("base_url, secure", [("http://test", False), ("https://test", True)])
async def test_auto_follows_the_scheme_of_the_request(settings, db_engine, base_url, secure) -> None:
    issued, cleared = await cookies_of(settings, db_engine, base_url=base_url, cookie_secure="auto")
    assert ("Secure" in issued) is secure and ("Secure" in cleared) is secure


async def test_auto_follows_a_trusted_proxy(settings, db_engine) -> None:
    issued, cleared = await cookies_of(
        settings, db_engine, headers={"x-forwarded-proto": "https"}, cookie_secure="auto", trust_proxy=True
    )
    assert "Secure" in issued and "Secure" in cleared


async def test_auto_takes_the_first_value_of_a_list(settings, db_engine) -> None:
    issued, _ = await cookies_of(
        settings, db_engine, headers={"x-forwarded-proto": "http, https"}, cookie_secure="auto", trust_proxy=True
    )
    assert "Secure" not in issued


async def test_auto_ignores_the_header_when_the_proxy_is_not_trusted(settings, db_engine) -> None:
    issued, cleared = await cookies_of(
        settings, db_engine, headers={"x-forwarded-proto": "https"}, cookie_secure="auto", trust_proxy=False
    )
    assert "Secure" not in issued and "Secure" not in cleared


async def test_the_cookie_stays_http_only_and_lax(settings, db_engine) -> None:
    issued, _ = await cookies_of(settings, db_engine, base_url="https://test", cookie_secure="auto")
    assert "HttpOnly" in issued and "samesite=lax" in issued.lower()
