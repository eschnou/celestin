"""Password policy (004 R1.3): length, and nothing personal in it."""

from __future__ import annotations

MIN_LENGTH = 6


def check_password(password: str, email: str, name: str) -> str | None:
    """Why the password is refused (`too_short` or `personal`, the keys of
    `WeakPassword`), else None. The sentence is the catalog's."""
    if len(password) < MIN_LENGTH:
        return "too_short"
    lowered = password.lower()
    local_part = email.lower().split("@", 1)[0]
    for personal in (local_part, name.lower()):
        if len(personal) >= 3 and personal in lowered:
            return "personal"
    return None
