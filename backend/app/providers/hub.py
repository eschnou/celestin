"""The clients behind one configuration that can change at runtime (spec 013 §3.6, spec 014 §3.5).

Everything that talks to a provider holds one of three *proxies* (`hub.llm`, `hub.authoring_llm`,
`hub.realtime`). A proxy looks up the hub's current clients each time it is called, so applying a new
configuration swaps the clients under the proxies and nothing that captured a proxy (the authoring agent,
the dependencies, a test's override) has to change. A call that already resolved its client finishes with
it; the next call uses the new one. With no configuration, a call raises `AiNotConfigured`.
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.config import Settings
from app.domain.ai_config import AiConfig, RoleConfig
from app.domain.errors import AiNotConfigured, DictationDisabled, VoiceDisabled
from app.providers.base import (
    ClientSecret,
    CompletionClient,
    CompletionResult,
    LLMClient,
    ProviderEvent,
    RealtimeClient,
    Transcript,
    TranscriptionClient,
)
from app.providers.openai_chat import OpenAIChatClient
from app.providers.openai_realtime import OpenAIRealtimeClient
from app.providers.openai_responses import OpenAIResponsesClient
from app.providers.openai_transcription import OpenAITranscriptionClient


@dataclass(frozen=True)
class Clients:
    config: AiConfig
    tutor: LLMClient
    authoring: CompletionClient
    transcription: CompletionClient
    realtime: RealtimeClient | None  # None: voice is off
    transcriber: TranscriptionClient | None = None  # None: dictation is off

    def __repr__(self) -> str:
        return "Clients(…)"


ClientFactory = Callable[[Settings, AiConfig], Clients]


def _role_client(role: RoleConfig, timeout_s: float) -> Any:
    """The adapter for the role's API style: Responses (OpenAI and the servers that copy it) or Chat Completions."""
    connection = role.connection
    adapter = OpenAIChatClient if connection.api_style == "chat" else OpenAIResponsesClient
    return adapter(connection, role.model, timeout_s, reasoning_effort=role.reasoning_effort)


def build_clients(settings: Settings, config: AiConfig) -> Clients:
    """One client per role, each with its own connection, model and timeout: the tutor's streaming client,
    the authoring and transcription clients (the latter reads documents) and, when voice is on, the Realtime
    client."""
    voice = config.voice
    return Clients(
        config=config,
        tutor=_role_client(config.tutor, settings.request_timeout_s),
        authoring=_role_client(config.authoring, settings.authoring_call_timeout_s),
        transcription=_role_client(config.transcription, settings.authoring_call_timeout_s),
        realtime=OpenAIRealtimeClient(voice.connection, settings.request_timeout_s) if voice else None,
        transcriber=(
            OpenAITranscriptionClient(dictation.connection, dictation.model, settings.request_timeout_s)
            if (dictation := config.dictation)
            else None
        ),
    )


class _LLMProxy:
    def __init__(self, hub: ProviderHub) -> None:
        self._hub = hub

    @property
    def model(self) -> str:
        clients = self._hub.clients
        return clients.tutor.model if clients else ""

    def stream(
        self, *, input: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AbstractAsyncContextManager[AsyncIterator[ProviderEvent]]:
        return self._hub.current().tutor.stream(input=input, tools=tools)


class _CompletionProxy:
    def __init__(self, hub: ProviderHub) -> None:
        self._hub = hub

    async def complete(
        self,
        *,
        role: Literal["authoring", "transcription"],
        instructions: list[str],
        input: list[dict[str, Any]],
        schema: type[BaseModel] | None = None,
        schema_name: str | None = None,
        max_output_tokens: int,
    ) -> CompletionResult:
        clients = self._hub.current()
        client = clients.transcription if role == "transcription" else clients.authoring
        return await client.complete(
            role=role,
            instructions=instructions,
            input=input,
            schema=schema,
            schema_name=schema_name,
            max_output_tokens=max_output_tokens,
        )


class _RealtimeProxy:
    def __init__(self, hub: ProviderHub) -> None:
        self._hub = hub

    async def create_client_secret(self, *, session: dict[str, Any], ttl_s: int) -> ClientSecret:
        realtime = self._hub.current().realtime
        if realtime is None:
            raise VoiceDisabled()
        return await realtime.create_client_secret(session=session, ttl_s=ttl_s)


class _TranscriptionProxy:
    def __init__(self, hub: ProviderHub) -> None:
        self._hub = hub

    async def transcribe(
        self, *, audio: bytes, filename: str, content_type: str, language: str | None = None
    ) -> Transcript:
        transcriber = self._hub.current().transcriber
        if transcriber is None:
            raise DictationDisabled()
        return await transcriber.transcribe(
            audio=audio, filename=filename, content_type=content_type, language=language
        )


class ProviderHub:
    def __init__(self, settings: Settings, factory: ClientFactory = build_clients) -> None:
        self._settings = settings
        self._factory = factory
        self._lock = threading.Lock()
        self._clients: Clients | None = None
        self.llm: LLMClient = _LLMProxy(self)
        self.authoring_llm: CompletionClient = _CompletionProxy(self)
        self.realtime: RealtimeClient = _RealtimeProxy(self)
        self.transcriber: TranscriptionClient = _TranscriptionProxy(self)

    @property
    def clients(self) -> Clients | None:
        return self._clients  # one read: a swap in between cannot give a half-new set

    @property
    def configured(self) -> bool:
        return self._clients is not None

    @property
    def config(self) -> AiConfig | None:
        clients = self._clients
        return clients.config if clients else None

    @property
    def voice_available(self) -> bool:
        clients = self._clients
        return clients is not None and clients.realtime is not None

    @property
    def dictation_available(self) -> bool:
        clients = self._clients
        return clients is not None and clients.transcriber is not None

    def current(self) -> Clients:
        clients = self._clients
        if clients is None:
            raise AiNotConfigured()
        return clients

    def build(self, config: AiConfig | None) -> Clients | None:
        """The clients of a configuration, not yet in force: a configuration that cannot be built raises
        here, before anything is stored."""
        return self._factory(self._settings, config) if config else None

    def install(self, clients: Clients | None) -> None:
        """Swap a built set in, in one assignment. `None` unconfigures."""
        with self._lock:
            self._clients = clients

    def apply(self, config: AiConfig | None) -> None:
        """Build every client, then swap them in. A configuration that cannot be built leaves the previous
        clients in force."""
        self.install(self.build(config))
