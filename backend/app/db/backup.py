"""A copy of the SQLite database, taken before a migration (spec 013 §3.9).

SQLite's online backup API copies a consistent snapshot while the file is in use (WAL included). The copy
lands in `backups/` beside the database, named with its UTC time and the revision it holds, readable by
the owner only: it holds email addresses and password hashes. Only the newest few are kept.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

BACKUPS_DIR = "backups"
PATTERN = "celestin-*-from-*.db"


def backup_database(db: Path, revision: str, *, keep: int, now: datetime | None = None) -> Path:
    """Copy `db` into `backups/` and prune to the newest `keep`. Any failure raises, and leaves no
    partial file behind."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    directory = db.parent / BACKUPS_DIR
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    # Microseconds keep two backups of one second apart and the names sortable as plain text.
    stamp = moment.strftime("%Y%m%dT%H%M%S") + f"{moment.microsecond:06d}Z"
    final = directory / f"celestin-{stamp}-from-{revision}.db"
    partial = final.with_suffix(".db.tmp")
    try:
        with closing(sqlite3.connect(db)) as source, closing(sqlite3.connect(partial)) as target:
            source.backup(target)
            # A copy of a WAL database would stay in WAL mode and grow sidecar files each time it
            # is opened: make it one self-contained file.
            target.execute("pragma journal_mode=delete")
        os.chmod(partial, 0o600)
        os.replace(partial, final)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    for old in sorted(directory.glob(PATTERN), reverse=True)[keep:]:
        old.unlink(missing_ok=True)
    return final
