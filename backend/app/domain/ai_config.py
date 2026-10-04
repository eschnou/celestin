"""What the application talks to: a connection per role (spec 014 §3.1).

Pure data and validation. Nothing here knows the SDK, the database or the environment: the settings
service resolves an `AiConfig`, the provider hub builds clients from it.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, get_args
from urllib.parse import urlsplit, urlunsplit

from app.domain.errors import InvalidAiSettings

if TYPE_CHECKING:
    from app.config import Settings

Role = Literal["tutor", "authoring", "transcription", "voice"]
ROLES: tuple[Role, ...] = ("tutor", "authoring", "transcription", "voice")
ApiStyle = Literal["responses", "chat"]
StructuredMode = Literal["schema", "json"]
Effort = Literal["low", "medium", "high"]
EFFORTS: tuple[str, ...] = get_args(Effort)
API_STYLES: tuple[str, ...] = get_args(ApiStyle)
STRUCTURED_MODES: tuple[str, ...] = get_args(StructuredMode)
# What a live check of the test action can find (spec 014 §3.9): a vocabulary that crosses to the interface.
LiveCode = Literal[
    "rejected",
    "unreachable",
    "model_not_found",
    "no_tool_calls",
    "tool_arguments",
    "no_image_input",
    "schema_unsupported",
    "other",
]

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_HOST = "api.openai.com"
MAX_BASE_URL_CHARS = 2048
MAX_KEY_CHARS = 256
MAX_MODEL_CHARS = 200

# What a role uses when neither the environment nor an administrator says otherwise (today's values).
DEFAULT_MODELS: dict[Role, str] = {
    "tutor": "gpt-6.1-sol",
    "authoring": "gpt-6.1-sol",
    "transcription": "gpt-6.1-sol",
    "voice": "gpt-realtime-2.1",
}
DEFAULT_EFFORTS: dict[Role, Effort | None] = {
    "tutor": None,
    "authoring": "medium",
    "transcription": "low",
    "voice": "low",
}
DEFAULT_VOICE_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"


@dataclass(frozen=True)
class Connection:
    """How to reach one server. `api_key` None: a keyless server (a local one), which gets a placeholder."""

    base_url: str
    api_key: str | None = None
    api_style: ApiStyle = "responses"
    structured: StructuredMode = "schema"

    def __repr__(self) -> str:
        return f"Connection({self.base_url!r}, {self.api_style}, {self.structured})"

    @property
    def host(self) -> str:
        return urlsplit(self.base_url).hostname or ""

    @property
    def is_openai(self) -> bool:
        return self.host == OPENAI_HOST

    @property
    def usable(self) -> bool:
        """OpenAI needs a key; a server that is not OpenAI's may not."""
        return bool(self.api_key) or not self.is_openai


@dataclass(frozen=True)
class RoleConfig:
    role: Role
    model: str
    reasoning_effort: Effort | None
    connection: Connection
    voice_transcription_model: str | None = None  # voice only


@dataclass(frozen=True)
class DictationConfig:
    """Speech to text for the composer's microphone: the voice role's speech model on a connection that
    serves `/audio/transcriptions`. Independent of Realtime: a server with no Realtime can still dictate."""

    model: str
    connection: Connection


@dataclass(frozen=True)
class AiConfig:
    tutor: RoleConfig
    authoring: RoleConfig
    transcription: RoleConfig
    voice: RoleConfig | None  # None: voice is off
    dictation: DictationConfig | None = None  # None: dictation is off

    def role(self, name: Role) -> RoleConfig | None:
        return getattr(self, name)

    def roles(self) -> list[RoleConfig]:
        return [rc for rc in (self.tutor, self.authoring, self.transcription, self.voice) if rc is not None]

    def describe(self) -> dict[str, dict[str, str]]:
        """Hosts, models and styles for the logs: never a key."""
        described = {
            rc.role: {"host": rc.connection.host, "model": rc.model, "style": rc.connection.api_style}
            for rc in self.roles()
        }
        if self.dictation:
            described["dictation"] = {"host": self.dictation.connection.host, "model": self.dictation.model, "style": ""}
        return described

    def __repr__(self) -> str:
        return f"AiConfig({self.describe()})"


def normalise_base_url(raw: str, field: str = "base_url") -> str:
    """The URL as stored: `http` or `https`, a host, no user-info, no fragment, no trailing slash.
    Private and loopback hosts are accepted on purpose (a local server is the point)."""
    value = raw.strip()
    if not value or len(value) > MAX_BASE_URL_CHARS:
        raise InvalidAiSettings([field])
    try:
        parts = urlsplit(value)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError as exc:
        raise InvalidAiSettings([field]) from exc
    if parts.scheme not in ("http", "https") or not host:
        raise InvalidAiSettings([field])
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise InvalidAiSettings([field])
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), parts.query, ""))


def _is_private_host(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or "." not in host:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def calls_url(connection: Connection) -> str:
    """Where the browser posts its SDP offer (spec 014 R10.2). `https`, or `http` for a private host."""
    url = f"{connection.base_url}/realtime/calls"
    parts = urlsplit(url)
    if parts.scheme == "http" and not _is_private_host(parts.hostname or ""):
        raise InvalidAiSettings(["voice.base_url"])
    return url


def priced(settings: Settings, connection: Connection | None, *price_fields: str) -> bool:
    """Whether a cost estimate means something (R11.2): OpenAI's own prices apply to OpenAI, anywhere else
    only prices the operator set explicitly."""
    return bool(connection and connection.is_openai) or any(name in settings.model_fields_set for name in price_fields)
