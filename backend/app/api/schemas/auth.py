"""Auth wire DTOs (004 design 4.3)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.locale import Locale
from app.domain.user import RegistrationMode, Role


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Model):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=200)]
    name: Annotated[str, Field(min_length=1, max_length=80)]


class LoginRequest(_Model):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=200)]


class UserDTO(_Model):
    id: str
    email: str
    name: str
    role: Role
    locale: Locale


class UserResponse(_Model):
    user: UserDTO


class UpdateMeRequest(_Model):
    """The settings a user can change about themselves. Optional fields, unknown ones
    refused: a later setting is a field here (spec 010 NFR 4.1.9). The language is the
    only one; changes that need proof of identity get routes of their own."""

    locale: Locale | None = None


class RegisterPendingResponse(_Model):
    """Registration in verification mode: the account exists, there is no session yet."""

    user: UserDTO
    pending: bool = True


class AuthConfigResponse(_Model):
    """What the signed-out pages need to know: whether to offer registration (spec 012) and whether
    the instance still waits for its first administrator (spec 013)."""

    registration: RegistrationMode
    setup_required: bool = False


class SetupRequest(RegisterRequest):
    """The first administrator: the registration fields, nothing more (spec 013 R2)."""


class ChangePasswordRequest(_Model):
    current_password: Annotated[str, Field(min_length=1, max_length=200)]
    new_password: Annotated[str, Field(min_length=1, max_length=200)]
