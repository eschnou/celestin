"""The administrator's view of the usage ledger (spec 015 §3.6): totals, per user, per call.

Read-only: nothing here writes. Every route admits `admin` only; a user id is whatever the admin names (there is
no ownership, as in spec 012), and no body carries a course or chapter name.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime
from starlette.concurrency import run_in_threadpool

from app.api.deps import AdminDep, ReposDep
from app.api.routes.admin import one_user
from app.api.schemas.usage import (
    CallListResponse,
    Direction,
    SummaryResponse,
    UserUsageDetailResponse,
    UserUsageListResponse,
    call_dto,
    detail_response,
    summary_response,
    user_usage_dto,
)
from app.db.repositories import CallFilters, Period, UserUsageOrder
from app.domain.ai_config import Role
from app.domain.usage import Feature, Status

router = APIRouter(prefix="/admin/usage")


def _period(
    since: Annotated[AwareDatetime | None, Query(description="Inclusive start, with an offset.")] = None,
    until: Annotated[AwareDatetime | None, Query(description="Exclusive end, with an offset.")] = None,
) -> Period:
    if since is not None and until is not None and since >= until:
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("query", "since"), "msg": "since must be before until", "input": str(since)}]
        )
    return Period(since, until)


PeriodDep = Annotated[Period, Depends(_period)]
LimitQuery = Annotated[int, Query(ge=1, le=200)]


@router.get("/summary", response_model=SummaryResponse)
async def summary(_admin: AdminDep, repos: ReposDep, period: PeriodDep) -> SummaryResponse:
    return summary_response(await run_in_threadpool(repos.ai_usage.summary, period))


@router.get("/users", response_model=UserUsageListResponse)
async def users(
    _admin: AdminDep,
    repos: ReposDep,
    period: PeriodDep,
    q: Annotated[str, Query(max_length=100)] = "",
    order: UserUsageOrder = "calls",
    direction: Direction = "desc",
    limit: LimitQuery = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserUsageListResponse:
    found, total = await run_in_threadpool(
        lambda: repos.ai_usage.per_user(
            period, query=q, order=order, descending=direction == "desc", limit=limit, offset=offset
        )
    )
    return UserUsageListResponse(users=[user_usage_dto(u) for u in found], total=total)


@router.get("/users/{user_id}", response_model=UserUsageDetailResponse)
async def user_detail(user_id: str, _admin: AdminDep, repos: ReposDep, period: PeriodDep) -> UserUsageDetailResponse:
    def load() -> UserUsageDetailResponse:
        user = one_user(repos, user_id)  # 404 for an unknown account
        return detail_response(user, repos.ai_usage.user_breakdown(user_id, period))

    return await run_in_threadpool(load)


@router.get("/calls", response_model=CallListResponse)
async def calls(
    _admin: AdminDep,
    repos: ReposDep,
    period: PeriodDep,
    user_id: Annotated[str | None, Query(max_length=32)] = None,
    role: Role | None = None,
    feature: Feature | None = None,
    model: Annotated[str | None, Query(max_length=200)] = None,
    status: Status | None = None,
    correlation_id: Annotated[str | None, Query(max_length=32)] = None,
    limit: LimitQuery = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CallListResponse:
    filters = CallFilters(
        user_id=user_id, role=role, feature=feature, model=model, status=status, correlation_id=correlation_id
    )
    found, has_more = await run_in_threadpool(
        lambda: repos.ai_usage.calls(period, filters, limit=limit, offset=offset)
    )
    return CallListResponse(calls=[call_dto(c) for c in found], has_more=has_more)
