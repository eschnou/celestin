"""Register, sign in, sign out, me (004 design 3.9)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    AnyUserDep,
    AuthServiceDep,
    SettingsDep,
    client_host,
    session_token,
)
from app.api.schemas.auth import (
    AuthConfigResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterPendingResponse,
    RegisterRequest,
    UpdateMeRequest,
    UserResponse,
)
from app.api.locale import locale_of
from app.api.session import clear_session_cookie, signed_in, user_dto
from app.domain.errors import RateLimited

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest, request: Request, settings: SettingsDep, auth: AuthServiceDep
) -> JSONResponse:
    limiter = request.app.state.register_limiter
    if not (
        limiter.allow(client_host(request, settings))
        and limiter.allow(f"email:{payload.email.lower()}")
    ):
        log.warning("auth_rate_limited", extra={"route": "register"})
        raise RateLimited()
    # The language the visitor was reading the page in becomes the account's (spec 010 R2.2).
    locale = locale_of(request)
    user, token = await run_in_threadpool(
        auth.register, payload.email, payload.password, payload.name, locale
    )
    if token is None:
        # Verification mode: the account waits for an admin; nothing is signed in.
        return JSONResponse(
            status_code=202,
            content=RegisterPendingResponse(user=user_dto(user)).model_dump(mode="json"),
        )
    return signed_in(user, token, request, settings, 201)


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config(auth: AuthServiceDep) -> AuthConfigResponse:
    """Public: the signed-out pages ask whether to offer registration."""
    # A database read until the first account exists, so not on the event loop.
    pending = await run_in_threadpool(auth.setup_required)
    return AuthConfigResponse(registration=auth.registration_mode, setup_required=pending)


@router.post("/login")
async def login(
    payload: LoginRequest, request: Request, settings: SettingsDep, auth: AuthServiceDep
) -> JSONResponse:
    limiter = request.app.state.login_limiter
    if not (limiter.allow(client_host(request, settings)) and limiter.allow(f"email:{payload.email.lower()}")):
        log.warning("auth_rate_limited", extra={"route": "login"})
        raise RateLimited()
    user, token = await run_in_threadpool(auth.login, payload.email, payload.password)
    return signed_in(user, token, request, settings, 200)


@router.post("/logout", status_code=204)
async def logout(request: Request, auth: AuthServiceDep, settings: SettingsDep) -> Response:
    """Public on purpose and idempotent: an expired or unknown cookie must still
    be cleared, or the browser keeps sending a dead one forever."""
    token = session_token(request)
    if token:
        await run_in_threadpool(auth.logout, token)
    response = Response(status_code=204)
    clear_session_cookie(response, request, settings)
    return response


@router.get("/me", response_model=UserResponse)
async def me(user: AnyUserDep) -> UserResponse:
    return UserResponse(user=user_dto(user))


@router.post("/password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest, request: Request, user: AnyUserDep, auth: AuthServiceDep
) -> Response:
    """The caller's own password, on proof of the current one. No id: nobody else's. Throttled
    like sign-in: a stolen session must not become a way to guess the password."""
    if not request.app.state.login_limiter.allow(f"password:{user.id}"):
        log.warning("auth_rate_limited", extra={"route": "password"})
        raise RateLimited()
    await run_in_threadpool(
        auth.change_password, user, payload.current_password, payload.new_password, session_token(request)
    )
    return Response(status_code=204)


@router.patch("/me", response_model=UserResponse)
async def update_me(payload: UpdateMeRequest, user: AnyUserDep, auth: AuthServiceDep) -> UserResponse:
    """Change the caller's own settings. There is no id: it cannot touch anyone else."""
    if payload.locale is not None:
        user = await run_in_threadpool(auth.set_locale, user.id, payload.locale)
    return UserResponse(user=user_dto(user))
