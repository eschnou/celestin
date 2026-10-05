"""OpenAI Responses adapter: OpenAI itself and any server that speaks its Responses API (spec 014).

Imports `openai`, like the other adapters of this package; nothing above `app/providers/` may.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import json

from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from app.domain.ai_config import Connection, Effort, StructuredMode
from app.domain.errors import (
    ProviderOutputInvalid,
    ProviderOutputTruncated,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers._client import make_client
from app.providers._errors import translate as _translate
from app.providers.base import (
    Completed,
    CompletionResult,
    Failed,
    ProviderEvent,
    TextDelta,
    ToolCallRequested,
)
from app.providers.chat_translate import extract_json, json_instruction

log = logging.getLogger(__name__)

# Fields of the Responses API that only OpenAI understands: sent to its own host, stripped elsewhere.
_OPENAI_ONLY_PART_FIELDS = ("prompt_cache_breakpoint",)
_OPENAI_ONLY_TOOL_FIELDS = ("strict",)


def wire_input(input: list[dict[str, Any]], *, openai: bool) -> list[dict[str, Any]]:
    """The input as the server gets it. For OpenAI, the very same objects (byte-identical to before spec
    014). Elsewhere a copy: without the cache breakpoint on content parts, the first `developer` message
    sent as `system` and every later one as a `user` message. Servers that render the conversation through
    a chat template (Qwen's, for one) know no `developer` role, expect a single system message and refuse a
    conversation with no user message, and the tutor's opening turn is the prompt and the path state,
    nothing else. The caller's items are never modified: the transcript is replayed on every turn."""
    if openai:
        return input
    seen_developer = False
    wired: list[dict[str, Any]] = []
    for item in input:
        item = _without_part_fields(item)
        if item.get("role") == "developer":
            item = {**item, "role": "user" if seen_developer else "system"}
            seen_developer = True
        wired.append(item)
    return wired


def _without_part_fields(item: dict[str, Any]) -> dict[str, Any]:
    content = item.get("content")
    if not isinstance(content, list):
        return item
    parts = [
        {key: value for key, value in part.items() if key not in _OPENAI_ONLY_PART_FIELDS}
        if isinstance(part, dict)
        else part
        for part in content
    ]
    return {**item, "content": parts}


def wire_tools(tools: list[dict[str, Any]], *, openai: bool) -> list[dict[str, Any]]:
    """Tool declarations without `strict` for a server that did not ask for it (Pydantic validates the
    arguments either way, design 4.3 of spec 001)."""
    if openai:
        return tools
    return [{key: value for key, value in tool.items() if key not in _OPENAI_ONLY_TOOL_FIELDS} for tool in tools]


class OpenAIResponsesClient:
    """One role's client: its connection, its model, its reasoning effort and its structured-output mode."""

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

    @property
    def model(self) -> str:
        return self._model

    @asynccontextmanager
    async def stream(
        self,
        *,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[AsyncIterator[ProviderEvent]]:
        try:
            # store=False: nothing is retained upstream (design 10.6).
            extra: dict[str, Any] = {"reasoning": {"effort": self._effort}} if self._effort else {}
            # The raw event stream, not `responses.stream()`: that helper folds the events into a snapshot of
            # the response and raises on a server whose events arrive in another order than OpenAI's. The
            # adapter needs the events only.
            raw = await self._client.responses.create(
                model=self._model,
                input=wire_input(input, openai=self._connection.is_openai),
                tools=wire_tools(tools, openai=self._connection.is_openai),
                store=False,
                stream=True,
                **extra,
            )
            async with raw:
                yield _map_events(raw)
        except Exception as exc:  # noqa: BLE001 - translated, then re-raised
            raise _translate(exc) from exc


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
        """One non-streamed call (005 design 3.7). The instructions form one
        developer message ending, for OpenAI, in a cache breakpoint, so a repair call and the
        next run of the same subject reuse the prefix. `role` was used to pick this client."""
        request = completion_request(
            model=self._model,
            instructions=instructions,
            input=wire_input(input, openai=self._connection.is_openai),
            schema=schema,
            schema_name=schema_name,
            reasoning_effort=self._effort,
            max_output_tokens=max_output_tokens,
            openai=self._connection.is_openai,
            structured=self._structured,
        )
        try:
            response = await self._client.responses.create(**request)
        except Exception as exc:  # noqa: BLE001 - translated, then re-raised
            raise _translate(exc) from exc
        return completion_result(response, parse_json=schema is not None, extract=self._structured == "json")


def completion_request(
    *,
    model: str,
    instructions: list[str],
    input: list[dict[str, Any]],
    schema: type[BaseModel] | None,
    schema_name: str | None,
    reasoning_effort: str | None,
    max_output_tokens: int,
    openai: bool = True,
    structured: StructuredMode = "schema",
) -> dict[str, Any]:
    texts = list(instructions)
    if schema is not None and structured == "json":
        texts.append(json_instruction(schema.model_json_schema()))
    part: dict[str, Any] = {"type": "input_text", "text": "\n\n".join(texts)}
    if openai:
        part["prompt_cache_breakpoint"] = {"mode": "explicit"}
    # `developer` is OpenAI's role for it; a chat-template server knows `system` (see `wire_input`).
    developer = {"role": "developer" if openai else "system", "content": [part]}
    request: dict[str, Any] = {
        "model": model,
        "input": [developer, *input],
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    if reasoning_effort:
        request["reasoning"] = {"effort": reasoning_effort}
    if schema is not None:
        request["text"] = {
            "format": {"type": "json_object"}
            if structured == "json"
            else {
                "type": "json_schema",
                "name": schema_name or schema.__name__,
                "schema": to_strict_json_schema(schema),
                "strict": True,
            }
        }
    return request


def completion_result(response: Any, *, parse_json: bool, extract: bool = False) -> CompletionResult:
    status = getattr(response, "status", None)
    raw_usage = getattr(response, "usage", None)
    usage = raw_usage.model_dump() if raw_usage else {}
    if status == "incomplete":
        raise ProviderOutputTruncated(str(getattr(response, "incomplete_details", "") or "incomplete"), usage)
    if status == "failed":
        raise ProviderUnavailable()
    text = getattr(response, "output_text", "") or ""
    data = None
    if parse_json:
        try:
            data = json.loads(extract_json(text) if extract else text)
        except ValueError as exc:
            raise ProviderOutputInvalid(str(exc), usage) from exc
        if not isinstance(data, dict):
            raise ProviderOutputInvalid("not a JSON object", usage)
    return CompletionResult(text=text, data=data, usage=usage)


async def _map_events(raw: AsyncIterator[Any]) -> AsyncIterator[ProviderEvent]:
    """Map Responses API events onto provider-neutral ones (design 3.3).

    Tool arguments are buffered until `.done`: a tool cannot execute on partial
    JSON, and the interface shows a marker rather than the arguments. The `.done`
    event carries only `item_id` and `arguments`, so the tool name and call id are
    picked up from the earlier `response.output_item.added` event.
    """
    pending: dict[str, tuple[str, str]] = {}

    async for event in raw:
        kind = getattr(event, "type", "")
        if kind == "response.output_text.delta":
            yield TextDelta(event.delta)
        elif kind == "response.output_item.added":
            item = getattr(event, "item", None)
            if getattr(item, "type", None) == "function_call":
                item_id = str(getattr(item, "id", "") or "")
                pending[item_id] = (
                    str(getattr(item, "call_id", "") or item_id),
                    str(getattr(item, "name", "") or ""),
                )
        elif kind == "response.function_call_arguments.done":
            item_id = str(getattr(event, "item_id", "") or "")
            call_id, name = pending.pop(item_id, (item_id or "call_unknown", ""))
            yield ToolCallRequested(
                call_id=call_id,
                name=name,
                arguments_json=getattr(event, "arguments", "") or "",
            )
        elif kind == "response.completed":
            usage = getattr(getattr(event, "response", None), "usage", None)
            yield Completed(usage=usage.model_dump() if usage else {})
        elif kind in ("response.failed", "response.incomplete", "error"):
            yield Failed(code=_failure_code(event), message=_failure_message(event))


_FAILURE_CODES = {
    "rate_limit_exceeded": ProviderRateLimited.code,
    "rate_limit": ProviderRateLimited.code,
    "timeout": ProviderTimeout.code,
}


def _failure_code(event: Any) -> str:
    error = getattr(getattr(event, "response", None), "error", None) or getattr(event, "error", None)
    reported = str(getattr(error, "code", "") or "").lower()
    return _FAILURE_CODES.get(reported, ProviderUnavailable.code)


def _failure_message(event: Any) -> str:
    error = getattr(getattr(event, "response", None), "error", None) or getattr(event, "error", None)
    return str(getattr(error, "message", None) or error or "provider failure")
