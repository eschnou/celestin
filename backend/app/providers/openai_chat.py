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
from app.providers._errors import translate as _translate
from app.providers.base import Completed, CompletionResult, Failed, ProviderEvent, TextDelta, ToolCallRequested
from app.providers.chat_translate import (
    ThinkStripper,
    extract_json,
    json_instruction,
    strip_think,
    to_messages,
    to_tools,
    usage_dict,
)

log = logging.getLogger(__name__)


class OpenAIChatClient:
    """One role's client over `chat/completions`: its connection, model, reasoning effort and structured mode."""

    def __init__(
        self,
        connection: Connection,
        model: str,
        timeout_s: float,
        reasoning_effort: Effort | None = None,
    ) -> None:
        self._client = make_client(connection, timeout_s)
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
        except Exception as exc:  # noqa: BLE001 - translated, then re-raised
            raise _translate(exc) from exc

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
    ) -> CompletionResult:
        """One non-streamed call. `role` was used to pick this client."""
        texts = list(instructions)
        if schema is not None and self._structured == "json":
            texts.append(json_instruction(schema.model_json_schema()))
        request: dict[str, Any] = {
            "model": self._model,
            "messages": to_messages(input, system="\n\n".join(texts)),
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
        try:
            try:
                response = await self._client.chat.completions.create(
                    **request, **{self._limit_param: max_output_tokens}
                )
            except openai.BadRequestError as exc:
                if self._limit_param != "max_completion_tokens" or "max_completion_tokens" not in str(exc):
                    raise
                self._limit_param = "max_tokens"
                log.info("chat_limit_param", extra={"param": self._limit_param})
                response = await self._client.chat.completions.create(**request, max_tokens=max_output_tokens)
        except Exception as exc:  # noqa: BLE001 - translated, then re-raised
            raise _translate(exc) from exc
        return chat_result(response, parse_json=schema is not None)


def chat_result(response: Any, *, parse_json: bool) -> CompletionResult:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ProviderUnavailable()
    usage = usage_dict(getattr(response, "usage", None))
    choice = choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        raise ProviderOutputTruncated("length", usage)
    text = strip_think(getattr(choice.message, "content", None) or "")
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
