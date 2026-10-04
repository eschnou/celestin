"""Create an admin, or make an existing account one (spec 012).

    uv run python -m scripts.create_admin --email admin@example.be [--name Admin]

The password is asked for twice, not read from the command line (which ends up in the shell
history and the process list). `--password` exists for scripts and tests.

Idempotent: an unknown address gets a new enabled admin account; a known one is made an
admin, enabled, and given the new password. There is no other way to become an admin:
the dashboard enables, disables and resets passwords, it does not promote. Run it
again with a new password to recover a lost admin account.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.config import get_settings
from app.db.base import make_engine, make_session_factory
from app.db.repositories import Repositories
from app.db.schema import check_schema
from app.domain.errors import WeakPassword
from app.domain.password import check_password
from app.services.auth_service import PasswordHasher, normalise_email


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", help="for scripts; omit it to be asked")
    parser.add_argument("--name", default="Admin")
    args = parser.parse_args(argv)

    email = normalise_email(args.email)
    password = args.password
    if password is None:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Again: "):
            print("The two passwords differ.", file=sys.stderr)
            return 2
    refusal = check_password(password, email, args.name)
    if refusal:
        print(WeakPassword(refusal), file=sys.stderr)
        return 2
    settings = get_settings()
    engine = make_engine(settings.database_url)
    check_schema(engine)
    repos = Repositories.from_factory(make_session_factory(engine))
    hasher = PasswordHasher(settings.argon2_memory_kib, settings.argon2_time, settings.argon2_parallelism)
    stored = repos.users.by_email(email)
    if stored is None:
        repos.users.create(email, args.name.strip(), hasher.hash(password), role="admin")
        print(f"admin {email} created")
    else:
        repos.users.make_admin(stored.user.id, hasher.hash(password))
        print(f"{email} is now an enabled admin, with the new password")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
