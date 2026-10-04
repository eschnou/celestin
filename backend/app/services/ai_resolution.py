"""Which AI configuration is in force: environment, else stored, else built-in (spec 014 §3.3).

`Resolver.resolve()` reads the environment (`Settings.model_fields_set` says which fields the environment
set explicitly, not merely defaulted), the stored document (`ai_settings` in `app_settings`) and the legacy
OpenAI key of spec 013, and returns a `Resolved`: the `AiConfig` to run (None when the instance is not
configured) and, for the settings screen, every field with its source. Pure of side effects but for the
database read; the service owns writes.

A key is never put in a state that leaves this module as text: `ConnectionState.key.value` is excluded from
`repr`, and the view the routes build reads `last4` only.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

from app.config import Settings
from app.db.repositories import AppSettingsRepository
from app.domain.ai_config import (
    API_STYLES,
    DEFAULT_EFFORTS,
    DEFAULT_MODELS,
    DEFAULT_VOICE_TRANSCRIPTION_MODEL,
    EFFORTS,
    OPENAI_BASE_URL,
    ROLES,
    STRUCTURED_MODES,
    AiConfig,
    ApiStyle,
    Connection,
    DictationConfig,
    Effort,
    Role,
    RoleConfig,
    StructuredMode,
    normalise_base_url,
)
from app.domain.errors import InvalidAiSettings
from app.services.cipher import Cipher, CipherError

log = logging.getLogger(__name__)

SETTING = "ai_settings"
LEGACY_SETTING = "openai_api_key"  # spec 013: kept readable, and mirrored while the default connection is OpenAI's
LEGACY_CONTEXT = "celestin:openai_api_key:v1"

T = TypeVar("T")
Source = Literal["environment", "stored", "default"]
KeySource = Literal["environment", "stored", "none"]
Slot = Literal["default", "tutor", "authoring", "transcription", "voice"]

# The environment field behind each role's model and effort.
MODEL_FIELD: dict[Role, str] = {
    "tutor": "openai_model",
    "authoring": "authoring_model",
    "transcription": "transcription_model",
    "voice": "voice_model",
}
EFFORT_FIELD: dict[Role, str] = {role: f"{role}_reasoning_effort" for role in ROLES}


class AiConfigError(RuntimeError):
    """The environment holds a value that cannot be used. Startup stops: a guess could send a key to the
    wrong host."""


def key_context(slot: str) -> str:
    return f"celestin:ai_key:v1:{slot}"


# ------------------------------------------------------------------ the stored document


@dataclass
class StoredKey:
    ct: str
    last4: str


@dataclass
class StoredConnection:
    base_url: str | None = None
    api_style: ApiStyle | None = None
    structured: StructuredMode | None = None
    key: StoredKey | None = None


@dataclass
class StoredRole:
    model: str | None = None
    reasoning_effort: str | None = None  # None: unset (the built-in default); "": not sent
    voice_transcription_model: str | None = None
    connection: StoredConnection | None = None


@dataclass
class Stored:
    default: StoredConnection = field(default_factory=StoredConnection)
    roles: dict[Role, StoredRole] = field(default_factory=dict)
    corrupt: bool = False

    def role(self, name: Role) -> StoredRole:
        return self.roles.get(name) or StoredRole()


def _text(value: object, *, allowed: tuple[str, ...] | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    if allowed is not None and value not in allowed:
        return None
    return value


def _stored_key(raw: object) -> StoredKey | None:
    if isinstance(raw, dict) and isinstance(raw.get("ct"), str):
        return StoredKey(raw["ct"], str(raw.get("last4") or ""))
    return None


def _stored_connection(raw: object) -> StoredConnection:
    if not isinstance(raw, dict):
        return StoredConnection()
    return StoredConnection(
        base_url=_text(raw.get("base_url")),
        api_style=_text(raw.get("api_style"), allowed=API_STYLES),  # type: ignore[arg-type]
        structured=_text(raw.get("structured"), allowed=STRUCTURED_MODES),  # type: ignore[arg-type]
        key=_stored_key(raw.get("key")),
    )


def parse_stored(raw: str | None) -> Stored:
    """A stored document, leniently: unknown keys are ignored, a wrong-typed field counts as absent, a
    document that is not JSON at all is `corrupt`."""
    if raw is None:
        return Stored()
    try:
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError("not an object")
    except ValueError:
        return Stored(corrupt=True)
    roles: dict[Role, StoredRole] = {}
    raw_roles = document.get("roles")
    for name in ROLES:
        item = raw_roles.get(name) if isinstance(raw_roles, dict) else None
        if not isinstance(item, dict):
            continue
        own = item.get("connection")
        roles[name] = StoredRole(
            model=_text(item.get("model")),
            reasoning_effort=_text(item.get("reasoning_effort"), allowed=("", *EFFORTS)),
            voice_transcription_model=_text(item.get("transcription_model")),
            connection=_stored_connection(own) if isinstance(own, dict) else None,
        )
    return Stored(default=_stored_connection(document.get("default")), roles=roles)


def _dump_connection(c: StoredConnection) -> dict[str, object]:
    out: dict[str, object] = {}
    if c.base_url is not None:
        out["base_url"] = c.base_url
    if c.api_style is not None:
        out["api_style"] = c.api_style
    if c.structured is not None:
        out["structured"] = c.structured
    out["key"] = {"ct": c.key.ct, "last4": c.key.last4} if c.key else None
    return out


def dump_stored(stored: Stored) -> str:
    roles: dict[str, object] = {}
    for name, item in stored.roles.items():
        entry: dict[str, object] = {}
        if item.model is not None:
            entry["model"] = item.model
        if item.reasoning_effort is not None:
            entry["reasoning_effort"] = item.reasoning_effort
        if item.voice_transcription_model is not None:
            entry["transcription_model"] = item.voice_transcription_model
        entry["connection"] = _dump_connection(item.connection) if item.connection else None
        roles[name] = entry
    return json.dumps({"v": 1, "default": _dump_connection(stored.default), "roles": roles}, ensure_ascii=False)


def _urls_usable(stored: Stored) -> bool:
    """A stored address that does not validate means the document was edited by hand: it is ignored as a
    whole, so a key stored beside it is never sent to a default host by mistake."""
    urls = [stored.default.base_url, *(r.connection.base_url for r in stored.roles.values() if r.connection)]
    try:
        for url in urls:
            if url:
                normalise_base_url(url)
    except InvalidAiSettings:
        return False
    return True


# ------------------------------------------------------------------ what is in force


@dataclass(frozen=True)
class FieldValue(Generic[T]):
    value: T
    source: Source


@dataclass(frozen=True)
class KeyState:
    source: KeySource
    last4: str | None
    unreadable: bool
    value: str | None = field(default=None, repr=False)  # never leaves the service


@dataclass(frozen=True)
class ConnectionState:
    base_url: FieldValue[str]
    api_style: FieldValue[ApiStyle]
    structured: FieldValue[StructuredMode]
    key: KeyState

    def to_connection(self) -> Connection:
        return Connection(self.base_url.value, self.key.value, self.api_style.value, self.structured.value)


@dataclass(frozen=True)
class RoleState:
    role: Role
    model: FieldValue[str]
    effort: FieldValue[Effort | None]
    voice_transcription_model: FieldValue[str] | None
    own: ConnectionState | None  # None: the role uses the default connection
    connection: ConnectionState  # the one in force: `own`, else the default
    resolved: bool

    @property
    def uses_default(self) -> bool:
        return self.own is None


@dataclass(frozen=True)
class Resolved:
    config: AiConfig | None
    default: ConnectionState
    roles: dict[Role, RoleState]
    missing: list[str]  # why the instance is not configured, for startup logs and scripts


def _pick(env: T | None, stored: T | None, default: T) -> FieldValue[T]:
    """The first of the environment's value, the stored one and the built-in default."""
    if env:
        return FieldValue(env, "environment")
    if stored:
        return FieldValue(stored, "stored")
    return FieldValue(default, "default")


def _env_key_state(value: str | None) -> KeyState:
    return KeyState("environment", value[-4:], False, value) if value else KeyState("none", None, False)


def _stripped(value: str | None) -> str | None:
    return (value or "").strip() or None


class Resolver:
    def __init__(self, settings: Settings, repo: AppSettingsRepository | None, cipher: Cipher | None) -> None:
        self._s = settings
        self._repo = repo
        self._cipher = cipher

    # ---- environment

    def _set(self, name: str) -> bool:
        return name in self._s.model_fields_set

    def _env_text(self, name: str) -> str | None:
        """An environment value that says something: set, and not blank."""
        if not self._set(name):
            return None
        return str(getattr(self._s, name) or "").strip() or None

    def _env_url(self, name: str) -> str | None:
        raw = self._env_text(name)
        if raw is None:
            return None
        try:
            return normalise_base_url(raw, name.upper())
        except InvalidAiSettings as exc:
            raise AiConfigError(f"{name.upper()} is not a usable http(s) address") from exc

    # ---- stored keys

    def _decrypt(self, key: StoredKey | None, context: str) -> tuple[str | None, bool]:
        """(plaintext, unreadable). A key that cannot be decrypted counts as absent, loudly."""
        if key is None:
            return None, False
        if self._cipher is None:
            return None, True
        try:
            return self._cipher.decrypt(key.ct, context=context), False
        except (CipherError, ValueError):
            return None, True

    def _stored_key_state(self, key: StoredKey | None, context: str) -> KeyState:
        """A stored key as a state: its plaintext and last four, or none (unreadable when it cannot be decrypted)."""
        plain, unreadable = self._decrypt(key, context)
        if plain and key:
            return KeyState("stored", key.last4 or plain[-4:], False, plain)
        return KeyState("none", None, unreadable)

    def _legacy_key_state(self) -> KeyState:
        """The key spec 013 stored, if any: a row that is not a key counts as unreadable."""
        raw = self._repo.get(LEGACY_SETTING) if self._repo else None
        if raw is None:
            return KeyState("none", None, False)
        try:
            key = _stored_key(json.loads(raw))
        except ValueError:
            key = None
        return self._stored_key_state(key, LEGACY_CONTEXT) if key else KeyState("none", None, True)

    # ---- one connection

    def _default_connection(self, stored: Stored) -> ConnectionState:
        s, sc = self._s, stored.default
        key = _env_key_state(self._env_text("openai_api_key"))
        if key.source == "none":
            key = self._stored_key_state(sc.key, key_context("default"))
            if sc.key is None:  # no key in the new document: the one spec 013 stored, if any
                key = self._legacy_key_state()
        return ConnectionState(
            _pick(self._env_url("openai_base_url"), normalise_base_url(sc.base_url) if sc.base_url else None, OPENAI_BASE_URL),
            _pick(s.ai_api_style if self._set("ai_api_style") else None, sc.api_style, "responses"),
            _pick(s.ai_structured_outputs if self._set("ai_structured_outputs") else None, sc.structured, "schema"),
            key,
        )

    def _own_connection(self, role: Role, stored: Stored) -> ConnectionState | None:
        s = self._s
        env_url = self._env_url(f"{role}_base_url")
        if env_url:  # the whole connection of this role is the environment's
            return ConnectionState(
                FieldValue(env_url, "environment"),
                FieldValue(getattr(s, f"{role}_api_style"), "environment"),
                FieldValue(getattr(s, f"{role}_structured_outputs"), "environment"),
                _env_key_state(self._env_text(f"{role}_api_key")),
            )
        sc = stored.role(role).connection
        if sc is None or not sc.base_url:
            return None
        return ConnectionState(
            FieldValue(normalise_base_url(sc.base_url), "stored"),
            FieldValue(sc.api_style or "responses", "stored"),
            FieldValue(sc.structured or "schema", "stored"),
            self._stored_key_state(sc.key, key_context(role)),
        )

    # ---- one role

    def _role(self, role: Role, stored: Stored, default: ConnectionState) -> RoleState:
        s, sr = self._s, stored.role(role)
        model = _pick(self._env_text(MODEL_FIELD[role]), _stripped(sr.model), DEFAULT_MODELS[role])
        voice_model = (
            _pick(
                self._env_text("voice_transcription_model"),
                _stripped(sr.voice_transcription_model),
                DEFAULT_VOICE_TRANSCRIPTION_MODEL,
            )
            if role == "voice"
            else None
        )
        own = self._own_connection(role, stored)
        connection = own or default
        resolved_connection = connection.to_connection()
        effort: FieldValue[Effort | None]
        if self._set(EFFORT_FIELD[role]):
            effort = FieldValue(getattr(s, EFFORT_FIELD[role]) or None, "environment")
        elif sr.reasoning_effort is not None:
            effort = FieldValue(sr.reasoning_effort or None, "stored")  # type: ignore[arg-type]
        else:
            # The tuned defaults are OpenAI's: `low` and `medium` are values another provider's models may
            # refuse (Qwen's on Groq take only « default » or « none »). Elsewhere nothing is sent unless
            # the administrator chooses.
            effort = FieldValue(DEFAULT_EFFORTS[role] if resolved_connection.is_openai else None, "default")
        if role == "voice":
            # Realtime is not guessed to work on another server: voice follows the default connection only
            # when that is OpenAI's, else it needs a connection of its own.
            resolved = bool(
                s.voice_enabled and model.value and resolved_connection.usable
                and (own is not None or default.to_connection().is_openai)
            )
        else:
            resolved = bool(model.value and resolved_connection.usable)
        return RoleState(role, model, effort, voice_model, own, connection, resolved)

    # ---- everything

    def resolve(self) -> Resolved:
        raw = self._repo.get(SETTING) if self._repo else None
        stored = parse_stored(raw)
        if not stored.corrupt and not _urls_usable(stored):
            stored = Stored(corrupt=True)
        if stored.corrupt:
            log.warning("ai_settings_unreadable", extra={"reason": "document"})
        default = self._default_connection(stored)
        roles = {role: self._role(role, stored, default) for role in ROLES}
        missing = [
            f"{role}: no model or no usable connection ({roles[role].connection.base_url.value})"
            for role in ("tutor", "authoring", "transcription")
            if not roles[role].resolved
        ]
        config = None if missing else self._config(roles)
        return Resolved(config, default, roles, missing)

    @staticmethod
    def _dictation(voice: RoleState) -> DictationConfig | None:
        """Dictation rides on the voice role's speech model and connection, without needing Realtime. As for
        voice, it is not guessed to work on a server that is not OpenAI's: there it needs a connection of its
        own or a speech model somebody chose (Groq's `whisper-large-v3-turbo`, say)."""
        speech = voice.voice_transcription_model
        connection = voice.connection.to_connection()
        if speech is None or not speech.value or not connection.usable:
            return None
        if not (voice.own is not None or connection.is_openai or speech.source != "default"):
            return None
        return DictationConfig(speech.value, connection)

    def _config(self, roles: dict[Role, RoleState]) -> AiConfig:
        def role_config(state: RoleState) -> RoleConfig:
            return RoleConfig(
                role=state.role,
                model=state.model.value,
                reasoning_effort=state.effort.value,
                connection=state.connection.to_connection(),
                voice_transcription_model=state.voice_transcription_model.value if state.voice_transcription_model else None,
            )

        voice = roles["voice"]
        dictation = self._dictation(voice) if self._s.dictation_enabled else None
        return AiConfig(
            tutor=role_config(roles["tutor"]),
            authoring=role_config(roles["authoring"]),
            transcription=role_config(roles["transcription"]),
            voice=role_config(voice) if voice.resolved else None,
            dictation=dictation,
        )
