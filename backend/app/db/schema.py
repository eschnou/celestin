"""Startup schema check (004 design 3.8): refuse to run behind the migrations."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from app.domain.errors import SchemaOutdated

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
UPGRADE_COMMAND = "cd backend && uv run alembic upgrade head"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def expected_head() -> str | None:
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    return heads[0] if heads else None


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def check_schema(engine: Engine) -> None:
    head = expected_head()
    current = current_revision(engine)
    if head != current:
        raise SchemaOutdated(current, head, UPGRADE_COMMAND)
