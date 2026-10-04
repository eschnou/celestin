"""The first administrator (spec 013): `POST /api/setup`, public, and only until an account exists.

The first visitor of a fresh instance wins, on purpose (a small self-hosted project: convenience over a
setup token). The route cannot add an admin to an instance that has any account, and nothing else creates
one apart from `scripts/create_admin.py`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import AuthServiceDep, SettingsDep, client_host
from app.api.locale import locale_of
from app.api.schemas.auth import SetupRequest
from app.api.session import signed_in
from app.domain.errors import RateLimited

log = logging.getLogger(__name__)
router = APIRouter(prefix="/setup")


@router.post("", status_code=201)
async def setup(
    payload: SetupRequest, request: Request, settings: SettingsDep, auth: AuthServiceDep
) -> JSONResponse:
    # The registration limiter, as for registration: the same guess budget per address and email.
    limiter = request.app.state.register_limiter
    if not (
        limiter.allow(client_host(request, settings))
        and limiter.allow(f"email:{payload.email.lower()}")
    ):
        log.warning("auth_rate_limited", extra={"route": "setup"})
        raise RateLimited()
    user, token = await run_in_threadpool(
        auth.setup, payload.email, payload.password, payload.name, locale_of(request)
    )
    return signed_in(user, token, request, settings, 201)
