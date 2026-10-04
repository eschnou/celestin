"""Bring the database to the latest revision, after a backup (spec 013 R9).

    uv run python -m scripts.migrate

When a migration is pending on a SQLite database that already has a revision, the file is copied to
`backups/` beside it first (the newest `MIGRATION_BACKUPS_KEPT` are kept). A new database, or one already
at the latest revision, is not copied. If the backup fails nothing is migrated. This is what the Docker
entrypoint runs at every start; `alembic upgrade head` by hand still works and takes no backup.
"""

from __future__ import annotations

import logging
import sys

from alembic import command

from app.config import get_settings
from app.db.backup import backup_database
from app.db.base import make_engine, sqlite_file
from app.db.schema import alembic_config, current_revision, expected_head
from app.logging_config import configure_logging

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    url = settings.database_url
    engine = make_engine(url)
    try:
        current, head = current_revision(engine), expected_head()
        if current is not None and current != head:
            path = sqlite_file(url)
            if path is None:
                log.info("migration_backup_skipped", extra={"reason": "not_sqlite", "from_revision": current})
            else:
                backup = backup_database(path, current, keep=settings.migration_backups_kept)
                log.info(
                    "migration_backup",
                    extra={"path": str(backup), "from_revision": current, "kept": settings.migration_backups_kept},
                )
                print(f"backup: {backup}")
        command.upgrade(alembic_config(url), "head")
    except Exception as exc:  # noqa: BLE001 - say why on one line and stop: the database is as it was
        print(f"migrate: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
