"""The provider boundary (design 3.3).

Everything above this module talks to `LLMClient` and knows nothing about any
vendor. That is what lets the turn loop be tested offline against a scripted fake.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.domain.ai_config import AiConfig, Connection


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallRequested:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True)
class Completed:
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Failed:
    code: str
    message: str


ProviderEvent = TextDelta | ToolCallRequested | Completed | Failed


class LLMClient(Protocol):
    @property
    def model(self) -> str: ...

    def stream(
        self,
        *,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AbstractAsyncContextManager[AsyncIterator[ProviderEvent]]: ...


@dataclass(frozen=True)
class CompletionResult:
    """One non-streamed answer (005 design 3.7). `data` is the parsed JSON when a
    schema was asked for; its shape is not validated here."""

    text: str
    data: dict[str, Any] | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class CompletionClient(Protocol):
    """One-shot calls. The client of a role owns its model, its reasoning effort and its structured-output
    mode (spec 014): the caller says which role it is, not which model."""

    async def complete(
        self,
        *,
        role: Literal["authoring", "transcription"],
        instructions: list[str],
        input: list[dict[str, Any]],
        schema: type[BaseModel] | None = None,
        schema_name: str | None = None,
        max_output_tokens: int,
    ) -> CompletionResult: ...


@dataclass(frozen=True)
class ClientSecret:
    """An ephemeral Realtime credential for the browser (003 design 3.7)."""

    value: str
    expires_at: int


class RealtimeClient(Protocol):
    async def create_client_secret(
        self, *, session: dict[str, Any], ttl_s: int
    ) -> ClientSecret: ...


@dataclass(frozen=True)
class Transcript:
    """What was said in one recording. Empty when nothing intelligible was."""

    text: str


class TranscriptionClient(Protocol):
    """Speech to text for dictation. The client owns its model and connection."""

    async def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        language: str | None = None,
    ) -> Transcript: ...


@dataclass(frozen=True)
class ModelVisibility:
    """Whether a connection can see a model. `None`: it cannot tell (a restricted key, no listing)."""

    model: str
    visible: bool | None


@dataclass(frozen=True)
class ProbeResult:
    """What a server says about a connection (spec 013 §3.6, spec 014 §3.5). `limited`: it authenticates but
    cannot list models (a restricted key, a server with no models route), which does not make it unusable.
    `available`: the model ids it lists, for suggestions."""

    status: Literal["ok", "rejected", "unreachable"]
    limited: bool = False
    models: list[ModelVisibility] = field(default_factory=list)
    available: list[str] = field(default_factory=list)


class ConnectionProbe(Protocol):
    async def check(self, connection: Connection, models: Sequence[str] = ()) -> ProbeResult: ...


class AiConfigSource(Protocol):
    """What services read the models from: the hub, or any object with its current configuration."""

    @property
    def config(self) -> AiConfig | None: ...
