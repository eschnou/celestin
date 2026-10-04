"""Engine and session factory (004 design 3.7).

SQLite in development and tests, portable types everywhere, so the move to
PostgreSQL is a `DATABASE_URL` change plus a migration run.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def sqlite_file(url: str) -> Path | None:
    """The database file of a SQLite URL; `None` for memory and for any other database."""
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite") or not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database).expanduser()


def make_engine(url: str) -> Engine:
    """A memory URL gets one shared connection (tests); a file gets WAL and
    enforced foreign keys."""
    if url.startswith("sqlite"):
        memory = url in ("sqlite://", "sqlite:///:memory:")
        path = sqlite_file(url)
        if path is not None:
            # SQLite creates the file but never the directory, and the default
            # lives in a gitignored `data/`: a fresh clone has no such folder.
            path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool if memory else None,
        )

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            if not memory:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
            # SQLite's own lower() folds ASCII only: « Élodie » would not match « élodie ».
            dbapi_connection.create_function(
                "lower", 1, lambda value: value.lower() if isinstance(value, str) else value, deterministic=True
            )

        return engine
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; everything in the app is aware UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
