"""Admin wire DTOs (spec 012)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.locale import Locale
from app.domain.user import RegistrationMode, Role


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdminUserDTO(_Model):
    id: str
    email: str
    name: str
    role: Role
    locale: Locale
    enabled: bool
    created_at: datetime
    last_seen_at: datetime | None


class UserCountsDTO(_Model):
    total: int
    enabled: int
    disabled: int


class UserListResponse(_Model):
    users: list[AdminUserDTO]
    # How many match the filter, for paging; `counts` is the whole table, for the tabs.
    total: int
    counts: UserCountsDTO
    registration_mode: RegistrationMode


class UpdateUserRequest(_Model):
    enabled: bool


class UserEnvelope(_Model):
    user: AdminUserDTO


class ResetPasswordResponse(_Model):
    """The new password, shown once: only its hash is stored."""

    user: AdminUserDTO
    password: str


UserStatus = Literal["all", "enabled", "disabled"]
