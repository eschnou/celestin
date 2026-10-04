"""Spec 013 §3.4: the repository methods behind the first-run setup and the stored key."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine

from app.db.base import make_session_factory
from app.db.repositories import Repositories
from app.domain.errors import SetupDone


def test_app_settings_get_put_overwrite_delete(repos: Repositories) -> None:
    store = repos.app_settings
    assert store.get("openai_api_key") is None
    store.put("openai_api_key", "one", "u1")
    assert store.get("openai_api_key") == "one"
    store.put("openai_api_key", "two", None)
    assert store.get("openai_api_key") == "two"
    assert store.delete("openai_api_key") is True
    assert store.get("openai_api_key") is None
    assert store.delete("openai_api_key") is False


def test_any_exists(repos: Repositories) -> None:
    assert repos.users.any_exists() is False
    repos.users.create("a@x.be", "Ana", "hash")
    assert repos.users.any_exists() is True


def test_first_admin_is_created_on_an_empty_table(repos: Repositories) -> None:
    user = repos.users.create_first_admin("a@x.be", "Ana", "hash", "en")
    assert (user.email, user.name, user.role, user.locale, user.enabled) == ("a@x.be", "Ana", "admin", "en", True)
    stored = repos.users.by_email("a@x.be")
    assert stored is not None and stored.user.id == user.id and stored.password_hash == "hash"
    assert repos.users.any_exists() is True


def test_first_admin_refuses_when_any_user_exists(repos: Repositories) -> None:
    repos.users.create("s@x.be", "Sam", "hash")
    with pytest.raises(SetupDone):
        repos.users.create_first_admin("a@x.be", "Ana", "hash", "fr")
    assert repos.users.by_email("a@x.be") is None


def test_two_simultaneous_first_admins_create_exactly_one(db_engine: Engine) -> None:
    factory = make_session_factory(db_engine)

    def attempt(n: int) -> str:
        try:
            Repositories.from_factory(factory).users.create_first_admin(f"a{n}@x.be", "Ana", "hash", "fr")
            return "created"
        except SetupDone:
            return "refused"

    for _ in range(5):  # a race, so more than once
        with ThreadPoolExecutor(6) as pool:
            outcomes = list(pool.map(attempt, range(6)))
        assert outcomes.count("created") == 1 and outcomes.count("refused") == 5
        with factory() as s:
            from sqlalchemy import delete

            from app.db.models import UserRow

            s.execute(delete(UserRow))
            s.commit()
