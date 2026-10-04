"""Registration, sign-in and sessions (004 design 3.2).

Tokens are 256-bit random strings; the table stores HMAC-SHA256(secret, token),
so a leaked database cannot mint a session. Unknown emails still pay a hash
verification, so timing does not tell them apart from wrong passwords.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.config import Settings
from app.db.base import utcnow
from app.db.repositories import Repositories
from app.domain.errors import (
    AccountDisabled,
    EmailTaken,
    InvalidCredentials,
    NotAuthenticated,
    NotFound,
    OwnAccount,
    RegistrationClosed,
    SetupRequired,
    WeakPassword,
    WrongPassword,
)
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.password import check_password
from app.domain.user import RegistrationMode, User

log = logging.getLogger(__name__)

TOUCH_INTERVAL = timedelta(hours=1)

# A temporary password is read out and typed by hand: no 0/O, 1/l/I, and no symbols. 14 characters
# of 54 are about 80 bits.
TEMPORARY_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TEMPORARY_PASSWORD_LENGTH = 14


class PasswordHasher:
    def __init__(self, memory_kib: int, time_cost: int, parallelism: int) -> None:
        self._hash = PasswordHash(
            (Argon2Hasher(memory_cost=memory_kib, time_cost=time_cost, parallelism=parallelism),)
        )
        # Verified against when the email is unknown, so both paths cost the same.
        self._dummy = self._hash.hash(secrets.token_urlsafe(16))

    def hash(self, password: str) -> str:
        return self._hash.hash(password)

    def verify_and_update(self, password: str, stored: str) -> tuple[bool, str | None]:
        return self._hash.verify_and_update(password, stored)

    def burn(self, password: str) -> None:
        self._hash.verify(password, self._dummy)


def normalise_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(
        self,
        repos: Repositories,
        hasher: PasswordHasher,
        settings: Settings,
        clock: Callable[[], datetime] = utcnow,
        *,
        secret: str | None = None,
    ) -> None:
        """`secret` is the session secret `load_secrets` resolved (spec 013); without it the
        setting is read as it always was."""
        self._repos = repos
        self.hasher = hasher
        self._secret = (secret if secret is not None else settings.require_session_secret()).encode("utf-8")
        # Once an account exists the instance is out of its first-run state for good: accounts are
        # never deleted, so a `True` here never needs to be read again (spec 013 R1.1).
        self._users_exist = False
        self._idle = timedelta(days=settings.session_idle_days)
        self._absolute = timedelta(days=settings.session_absolute_days)
        self._clock = clock
        self.registration_mode: RegistrationMode = settings.registration_mode

    # ------------------------------------------------------------- accounts

    def setup_required(self) -> bool:
        """Whether the instance still waits for its first administrator: it has no account."""
        if not self._users_exist:
            self._users_exist = self._repos.users.any_exists()
        return not self._users_exist

    def setup(
        self, email: str, password: str, name: str, locale: Locale = DEFAULT_LOCALE
    ) -> tuple[User, str]:
        """The first administrator and their session (spec 013). Only while no account exists,
        decided in the insert itself: `SetupDone` for any later call, whoever makes it."""
        email = normalise_email(email)
        name = name.strip()
        refusal = check_password(password, email, name)
        if refusal:
            raise WeakPassword(refusal)
        user = self._repos.users.create_first_admin(email, name, self.hasher.hash(password), locale)
        self._users_exist = True
        log.info("setup_completed", extra={"user_id": user.id})
        return user, self.open_session(user)

    def register(
        self, email: str, password: str, name: str, locale: Locale = DEFAULT_LOCALE
    ) -> tuple[User, str | None]:
        """The new account and its session token. In `verification` mode the account
        starts disabled and there is no token: the student signs in once an admin has
        enabled it. In `closed` mode there is no registration at all (spec 012). While the
        instance waits for its first administrator nobody registers, whatever the mode (spec 013):
        the first account must be the administrator's."""
        if self.setup_required():
            log.info("auth_register_refused", extra={"reason": "setup_pending"})
            raise SetupRequired()
        if self.registration_mode == "closed":
            log.info("auth_register_refused", extra={"reason": "closed"})
            raise RegistrationClosed()
        email = normalise_email(email)
        name = name.strip()
        refusal = check_password(password, email, name)
        if refusal:
            raise WeakPassword(refusal)
        if self._repos.users.by_email(email) is not None:
            raise EmailTaken()
        pending = self.registration_mode == "verification"
        user = self._repos.users.create(
            email, name, self.hasher.hash(password), locale=locale, enabled=not pending
        )
        log.info("auth_register", extra={"user_id": user.id, "pending": pending})
        return user, None if pending else self.open_session(user)

    def login(self, email: str, password: str) -> tuple[User, str]:
        stored = self._repos.users.by_email(normalise_email(email))
        if stored is None:
            self.hasher.burn(password)
            log.info("auth_login_failed", extra={"reason": "unknown_email"})
            raise InvalidCredentials()
        ok, new_hash = self.hasher.verify_and_update(password, stored.password_hash)
        if not ok:
            log.info("auth_login_failed", extra={"reason": "bad_password", "user_id": stored.user.id})
            raise InvalidCredentials()
        if new_hash:
            self._repos.users.update_hash(stored.user.id, new_hash)
        if not stored.user.enabled:
            # Only said once the password was right: the answer must not tell a stranger
            # which addresses have an account.
            log.info("auth_login_failed", extra={"reason": "disabled", "user_id": stored.user.id})
            raise AccountDisabled()
        log.info("auth_login_ok", extra={"user_id": stored.user.id})
        return stored.user, self.open_session(stored.user)

    def set_locale(self, user_id: str, locale: Locale) -> User:
        """The user with a new interface language (spec 010 R2.4)."""
        user = self._repos.users.set_locale(user_id, locale)
        if user is None:
            raise NotAuthenticated()
        return user

    def change_password(self, user: User, current: str, new: str, token: str | None) -> None:
        """The user's own change: the current password proves it is them. Every other
        session of the account ends; the one making the change stays."""
        stored = self._repos.users.stored_by_id(user.id)
        if stored is None:
            raise NotAuthenticated()
        ok, _ = self.hasher.verify_and_update(current, stored.password_hash)
        if not ok:
            log.info("auth_password_change_failed", extra={"user_id": user.id})
            raise WrongPassword()
        refusal = check_password(new, stored.user.email, stored.user.name)
        if refusal:
            raise WeakPassword(refusal)
        session = self._repos.sessions.by_token_hash(self._digest(token)) if token else None
        self._repos.users.set_hash_and_revoke(
            user.id, self.hasher.hash(new), keep_session=session.id if session else None
        )
        log.info("auth_password_changed", extra={"user_id": user.id})

    # --------------------------------------------------------------- admin

    def set_enabled(self, actor: User, user_id: str, enabled: bool) -> User:
        """An admin enables or disables an account (spec 012). Disabling signs the
        account out everywhere. An admin cannot disable themselves, which also means
        there is always one enabled admin left."""
        if user_id == actor.id and not enabled:
            raise OwnAccount()
        user = self._repos.users.set_enabled(user_id, enabled)
        if user is None:
            raise NotFound()
        log.info(
            "admin_user_enabled" if enabled else "admin_user_disabled",
            extra={"actor_id": actor.id, "user_id": user_id},
        )
        return user

    def reset_password(self, actor: User, user_id: str) -> str:
        """A new random password for the account, returned once and stored only as a
        hash; every session of the account ends. The admin hands it over; the user
        changes it from the settings."""
        if user_id == actor.id:
            raise OwnAccount()
        stored = self._repos.users.stored_by_id(user_id)
        if stored is None:
            raise NotFound()
        password = self._temporary_password(stored.user)
        self._repos.users.set_hash_and_revoke(user_id, self.hasher.hash(password))
        log.info("admin_password_reset", extra={"actor_id": actor.id, "user_id": user_id})
        return password

    @staticmethod
    def _temporary_password(user: User) -> str:
        while True:
            password = "".join(
                secrets.choice(TEMPORARY_PASSWORD_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH)
            )
            if check_password(password, user.email, user.name) is None:
                return password

    def logout(self, token: str) -> None:
        session = self._repos.sessions.by_token_hash(self._digest(token))
        if session:
            self._repos.sessions.delete(session.id)
            log.info("auth_logout", extra={"user_id": session.user_id})

    # ------------------------------------------------------------- sessions

    def authenticate(self, token: str) -> User | None:
        """The user behind a token, or None. Expired rows are deleted on sight;
        `last_seen_at` moves at most once an hour."""
        found = self._repos.sessions.lookup(self._digest(token))
        if found is None:
            return None
        session, user = found
        if not user.enabled:
            self._repos.sessions.delete(session.id)
            return None
        now = self._clock()
        if now > session.last_seen_at + self._idle or now > session.created_at + self._absolute:
            self._repos.sessions.delete(session.id)
            return None
        if now - session.last_seen_at >= TOUCH_INTERVAL:
            self._repos.sessions.touch(session.id, now)
            self._repos.users.mark_seen(user.id, now)
        return user

    def purge_expired(self) -> int:
        count = self._repos.sessions.purge_expired(self._clock(), self._idle, self._absolute)
        if count:
            log.info("sessions_purged", extra={"count": count})
        return count

    def open_session(self, user: User) -> str:
        """A fresh token for `user`; what register and login hand to the cookie."""
        token = secrets.token_urlsafe(32)
        now = self._clock()
        self._repos.sessions.create(user.id, self._digest(token), now=now)
        self._repos.users.mark_seen(user.id, now)
        return token

    def _digest(self, token: str) -> str:
        return hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
