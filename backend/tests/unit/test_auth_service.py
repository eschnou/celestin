from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.db.repositories import Repositories
from app.domain.errors import EmailTaken, InvalidCredentials, WeakPassword
from app.services.auth_service import AuthService, PasswordHasher
from tests.conftest import occupy


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class SpyHasher(PasswordHasher):
    def __init__(self) -> None:
        super().__init__(memory_kib=8192, time_cost=1, parallelism=1)
        self.verifications = 0

    def verify_and_update(self, password: str, stored: str):
        self.verifications += 1
        return super().verify_and_update(password, stored)

    def burn(self, password: str) -> None:
        self.verifications += 1
        super().burn(password)


@pytest.fixture
def auth(repos: Repositories, settings: Settings):
    clock = Clock()
    hasher = SpyHasher()
    service = AuthService(repos, hasher, settings, clock=clock)
    occupy(repos)  # not waiting for the first administrator: registration is open
    return service, clock, hasher


def test_register_normalises_and_signs_in(auth, repos: Repositories) -> None:
    service, _, _ = auth
    user, token = service.register("  Lea@Example.BE ", "mot-de-passe-solide", " Léa ")
    assert user.email == "lea@example.be" and user.name == "Léa" and user.role == "student"
    assert service.authenticate(token) == user
    assert repos.users.by_email("lea@example.be").password_hash != "mot-de-passe-solide"  # type: ignore[union-attr]


def test_register_refuses_weak_and_taken(auth) -> None:
    service, _, _ = auth
    with pytest.raises(WeakPassword):
        service.register("lea@example.be", "court", "Léa")
    service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    with pytest.raises(EmailTaken):
        service.register("LEA@example.be", "un-autre-mot-de-passe", "Léa")


def test_login_paths_cost_the_same(auth) -> None:
    service, _, hasher = auth
    service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    hasher.verifications = 0
    with pytest.raises(InvalidCredentials):
        service.login("nobody@example.be", "mot-de-passe-solide")
    with pytest.raises(InvalidCredentials):
        service.login("lea@example.be", "faux-mot-de-passe")
    assert hasher.verifications == 2
    user, token = service.login("lea@example.be", "mot-de-passe-solide")
    assert service.authenticate(token) == user


def test_logout_and_unknown_token(auth) -> None:
    service, _, _ = auth
    _, token = service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    service.logout(token)
    assert service.authenticate(token) is None
    assert service.authenticate("not-a-token") is None
    service.logout("not-a-token")  # no error


def test_idle_and_absolute_expiry(auth, repos: Repositories) -> None:
    service, clock, _ = auth
    user, token = service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    clock.now += timedelta(days=29)
    assert service.authenticate(token) == user          # renewed by use
    clock.now += timedelta(days=29)
    assert service.authenticate(token) == user
    clock.now += timedelta(days=31)
    assert service.authenticate(token) is None          # idle > 30 days
    _, token2 = service.register("bob@example.be", "mot-de-passe-solide", "Bob")
    for _ in range(10):
        clock.now += timedelta(days=10)
        service.authenticate(token2)
    assert service.authenticate(token2) is None         # created > 90 days ago despite use


def test_touch_at_most_hourly(auth, repos: Repositories, db_engine) -> None:
    service, clock, _ = auth
    _, token = service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    start = clock.now
    clock.now += timedelta(minutes=30)
    service.authenticate(token)
    session = next(iter(_sessions(db_engine)))
    assert session.last_seen_at == start
    clock.now += timedelta(minutes=31)
    service.authenticate(token)
    assert next(iter(_sessions(db_engine))).last_seen_at == clock.now


def _sessions(engine):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.base import as_utc
    from app.db.models import SessionRow

    with Session(engine) as s:
        rows = s.scalars(select(SessionRow)).all()
    for row in rows:
        row.last_seen_at = as_utc(row.last_seen_at)
    return rows


def test_purge(auth, repos: Repositories) -> None:
    service, clock, _ = auth
    service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    clock.now += timedelta(days=31)
    assert service.purge_expired() == 1
    assert service.purge_expired() == 0


def test_register_keeps_the_language_it_was_given(auth) -> None:
    service, _, _ = auth
    french, _ = service.register("fr@example.be", "mot-de-passe-solide", "Léa")
    english, token = service.register("en@example.be", "mot-de-passe-solide", "Ann", "en")
    assert french.locale == "fr" and english.locale == "en"
    assert service.authenticate(token).locale == "en"  # type: ignore[union-attr]
    again, _ = service.login("en@example.be", "mot-de-passe-solide")
    assert again.locale == "en"


def test_set_locale_changes_what_authenticate_returns(auth) -> None:
    service, _, _ = auth
    user, token = service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    changed = service.set_locale(user.id, "en")
    assert changed.locale == "en"
    assert service.authenticate(token).locale == "en"  # type: ignore[union-attr]


# ------------------------------------------------------------- first-run setup (spec 013)


@pytest.fixture
def pending(repos: Repositories, settings: Settings):
    """An instance with no account: waiting for its first administrator."""
    return AuthService(repos, SpyHasher(), settings)


def test_setup_is_pending_until_an_account_exists(pending, repos: Repositories) -> None:
    assert pending.setup_required() is True
    repos.users.create("a@x.be", "Ana", "hash")
    assert pending.setup_required() is False


def test_setup_creates_an_enabled_admin_with_a_working_session(pending, repos: Repositories) -> None:
    user, token = pending.setup("  Ada@Example.BE ", "mot-de-passe-solide", " Ada ", "en")
    assert (user.email, user.name, user.role, user.locale, user.enabled) == ("ada@example.be", "Ada", "admin", "en", True)
    assert pending.authenticate(token) == user
    assert pending.setup_required() is False
    assert repos.users.by_email("ada@example.be").password_hash != "mot-de-passe-solide"  # type: ignore[union-attr]


def test_setup_twice_is_refused_for_good(pending) -> None:
    from app.domain.errors import SetupDone

    pending.setup("ada@example.be", "mot-de-passe-solide", "Ada")
    with pytest.raises(SetupDone):
        pending.setup("eve@example.be", "mot-de-passe-solide", "Eve")


def test_setup_refuses_a_weak_password_and_stays_pending(pending) -> None:
    with pytest.raises(WeakPassword):
        pending.setup("ada@example.be", "court", "Ada")
    assert pending.setup_required() is True


@pytest.mark.parametrize("mode", ["open", "closed", "verification"])
def test_registration_waits_for_the_first_administrator_in_every_mode(repos, settings, mode) -> None:
    from app.domain.errors import SetupRequired

    service = AuthService(repos, SpyHasher(), settings.model_copy(update={"registration_mode": mode}))
    with pytest.raises(SetupRequired):
        service.register("lea@example.be", "mot-de-passe-solide", "Léa")
    assert repos.users.by_email("lea@example.be") is None


@pytest.mark.parametrize("exists, reads", [(True, 1), (False, 2)])
def test_only_a_false_answer_is_remembered(settings, exists: bool, reads: int) -> None:
    """Once an account exists the answer is cached; while the instance is waiting it is read every time."""

    class Spy:
        calls = 0

        @property
        def users(self):
            return self

        def any_exists(self) -> bool:
            Spy.calls += 1
            return exists

    service = AuthService(Spy(), SpyHasher(), settings)  # type: ignore[arg-type]
    assert service.setup_required() is (not exists) and service.setup_required() is (not exists)
    assert Spy.calls == reads


def test_the_session_secret_can_be_given_to_the_service(repos: Repositories, settings: Settings) -> None:
    other = settings.model_copy(update={"session_secret": ""})
    service = AuthService(repos, SpyHasher(), other, secret="a-secret-from-a-file-0123456789")
    user, token = service.setup("ada@example.be", "mot-de-passe-solide", "Ada")
    assert service.authenticate(token) == user
