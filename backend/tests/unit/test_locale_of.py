"""Spec 010 §4.1: the language of a request is the account's, else the browser's."""

from __future__ import annotations

from starlette.requests import Request

from app.api.deps import current_user
from app.api.locale import locale_of
from tests.conftest import occupy


def _request(accept_language: str | None = None, state_locale: str | None = None) -> Request:
    headers = [] if accept_language is None else [(b"accept-language", accept_language.encode())]
    request = Request({"type": "http", "headers": headers, "method": "GET", "path": "/"})
    if state_locale is not None:
        request.state.locale = state_locale
    return request


def test_the_account_wins_over_the_header() -> None:
    assert locale_of(_request("fr-BE", state_locale="en")) == "en"


def test_the_header_is_read_when_nobody_is_signed_in() -> None:
    assert locale_of(_request("en-GB")) == "en"
    assert locale_of(_request("de-DE")) == "fr"
    assert locale_of(_request()) == "fr"


def test_a_bad_state_value_is_ignored() -> None:
    assert locale_of(_request("en", state_locale="de")) == "en"


def test_current_user_leaves_the_language_on_the_request(repos, settings) -> None:
    from app.services.auth_service import AuthService, PasswordHasher

    auth = AuthService(repos, PasswordHasher(memory_kib=8192, time_cost=1, parallelism=1), settings)
    occupy(repos)
    user, token = auth.register("ann@example.be", "mot-de-passe-solide", "Ann", "en")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", f"Bearer {token}".encode()), (b"accept-language", b"fr")],
        }
    )
    assert current_user(request, auth) == user
    assert locale_of(request) == "en"


def test_the_scope_reader_serves_the_asgi_middleware() -> None:
    from app.api.locale import locale_of_scope

    assert locale_of_scope({"headers": [(b"accept-language", b"en-GB,en;q=0.9")]}) == "en"
    assert locale_of_scope({"headers": [(b"accept-language", b"nl-BE")]}) == "nl"
    assert locale_of_scope({"headers": [(b"accept-language", b"de")]}) == "fr"
    assert locale_of_scope({"headers": [(b"host", b"x")]}) == "fr"
