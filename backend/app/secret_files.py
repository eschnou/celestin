"""The two secrets the application owns (spec 013 §3.2).

`session_secret` keys the session-token hash; `encryption_key` encrypts the OpenAI API key in the
database. Either comes from the environment (the session secret only) or from a file in
`SECRETS_DIR`, generated on first boot. The files are independent on purpose: deleting the session
secret signs everyone out and leaves the stored API key readable; deleting the encryption key makes
the stored API key unreadable and signs nobody out.

A file that exists but cannot be used stops the start. It is never regenerated silently.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from app.config import MIN_SESSION_SECRET_CHARS, Settings

log = logging.getLogger(__name__)

SESSION_SECRET_FILE = "session_secret"
ENCRYPTION_KEY_FILE = "encryption_key"
_HEX_KEY = re.compile(r"[0-9a-f]{64}")
MIN_SESSION_SECRET = 32  # characters in a file; the environment variable keeps its 16


class SecretFileError(RuntimeError):
    """A secret file that cannot be read or is the wrong size. Names the file and the remedy."""


@dataclass(frozen=True)
class Secrets:
    session_secret: str
    encryption_key: bytes | None  # 32 bytes; None without SECRETS_DIR (nothing can be stored)

    def __repr__(self) -> str:  # never in a log or a traceback
        return "Secrets(…)"


def load_secrets(settings: Settings) -> Secrets:
    directory = settings.secrets_dir
    if directory is None:
        return Secrets(settings.require_session_secret(), None)

    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        pass  # a mount that refuses chmod: the files below are 0600 in any case

    generated: list[str] = []
    if len(settings.session_secret) >= MIN_SESSION_SECRET_CHARS:
        session_secret = settings.session_secret
    else:
        value, created = _read_or_create(directory / SESSION_SECRET_FILE)
        if len(value) < MIN_SESSION_SECRET or any(c.isspace() for c in value):
            raise _invalid(directory / SESSION_SECRET_FILE, f"it must hold at least {MIN_SESSION_SECRET} characters", "signs everyone out")
        session_secret = value
        if created:
            generated.append(SESSION_SECRET_FILE)

    key_path = directory / ENCRYPTION_KEY_FILE
    key_hex, created = _read_or_create(key_path)
    if not _HEX_KEY.fullmatch(key_hex):
        raise _invalid(key_path, "it must hold exactly 64 hexadecimal characters", "makes the stored OpenAI key unreadable")
    if created:
        generated.append(ENCRYPTION_KEY_FILE)

    if generated:
        log.info("secrets_generated", extra={"files": generated})
    return Secrets(session_secret, bytes.fromhex(key_hex))


def read_encryption_key(directory: Path) -> bytes | None:
    """The encryption key in `directory`, or None when there is none or it cannot be used. Never creates
    anything: for the scripts, which read what a server stored and must not make a secret of their own."""
    try:
        text = (directory / ENCRYPTION_KEY_FILE).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return bytes.fromhex(text) if _HEX_KEY.fullmatch(text) else None


def _read_or_create(path: Path) -> tuple[str, bool]:
    """The file's content, creating it atomically (never overwriting) when it is missing."""
    try:
        return path.read_text(encoding="ascii").strip(), False
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError) as exc:
        raise SecretFileError(f"{path}: cannot be read ({exc.__class__.__name__}); check its owner and mode") from exc
    value = secrets.token_hex(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # another process won the race: use its value
        return path.read_text(encoding="ascii").strip(), False
    except OSError as exc:
        raise SecretFileError(f"{path}: cannot be created ({exc.__class__.__name__}); is the directory writable?") from exc
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(value + "\n")
    return value, True


def _invalid(path: Path, why: str, consequence: str) -> SecretFileError:
    return SecretFileError(
        f"{path}: {why}. Fix the file, or delete it to generate a new one (this {consequence})."
    )
