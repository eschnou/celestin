"""Spec 013 §3.9: the copy of the database taken before a migration."""

from __future__ import annotations

import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.db.backup import backup_database
from app.db.base import sqlite_file


def database(path: Path, rows: int = 3) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute("pragma journal_mode=wal")
        conn.execute("create table t (n integer)")
        conn.executemany("insert into t values (?)", [(n,) for n in range(rows)])
    return path


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:", "postgresql://u@h/db", "postgresql+psycopg://u@h/db"])
def test_only_a_sqlite_file_has_a_path(url: str) -> None:
    assert sqlite_file(url) is None


def test_a_sqlite_url_gives_its_file() -> None:
    assert sqlite_file("sqlite:////data/celestin.db") == Path("/data/celestin.db")
    assert sqlite_file("sqlite:///./data/celestin.db") == Path("./data/celestin.db")


def test_the_copy_holds_the_same_rows_and_is_private(tmp_path: Path) -> None:
    db = database(tmp_path / "a.db", rows=5)
    when = datetime(2026, 10, 3, 10, 30, 11, 123456, tzinfo=UTC)
    backup = backup_database(db, "0008", keep=5, now=when)
    assert backup == tmp_path / "backups" / "celestin-20261003T103011123456Z-from-0008.db"
    assert mode(backup) == 0o600 and mode(backup.parent) == 0o700
    with sqlite3.connect(backup) as conn:
        assert conn.execute("select count(*) from t").fetchone() == (5,)
    assert [p.name for p in backup.parent.iterdir()] == [backup.name]  # no temporary file left


def test_the_copy_is_consistent_while_a_writer_holds_the_file(tmp_path: Path) -> None:
    db = database(tmp_path / "a.db", rows=2)
    writer = sqlite3.connect(db, isolation_level=None)
    writer.execute("begin immediate")
    writer.execute("insert into t values (99)")  # uncommitted: the copy must not see it
    try:
        backup = backup_database(db, "0008", keep=5)
    finally:
        writer.execute("commit")
        writer.close()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("select count(*) from t").fetchone() == (2,)


def test_only_the_newest_are_kept(tmp_path: Path) -> None:
    db = database(tmp_path / "a.db")
    start = datetime(2026, 10, 3, 10, 0, 0, tzinfo=UTC)
    names = [backup_database(db, "0008", keep=3, now=start + timedelta(minutes=n)).name for n in range(5)]
    kept = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert kept == sorted(names)[-3:]


def test_other_files_in_the_directory_are_left_alone(tmp_path: Path) -> None:
    db = database(tmp_path / "a.db")
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "notes.txt").write_text("mine")
    for n in range(3):
        backup_database(db, "0008", keep=1, now=datetime(2026, 10, 3, 10, n, tzinfo=UTC))
    assert (tmp_path / "backups" / "notes.txt").read_text() == "mine"
    assert len(list((tmp_path / "backups").glob("celestin-*.db"))) == 1


def test_a_directory_that_cannot_be_made_raises(tmp_path: Path) -> None:
    db = database(tmp_path / "a.db")
    (tmp_path / "backups").write_text("a file where the directory should be")
    with pytest.raises(OSError):
        backup_database(db, "0008", keep=5)


def test_the_copy_is_one_standalone_file(tmp_path: Path) -> None:
    db = database(tmp_path / "a.db")  # a WAL database
    backup = backup_database(db, "0008", keep=5)
    with sqlite3.connect(backup) as conn:
        assert conn.execute("pragma journal_mode").fetchone() == ("delete",)
    assert sorted(p.name for p in backup.parent.iterdir()) == [backup.name]


def test_a_missing_source_raises_and_leaves_no_partial_file(tmp_path: Path) -> None:
    broken = tmp_path / "not-a-database.db"
    broken.write_text("this is not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        backup_database(broken, "0008", keep=5)
    assert list((tmp_path / "backups").iterdir()) == []
