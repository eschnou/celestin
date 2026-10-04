"""The admin dashboard's routes (spec 012): list accounts, enable or disable one, reset
a password. Every route admits `admin` only. A user id here is whatever the admin
names; there is no ownership, which is the point of the role."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import AdminDep, AiSettingsDep, AuthServiceDep, ReposDep
from app.api.schemas.admin import (
    AdminUserDTO,
    ResetPasswordResponse,
    UpdateUserRequest,
    UserCountsDTO,
    UserEnvelope,
    UserListResponse,
    UserStatus,
)
from app.api.schemas.ai import (
    AiSettingsDTO,
    AiTestDTO,
    ModelListingDTO,
    SaveAiSettingsRequest,
    TestRequest,
    settings_view,
)
from app.db.repositories import Repositories, UserListing
from app.services.ai_resolution import Slot
from app.domain.errors import NotFound, RateLimited

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin")


def _dto(listing: UserListing) -> AdminUserDTO:
    user = listing.user
    return AdminUserDTO(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        locale=user.locale,
        enabled=user.enabled,
        created_at=listing.created_at,
        last_seen_at=listing.last_seen_at,
    )


def _one(repos: Repositories, user_id: str) -> AdminUserDTO:
    listing, _ = repos.users.list_users(user_id=user_id, limit=1)
    if not listing:
        raise NotFound()
    return _dto(listing[0])


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _admin: AdminDep,
    repos: ReposDep,
    auth: AuthServiceDep,
    q: Annotated[str, Query(max_length=100)] = "",
    status: UserStatus = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserListResponse:
    enabled = {"all": None, "enabled": True, "disabled": False}[status]

    def load() -> UserListResponse:
        listing, total = repos.users.list_users(query=q, enabled=enabled, limit=limit, offset=offset)
        counts = repos.users.counts()
        return UserListResponse(
            users=[_dto(item) for item in listing],
            total=total,
            counts=UserCountsDTO(total=counts.total, enabled=counts.enabled, disabled=counts.disabled),
            registration_mode=auth.registration_mode,
        )

    return await run_in_threadpool(load)


@router.patch("/users/{user_id}", response_model=UserEnvelope)
async def update_user(
    user_id: str, payload: UpdateUserRequest, admin: AdminDep, repos: ReposDep, auth: AuthServiceDep
) -> UserEnvelope:
    await run_in_threadpool(auth.set_enabled, admin, user_id, payload.enabled)
    return UserEnvelope(user=await run_in_threadpool(_one, repos, user_id))


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    user_id: str, admin: AdminDep, repos: ReposDep, auth: AuthServiceDep
) -> JSONResponse:
    password = await run_in_threadpool(auth.reset_password, admin, user_id)
    body = ResetPasswordResponse(user=await run_in_threadpool(_one, repos, user_id), password=password)
    # A secret: nothing may keep a copy of this answer.
    return JSONResponse(content=body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- the AI provider (specs 013 R5, 014 §3.8)


def _throttle(request: Request, admin_id: str) -> None:
    """A stolen admin session must not become a way to try keys or to hammer a provider: the same
    limiter and window as sign-in and the password change."""
    if not request.app.state.login_limiter.allow(f"ai-settings:{admin_id}"):
        log.warning("auth_rate_limited", extra={"route": "ai-settings"})
        raise RateLimited()


@router.get("/ai", response_model=AiSettingsDTO)
async def get_ai_settings(_admin: AdminDep, ai: AiSettingsDep) -> AiSettingsDTO:
    return settings_view(await run_in_threadpool(ai.resolve), can_store=ai.can_store)


@router.put("/ai", response_model=AiSettingsDTO)
async def put_ai_settings(
    payload: SaveAiSettingsRequest, request: Request, admin: AdminDep, ai: AiSettingsDep
) -> AiSettingsDTO:
    _throttle(request, admin.id)
    return settings_view(await ai.save(payload.to_request(), admin.id), can_store=ai.can_store)


@router.get("/ai/models", response_model=ModelListingDTO)
async def list_ai_models(
    request: Request,
    admin: AdminDep,
    ai: AiSettingsDep,
    slot: Slot = "default",
) -> ModelListingDTO:
    _throttle(request, admin.id)
    return ModelListingDTO.model_validate(await ai.models(slot), from_attributes=True)


@router.post("/ai/test", response_model=AiTestDTO)
async def test_ai(
    payload: TestRequest, request: Request, admin: AdminDep, ai: AiSettingsDep
) -> AiTestDTO:
    _throttle(request, admin.id)
    return AiTestDTO.model_validate(await ai.test(payload.live), from_attributes=True)
