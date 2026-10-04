"""Who is asking (004 design 4.2). No hash here: the domain never sees it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from app.domain.locale import DEFAULT_LOCALE, Locale

Role = Literal["student", "parent", "admin"]
ROLES: tuple[str, ...] = get_args(Role)

# Who may create an account (spec 012): anyone; nobody; or anyone, but an admin has
# to enable the account before its first sign-in.
RegistrationMode = Literal["open", "closed", "verification"]
REGISTRATION_MODES: tuple[str, ...] = get_args(RegistrationMode)


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    role: Role
    # The interface language; the default keeps every `User(...)` call valid.
    locale: Locale = DEFAULT_LOCALE
    # A disabled account cannot sign in and holds no session (spec 012). Defaults to
    # enabled so every `User(...)` call stays valid.
    enabled: bool = True
