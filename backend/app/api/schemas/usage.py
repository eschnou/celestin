"""The usage ledger's wire DTOs (spec 015 §3.6).

Metadata only, and no name of a course or a chapter: a call says which course by its id, its subject and its
language, which is enough to attribute a cost and nothing a student wrote.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api.schemas.admin import AdminUserDTO
from app.db.repositories import Breakdown, CallListing, ModelUsage, RoleUsage, UsageSummary, UsageTotals, UserUsage
from app.domain.ai_config import Role
from app.domain.usage import Feature, Status

Direction = Literal["asc", "desc"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TotalsDTO(_Model):
    """`cost_usd` is the sum of the costs the provider reported, null when none did; `costed_calls` of `calls`
    reported one. Tokens sum what was reported."""

    calls: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float | None
    costed_calls: int


class UserUsageDTO(TotalsDTO):
    user_id: str
    name: str
    email: str
    enabled: bool


class RoleUsageDTO(TotalsDTO):
    role: Role


class ModelUsageDTO(TotalsDTO):
    model: str
    provider: str


class SummaryResponse(_Model):
    totals: TotalsDTO
    models: list[str]


class UserUsageListResponse(_Model):
    users: list[UserUsageDTO]
    total: int


class UserUsageDetailResponse(_Model):
    user: AdminUserDTO
    totals: TotalsDTO
    by_role: list[RoleUsageDTO]
    by_model: list[ModelUsageDTO]


class CallDTO(_Model):
    id: int
    created_at: datetime
    user_id: str
    user_name: str
    user_email: str
    course_id: str | None
    chapter_id: str | None
    course_subject: str | None
    course_language: str | None
    correlation_id: str | None
    role: Role
    feature: Feature
    model: str
    provider: str
    status: Status
    error_code: str | None
    latency_ms: int | None
    ttft_ms: int | None
    input_tokens: int | None
    cached_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    input_audio_tokens: int | None
    output_audio_tokens: int | None
    audio_seconds: float | None
    cost_usd: float | None


class CallListResponse(_Model):
    calls: list[CallDTO]
    has_more: bool


def totals_dto(totals: UsageTotals) -> TotalsDTO:
    return TotalsDTO(**asdict(totals))


def summary_response(summary: UsageSummary) -> SummaryResponse:
    return SummaryResponse(totals=totals_dto(summary.totals), models=summary.models)


def user_usage_dto(item: UserUsage) -> UserUsageDTO:
    return UserUsageDTO(user_id=item.user_id, name=item.name, email=item.email, enabled=item.enabled, **asdict(item.totals))


def detail_response(user: AdminUserDTO, breakdown: Breakdown) -> UserUsageDetailResponse:
    def role(item: RoleUsage) -> RoleUsageDTO:
        return RoleUsageDTO(role=item.role, **asdict(item.totals))  # type: ignore[arg-type]

    def model(item: ModelUsage) -> ModelUsageDTO:
        return ModelUsageDTO(model=item.model, provider=item.provider, **asdict(item.totals))

    return UserUsageDetailResponse(
        user=user,
        totals=totals_dto(breakdown.totals),
        by_role=[role(r) for r in breakdown.by_role],
        by_model=[model(m) for m in breakdown.by_model],
    )


def call_dto(call: CallListing) -> CallDTO:
    return CallDTO(
        id=call.id,
        user_name=call.user_name,
        user_email=call.user_email,
        course_subject=call.course_subject,
        course_language=call.course_language,
        **asdict(call.entry),
    )
