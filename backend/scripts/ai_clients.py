"""The AI configuration the scripts run on (spec 014 R9.1).

The same resolution the server does: the environment first, then what an administrator stored, so
`OPENAI_BASE_URL=… OPENAI_MODEL=… uv run python -m scripts.probe` and a provider configured in the settings
screen both work. The stored settings are read only when the database file already exists and
`SECRETS_DIR` has its encryption key: a script never creates either.
"""

from __future__ import annotations

from app.config import Settings
from app.db.base import make_engine, make_session_factory, sqlite_file
from app.db.repositories import AppSettingsRepository
from app.domain.ai_config import AiConfig, Role
from app.providers.hub import ProviderHub
from app.secret_files import read_encryption_key
from app.services.ai_settings import load_ai_config
from app.services.cipher import Cipher


def _stored(settings: Settings) -> tuple[AppSettingsRepository | None, Cipher | None]:
    path = sqlite_file(settings.database_url)
    if path is None or not path.is_file():
        return None, None
    repo = AppSettingsRepository(make_session_factory(make_engine(settings.database_url)))
    key = read_encryption_key(settings.secrets_dir) if settings.secrets_dir else None
    cipher = Cipher(key) if key else None
    return repo, cipher


def resolve(settings: Settings) -> AiConfig:
    """The configuration in force, or `MissingApiKey` saying what is missing."""
    repo, cipher = _stored(settings)
    return load_ai_config(settings, repo, cipher)


def hub(settings: Settings) -> ProviderHub:
    """A hub with the configuration in force applied: proxies for the services, `hub.config` for the header."""
    applied = ProviderHub(settings)
    applied.apply(resolve(settings))
    return applied


def describe(config: AiConfig, *roles: Role) -> str:
    """`api.groq.com · openai/gpt-oss-120b` for each role asked about, for a script's header line."""
    shown = []
    for name in roles:
        rc = config.role(name)
        if rc is not None:
            shown.append(f"{name}: {rc.connection.host} · {rc.model} ({rc.connection.api_style})")
    return " | ".join(shown)
