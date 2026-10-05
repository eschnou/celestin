"""Recording wrappers: one ledger row per provider call (spec 015 §3.2).

The hub puts these around the clients it builds (`ProviderHub.build`), so they cover the proxies the application
holds, the clients the admin's live test calls directly and every scripted fake. A wrapper keeps its protocol's
signature: it times the call, keeps the last usage block the provider sent, and when the call ends hands one
`UsageEntry` to the sink. *Who* the call is for comes from the usage scope (`app/domain/usage.py`), read when the
call starts; a call outside any scope is not recorded.

A wrapper never reads what it carries: not the input, the instructions, the tools, the answer, nor an exception's
message. An entry holds ids, enumerations, a model name, a host name and numbers, so nothing a student wrote or
said can reach the ledger. Recording can never fail or delay a call: building an entry and the sink are guarded,
and the production sink writes off the event loop.

Imports nothing from `app.db` (the sink is injected).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel

from app.domain.ai_config import Role
from app.domain.errors import ProviderOutputInvalid, ProviderOutputTruncated, TutorError
from app.domain.usage import Status, UsageEntry, UsageScope, current_scope, feature_of, read_usage
from app.providers.base import (
    Completed,
    CompletionClient,
    CompletionResult,
    Failed,
    LLMClient,
    ProviderEvent,
    TextDelta,
    Transcript,
    TranscriptionClient,
)

if TYPE_CHECKING:
    from app.providers.hub import Clients

log = logging.getLogger(__name__)

MAX_CODE_CHARS = 40


class UsageSink(Protocol):
    def record(self, entry: UsageEntry) -> None:
        """Take one entry. Never raises."""


class UsageRecorder:
    """The production sink: each entry is written on the loop's default executor, after the call has ended, so a
    streamed turn's events are never held up by the database and a cancelled task can still hand its row over
    (submitting does not await). A failed write is a log line."""

    def __init__(self, write: Callable[[UsageEntry], None]) -> None:
        self._write = write
        self._pending: set[asyncio.Future[None]] = set()

    def record(self, entry: UsageEntry) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # a synchronous caller: nothing to hold up
            self._write_safely(entry)
            return
        future = loop.run_in_executor(None, self._write_safely, entry)
        self._pending.add(future)
        future.add_done_callback(self._pending.discard)

    def _write_safely(self, entry: UsageEntry) -> None:
        try:
            self._write(entry)
        except Exception as exc:  # noqa: BLE001 - the ledger is best effort: a lost row is a log line
            # The class only: a database error's message carries the bound values.
            log.error("ai_usage_not_stored", extra={"error": type(exc).__name__, "role": entry.role})

    async def drain(self) -> None:
        """Wait for the writes in flight (shutdown, tests)."""
        while self._pending:
            done = list(self._pending)
            await asyncio.gather(*done, return_exceptions=True)
            self._pending.difference_update(done)  # the done-callbacks may not have run yet: do not spin on them


def _code(exc: BaseException) -> str:
    """The application's own error code of a failure, never the provider's text: only our own errors have one."""
    code = getattr(exc, "code", None) if isinstance(exc, (TutorError, ProviderOutputInvalid)) else None
    return code[:MAX_CODE_CHARS] if isinstance(code, str) and code else "unknown"


@dataclass
class _Call:
    """What is known when a call starts."""

    scope: UsageScope | None
    started: float
    at: datetime


class _Recording:
    def __init__(self, role: Role, model: str, host: str, sink: UsageSink) -> None:
        self._role = role
        self._model = model
        self._host = host
        self._sink = sink

    def _begin(self) -> _Call:
        return _Call(scope=current_scope(), started=time.monotonic(), at=datetime.now(UTC))

    def _emit(
        self,
        call: _Call,
        status: Status,
        error_code: str | None = None,
        *,
        usage: dict[str, Any] | None = None,
        ttft_ms: int | None = None,
        ended: float | None = None,
    ) -> None:
        scope = call.scope
        if scope is None:
            log.debug("ai_usage_unscoped", extra={"role": self._role})
            return
        try:
            numbers = read_usage(usage)
            self._sink.record(
                UsageEntry(
                    created_at=call.at,
                    user_id=scope.user_id,
                    course_id=scope.course_id,
                    chapter_id=scope.chapter_id,
                    correlation_id=scope.correlation_id,
                    role=self._role,
                    feature=feature_of(scope, self._role),
                    model=self._model,
                    provider=self._host,
                    status=status,
                    error_code=error_code,
                    latency_ms=round(((ended if ended is not None else time.monotonic()) - call.started) * 1000),
                    ttft_ms=ttft_ms,
                    input_tokens=numbers.input_tokens,
                    cached_tokens=numbers.cached_tokens,
                    output_tokens=numbers.output_tokens,
                    reasoning_tokens=numbers.reasoning_tokens,
                    audio_seconds=scope.audio_seconds,
                    cost_usd=numbers.cost_usd,
                )
            )
        except Exception as exc:  # noqa: BLE001 - recording must never fail the call it describes
            log.error("ai_usage_not_stored", extra={"error": type(exc).__name__, "role": self._role})


class _Seen:
    """What a stream showed: when the first text came, the last usage, whether it failed."""

    def __init__(self, started: float) -> None:
        self._started = started
        self.first_text_at: float | None = None
        self.usage: dict[str, Any] | None = None
        self.completed = False
        self.failed: str | None = None
        self.ended_at: float | None = None  # when the provider's stream ended: the consumer's time is not the call's

    @property
    def ttft_ms(self) -> int | None:
        return None if self.first_text_at is None else round((self.first_text_at - self._started) * 1000)

    def outcome(self) -> tuple[Status, str | None]:
        if self.failed is not None:
            return "failed", self.failed
        return ("ok", None) if self.completed else ("cancelled", None)

    @property
    def finished(self) -> bool:
        """The provider said how the call ended."""
        return self.completed or self.failed is not None

    async def watch(self, events: AsyncIterator[ProviderEvent]) -> AsyncIterator[ProviderEvent]:
        async for event in events:
            if isinstance(event, TextDelta) and self.first_text_at is None:
                self.first_text_at = time.monotonic()
            elif isinstance(event, Completed):
                self.completed = True
                self.usage = event.usage
                self.ended_at = time.monotonic()
            elif isinstance(event, Failed):
                self.failed = event.code[:MAX_CODE_CHARS] or "unknown"
                self.ended_at = time.monotonic()
            yield event


class RecordingLLM(_Recording):
    """The tutor's streaming client, recording each round as one call."""

    def __init__(self, inner: LLMClient, *, model: str, host: str, sink: UsageSink) -> None:
        super().__init__("tutor", model, host, sink)
        self._inner = inner

    @property
    def model(self) -> str:
        return self._inner.model

    @asynccontextmanager
    async def stream(
        self, *, input: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncIterator[AsyncIterator[ProviderEvent]]:
        call = self._begin()
        seen = _Seen(call.started)
        outcome: tuple[Status, str | None] = ("cancelled", None)  # what a cut-short stream is
        try:
            async with self._inner.stream(input=input, tools=tools) as events:
                yield seen.watch(events)
            outcome = seen.outcome()
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except Exception as exc:
            # The provider's own word on how the call ended stands: a consumer that fails after `Completed` did not
            # make a billed, finished call a failed one.
            outcome = seen.outcome() if seen.finished else ("failed", _code(exc))
            raise
        finally:
            self._emit(call, *outcome, usage=seen.usage, ttft_ms=seen.ttft_ms, ended=seen.ended_at)


class RecordingCompletion(_Recording):
    """One role's one-shot client (authoring or transcription), recording each call."""

    def __init__(self, inner: CompletionClient, *, role: Literal["authoring", "transcription"], model: str, host: str, sink: UsageSink) -> None:
        super().__init__(role, model, host, sink)
        self._inner = inner

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
        call = self._begin()
        try:
            result = await self._inner.complete(
                role=role,
                instructions=instructions,
                input=input,
                schema=schema,
                schema_name=schema_name,
                max_output_tokens=max_output_tokens,
            )
        except asyncio.CancelledError:
            self._emit(call, "cancelled")
            raise
        except Exception as exc:
            # An answer that came but could not be used was billed: its usage block is on the exception.
            truncated = isinstance(exc, ProviderOutputTruncated)
            self._emit(
                call,
                "truncated" if truncated else "failed",
                None if truncated else _code(exc),
                usage=getattr(exc, "usage", None),
            )
            raise
        self._emit(call, "ok", usage=result.usage)
        return result


class RecordingTranscriber(_Recording):
    """Dictation's speech-to-text client, recorded under the voice role: its audio length comes from the scope."""

    def __init__(self, inner: TranscriptionClient, *, model: str, host: str, sink: UsageSink) -> None:
        super().__init__("voice", model, host, sink)
        self._inner = inner

    async def transcribe(
        self, *, audio: bytes, filename: str, content_type: str, language: str | None = None
    ) -> Transcript:
        call = self._begin()
        try:
            transcript = await self._inner.transcribe(
                audio=audio, filename=filename, content_type=content_type, language=language
            )
        except asyncio.CancelledError:
            self._emit(call, "cancelled")
            raise
        except Exception as exc:
            self._emit(call, "failed", _code(exc))
            raise
        self._emit(call, "ok")
        return transcript


def record_clients(clients: Clients, sink: UsageSink) -> Clients:
    """The same clients, each behind its recording wrapper. The Realtime client is left alone: minting a secret
    is not a billable call, and a voice session is recorded from the browser's report."""
    config = clients.config
    transcriber = clients.transcriber
    if transcriber is not None and config.dictation is not None:
        transcriber = RecordingTranscriber(
            transcriber, model=config.dictation.model, host=config.dictation.connection.host, sink=sink
        )
    return replace(
        clients,
        tutor=RecordingLLM(clients.tutor, model=config.tutor.model, host=config.tutor.connection.host, sink=sink),
        authoring=RecordingCompletion(
            clients.authoring, role="authoring", model=config.authoring.model,
            host=config.authoring.connection.host, sink=sink,
        ),
        transcription=RecordingCompletion(
            clients.transcription, role="transcription", model=config.transcription.model,
            host=config.transcription.connection.host, sink=sink,
        ),
        transcriber=transcriber,
    )
