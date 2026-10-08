"""Chat Completions adapter: servers that speak OpenAI's chat API and not its Responses API (spec 014 §3.5).

llama.cpp, LM Studio, text-generation-webui, many gateways. The application's items stay Responses-shaped;
`chat_translate` turns them into messages, this module streams and completes. The only other module that
imports `openai` for completions is `openai_responses.py`; nothing above `app/providers/` may.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import openai
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from app.domain.ai_config import Connection, Effort, StructuredMode
from app.domain.errors import ProviderOutputInvalid, ProviderOutputTruncated, ProviderUnavailable
from app.providers._client import make_client
from app.providers.base import (
    Completed,
    CompletionResult,
    Failed,
    ProgressCallback,
    ProviderEvent,
    StreamBroken,
    StreamLimits,
    TextDelta,
    ToolCallRequested,
)
from app.providers.chat_translate import (
    ThinkStripper,
    extract_json,
    json_instruction,
    strip_think,
    to_messages,
    to_tools,
    usage_dict,
)
from app.providers.streaming import CallStats, consume, fail, log_done

log = logging.getLogger(__name__)


class OpenAIChatClient:
    """One role's client over `chat/completions`: its connection, model, reasoning effort and structured mode."""

    def __init__(
        self,
        connection: Connection,
        model: str,
        timeout_s: float,
        reasoning_effort: Effort | None = None,
        limits: StreamLimits | None = None,
    ) -> None:
        self._client = make_client(connection, timeout_s)
        self._limits = limits or StreamLimits(timeout_s, timeout_s)
        self._connection = connection
        self._model = model
        self._effort = reasoning_effort
        self._structured: StructuredMode = connection.structured
        # The output limit's name: `max_completion_tokens` (current), or `max_tokens` for a server that only
        # knows the older one. Learned from the server's refusal, once.
        self._limit_param = "max_completion_tokens"

    @property
    def model(self) -> str:
        return self._model

    # ------------------------------------------------------------------ streaming

    @asynccontextmanager
    async def stream(
        self,
        *,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[AsyncIterator[ProviderEvent]]:
        stats = CallStats.begin()
        try:
            request: dict[str, Any] = {
                "model": self._model,
                "messages": to_messages(input),
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if tools:
                request["tools"] = to_tools(tools, openai=self._connection.is_openai)
            if self._effort:
                request["reasoning_effort"] = self._effort
            raw = await self._client.chat.completions.create(**request)
            async with raw:
                yield _map_chunks(raw)
        except Exception as exc:  # noqa: BLE001 - translated, logged with its class and duration, re-raised
            fail(exc, role="tutor", model=self._model, host=self._connection.host, stats=stats, only_provider=True)

    # ------------------------------------------------------------------ one-shot

    async def complete(
        self,
        *,
        role: str,
        instructions: list[str],
        input: list[dict[str, Any]],
        schema: type[BaseModel] | None = None,
        schema_name: str | None = None,
        max_output_tokens: int,
        on_progress: ProgressCallback | None = None,
    ) -> CompletionResult:
        """One call, streamed (spec 016): the answer is assembled from the chunks and judged as a whole response
        was. `role` was used to pick this client."""
        texts = list(instructions)
        if schema is not None and self._structured == "json":
            texts.append(json_instruction(schema.model_json_schema()))
        request: dict[str, Any] = {
            "model": self._model,
            "messages": to_messages(input, system="\n\n".join(texts)),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if schema is not None:
            request["response_format"] = (
                {"type": "json_object"}
                if self._structured == "json"
                else {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name or schema.__name__,
                        "schema": to_strict_json_schema(schema),
                        "strict": True,
                    },
                }
            )
        if self._effort:
            request["reasoning_effort"] = self._effort
        stats = CallStats.begin()
        parts: list[str] = []
        usage: dict[str, Any] = {}
        finish: str | None = None

        def handle(chunk: Any) -> None:
            nonlocal usage, finish
            if getattr(chunk, "usage", None) is not None:
                usage = usage_dict(chunk.usage)
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None) if delta is not None else None
                if content:  # a model's reasoning deltas are events (activity), not characters of the answer
                    parts.append(content)
                    stats.received_chars += len(content)
                if getattr(choice, "finish_reason", None):
                    finish = choice.finish_reason

        async def read(limit_param: str) -> None:
            await consume(
                lambda: self._client.chat.completions.create(**request, **{limit_param: max_output_tokens}),
                handle,
                limits=self._limits,
                stats=stats,
                on_progress=on_progress,
            )

        try:
            try:
                await read(self._limit_param)
            except openai.BadRequestError as exc:
                if self._limit_param != "max_completion_tokens" or "max_completion_tokens" not in str(exc):
                    raise
                self._limit_param = "max_tokens"
                log.info("chat_limit_param", extra={"param": self._limit_param})
                await read(self._limit_param)
            if finish is None:
                raise StreamBroken("stream_ended", ProviderUnavailable.code)
            result = chat_finish("".join(parts), finish, usage, parse_json=schema is not None)
        except Exception as exc:  # noqa: BLE001 - translated, logged with its class and duration, re-raised
            fail(exc, role=role, model=self._model, host=self._connection.host, stats=stats)
        log_done(role=role, model=self._model, host=self._connection.host, stats=stats, usage=result.usage)
        return result


def chat_result(response: Any, *, parse_json: bool) -> CompletionResult:
    """A whole (non-streamed) response, judged by `chat_finish`."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ProviderUnavailable()
    choice = choices[0]
    return chat_finish(
        getattr(choice.message, "content", None) or "",
        getattr(choice, "finish_reason", None),
        usage_dict(getattr(response, "usage", None)),
        parse_json=parse_json,
    )


def chat_finish(text: str, finish: str | None, usage: dict[str, Any], *, parse_json: bool) -> CompletionResult:
    """An answer's text, how it ended and what it was billed, turned into a result or the error it deserves:
    the one judgement a streamed and a whole response share."""
    if finish == "length":
        raise ProviderOutputTruncated("length", usage)
    text = strip_think(text)
    data = None
    if parse_json:
        try:
            data = json.loads(extract_json(text))
        except ValueError as exc:
            raise ProviderOutputInvalid(str(exc), usage) from exc
        if not isinstance(data, dict):
            raise ProviderOutputInvalid("not a JSON object", usage)
    return CompletionResult(text=text, data=data, usage=usage)


async def _map_chunks(raw: AsyncIterator[Any]) -> AsyncIterator[ProviderEvent]:
    """Map Chat Completions chunks onto the provider-neutral events.

    Text goes out as it comes (minus a model's visible thinking); a tool call is assembled from its
    fragments, by index, and emitted once the stream ends, like Responses' `.done`: a tool cannot run on
    partial JSON. The finish reason says whether the answer is whole.
    """
    stripper = ThinkStripper()
    calls: dict[int, dict[str, Any]] = {}
    usage: dict[str, Any] = {}
    finish: str | None = None
    async for chunk in raw:
        if getattr(chunk, "usage", None) is not None:
            usage = usage_dict(chunk.usage)
        for choice in getattr(chunk, "choices", None) or []:
            delta = getattr(choice, "delta", None)
            text = getattr(delta, "content", None) if delta is not None else None
            if text:
                visible = stripper.feed(text)
                if visible:
                    yield TextDelta(visible)
            for fragment in (getattr(delta, "tool_calls", None) or []) if delta is not None else []:
                slot = calls.setdefault(int(getattr(fragment, "index", 0) or 0), {"id": "", "name": "", "args": []})
                if getattr(fragment, "id", None):
                    slot["id"] = fragment.id
                function = getattr(fragment, "function", None)
                if function is not None:
                    if getattr(function, "name", None) and not slot["name"]:
                        slot["name"] = function.name
                    if getattr(function, "arguments", None):
                        slot["args"].append(function.arguments)
            if getattr(choice, "finish_reason", None):
                finish = choice.finish_reason
    tail = stripper.flush()
    if tail:
        yield TextDelta(tail)
    if finish is None:
        yield Failed(code=ProviderUnavailable.code, message="the stream ended before a finish reason")
        return
    if finish == "length":
        yield Failed(code=ProviderUnavailable.code, message="output limit reached")
        return
    for index in sorted(calls):
        slot = calls[index]
        yield ToolCallRequested(
            call_id=slot["id"] or f"call_{index}", name=slot["name"], arguments_json="".join(slot["args"]) or "{}"
        )
    yield Completed(usage=usage)
