"""Spec 012: the one way to get an admin."""

from __future__ import annotations

import pytest
from alembic import command

from app.config import get_settings
from app.db.base import make_engine, make_session_factory
from app.db.repositories import Repositories
from app.db.schema import alembic_config
from scripts import create_admin


@pytest.fixture
def database(tmp_path, monkeypatch) -> Repositories:
    url = f"sqlite:///{tmp_path / 'a.db'}"
    command.upgrade(alembic_config(url), "head")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("SESSION_SECRET", "test-secret-long-enough")
    monkeypatch.setenv("ARGON2_MEMORY_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME", "1")
    get_settings.cache_clear()
    yield Repositories.from_factory(make_session_factory(make_engine(url)))
    get_settings.cache_clear()


def test_creates_an_enabled_admin(database, capsys) -> None:
    assert create_admin.main(["--email", "Admin@Example.be", "--password", "mot-de-passe-solide"]) == 0
    user = database.users.by_email("admin@example.be").user
    assert user.role == "admin" and user.enabled is True


def test_promotes_an_existing_disabled_account_and_replaces_its_password(database) -> None:
    created = database.users.create("lea@example.be", "Léa", "old-hash", enabled=False)
    token_hash = "a" * 64
    database.sessions.create(created.id, token_hash)
    assert create_admin.main(["--email", "lea@example.be", "--password", "mot-de-passe-solide"]) == 0
    stored = database.users.by_email("lea@example.be")
    assert stored.user.role == "admin" and stored.user.enabled is True
    assert stored.password_hash != "old-hash"
    assert database.sessions.by_token_hash(token_hash) is None


def test_refuses_a_weak_password(database, capsys) -> None:
    assert create_admin.main(["--email", "admin@example.be", "--password", "court"]) == 2
    assert database.users.by_email("admin@example.be") is None


def test_asks_for_the_password_when_none_is_given(database, monkeypatch) -> None:
    answers = iter(["mot-de-passe-solide", "mot-de-passe-solide"])
    monkeypatch.setattr("scripts.create_admin.getpass.getpass", lambda _prompt: next(answers))
    assert create_admin.main(["--email", "admin@example.be"]) == 0
    assert database.users.by_email("admin@example.be").user.role == "admin"


def test_refuses_two_different_answers(database, monkeypatch, capsys) -> None:
    answers = iter(["mot-de-passe-solide", "autre-mot-de-passe-solide"])
    monkeypatch.setattr("scripts.create_admin.getpass.getpass", lambda _prompt: next(answers))
    assert create_admin.main(["--email", "admin@example.be"]) == 2
    assert database.users.by_email("admin@example.be") is None
