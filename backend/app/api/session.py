"""The session cookie and the signed-in answer, shared by sign-in, registration and setup.

`COOKIE_SECURE=auto` (spec 013 R8) makes the cookie `Secure` exactly when the request reached
the application over HTTPS. Behind a proxy that is the proxy's word (`X-Forwarded-Proto`), believed
only when `TRUST_PROXY` is set: the same trust the client address gets (`deps.client_host`).
"""

from __future__ import annotations

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.api.deps import COOKIE_NAME
from app.api.schemas.auth import UserDTO, UserResponse
from app.config import Settings
from app.domain.user import User


def is_https(request: Request, settings: Settings) -> bool:
    scheme = request.url.scheme
    if settings.trust_proxy:
        proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        if proto in ("http", "https"):
            scheme = proto
    return scheme == "https"


def cookie_secure(request: Request, settings: Settings) -> bool:
    if settings.cookie_secure == "auto":
        return is_https(request, settings)
    return bool(settings.cookie_secure)


def set_session_cookie(response: Response, request: Request, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        # The server owns expiry (idle, then absolute); the cookie only has to
        # outlast the idle window so a session renewed by use is not dropped
        # by the browser first (R1.6).
        max_age=settings.session_absolute_days * 86400,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request, settings),
        path="/",
    )


def clear_session_cookie(response: Response, request: Request, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=cookie_secure(request, settings)
    )


def user_dto(user: User) -> UserDTO:
    return UserDTO(id=user.id, email=user.email, name=user.name, role=user.role, locale=user.locale)


def signed_in(user: User, token: str, request: Request, settings: Settings, status: int) -> JSONResponse:
    response = JSONResponse(
        status_code=status, content=UserResponse(user=user_dto(user)).model_dump(mode="json")
    )
    set_session_cookie(response, request, token, settings)
    return response
