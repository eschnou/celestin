"""Spec 013 R9: `scripts.migrate`, a backup and then the migration."""

from __future__ import annotations

import logging
import sqlite3
import stat
from pathlib import Path

import pytest
from alembic import command

from app.config import get_settings
from app.db.base import make_engine
from app.db.schema import alembic_config, current_revision, expected_head
from scripts import migrate


def seed(path: Path, revision: str) -> str:
    url = f"sqlite:///{path}"
    command.upgrade(alembic_config(url), revision)
    with sqlite3.connect(path) as conn:
        if revision != "head":
            conn.execute(
                "insert into users (id, email, name, password_hash, role, locale, created_at) "
                "values ('u1', 'a@x.be', 'Ana', 'h', 'student', 'fr', '2026-01-01 00:00:00')"
            )
    return url


@pytest.fixture
def env(tmp_path, monkeypatch):
    # `configure_logging` replaces the root handlers, which would take pytest's capture with them.
    monkeypatch.setattr(migrate, "configure_logging", lambda level: None)

    def configure(url: str, **extra: str) -> None:
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("SESSION_SECRET", "test-secret-long-enough")
        for key, value in extra.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield configure
    get_settings.cache_clear()


def revision_of(path: Path) -> str | None:
    engine = make_engine(f"sqlite:///{path}")
    try:
        return current_revision(engine)
    finally:
        engine.dispose()


def test_a_pending_migration_is_backed_up_then_applied(tmp_path, env, caplog, capsys) -> None:
    db = tmp_path / "old.db"
    env(seed(db, "0008"))
    # alembic's env.py reconfigures logging (and drops pytest's handler) on every upgrade: put it back.
    logging.getLogger().addHandler(caplog.handler)
    with caplog.at_level(logging.INFO):
        assert migrate.main([]) == 0
    assert revision_of(db) == expected_head()
    (backup,) = (tmp_path / "backups").glob("celestin-*-from-0008.db")
    assert revision_of(backup) == "0008"  # the copy is what the database was
    with sqlite3.connect(backup) as conn:
        assert conn.execute("select count(*) from users").fetchone() == (1,)
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    record = next(r for r in caplog.records if r.message == "migration_backup")
    assert record.from_revision == "0008" and record.path == str(backup)  # type: ignore[attr-defined]
    assert f"backup: {backup}" in capsys.readouterr().out


def test_a_new_database_is_migrated_without_a_backup(tmp_path, env) -> None:
    db = tmp_path / "new.db"
    env(f"sqlite:///{db}")
    assert migrate.main([]) == 0
    assert revision_of(db) == expected_head() and not (tmp_path / "backups").exists()


def test_a_database_at_the_latest_revision_is_left_alone(tmp_path, env) -> None:
    db = tmp_path / "head.db"
    env(seed(db, "head"))
    assert migrate.main([]) == 0
    assert not (tmp_path / "backups").exists()


def test_only_the_newest_backups_are_kept(tmp_path, env) -> None:
    db = tmp_path / "old.db"
    url = f"sqlite:///{db}"
    env(url, MIGRATION_BACKUPS_KEPT="2")
    seed(db, "0008")
    for _ in range(4):
        assert migrate.main([]) == 0  # a backup, then 0009
        command.downgrade(alembic_config(url), "0008")  # pending again
    assert len(list((tmp_path / "backups").glob("celestin-*.db"))) == 2


def test_a_failed_backup_stops_before_the_migration(tmp_path, env, capsys) -> None:
    db = tmp_path / "old.db"
    env(seed(db, "0008"))
    (tmp_path / "backups").write_text("a file where the directory should be")  # the backup cannot be made
    assert migrate.main([]) == 1
    assert revision_of(db) == "0008"  # untouched
    assert "migrate: " in capsys.readouterr().err


def test_another_database_is_migrated_without_a_backup(tmp_path, env, monkeypatch, caplog) -> None:
    """Not SQLite: no file to copy. The upgrade is stubbed: this only needs the decision."""
    env("postgresql+psycopg://u@h/db")
    monkeypatch.setattr(migrate, "make_engine", lambda url: make_engine(f"sqlite:///{tmp_path / 'x.db'}"))
    monkeypatch.setattr(migrate, "current_revision", lambda engine: "0008")
    upgraded: list[str] = []
    monkeypatch.setattr(migrate.command, "upgrade", lambda config, target: upgraded.append(target))
    with caplog.at_level(logging.INFO):
        assert migrate.main([]) == 0
    assert upgraded == ["head"]
    skipped = next(r for r in caplog.records if r.message == "migration_backup_skipped")
    assert skipped.reason == "not_sqlite"  # type: ignore[attr-defined]


def test_alembic_by_hand_takes_no_backup(tmp_path) -> None:
    db = tmp_path / "old.db"
    url = seed(db, "0008")
    command.upgrade(alembic_config(url), "head")
    assert not (tmp_path / "backups").exists()
