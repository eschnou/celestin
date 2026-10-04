"""The language of a request (spec 010 §4.1): the signed-in account's, else the browser's.

`deps.current_user` leaves the account's language on `request.state` when it resolves
the user, so nothing here looks the session up again. Whatever happens before or
without a session (sign-in, a 401, the middleware's refusals) is signed out by
definition and reads `Accept-Language`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from starlette.datastructures import Headers
from starlette.requests import Request

from app.domain.locale import Locale, is_locale, parse_accept_language


def locale_of(request: Request) -> Locale:
    locale = getattr(request.state, "locale", None)
    if is_locale(locale):
        return locale
    return parse_accept_language(request.headers.get("accept-language"))


def locale_of_scope(scope: Mapping[str, Any]) -> Locale:
    """For the pure ASGI middleware, which runs before routing and has no Request."""
    return parse_accept_language(Headers(scope=scope).get("accept-language"))
