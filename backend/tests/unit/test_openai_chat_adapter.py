"""Spec 014 §3.5: the Chat Completions adapter, against scripted SDK doubles. No network."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.domain.errors import (
    ProviderAuthRejected,
    ProviderModelNotFound,
    ProviderOutputInvalid,
    ProviderOutputTruncated,
    ProviderRateLimited,
    ProviderRejectedRequest,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.base import Completed, Failed, TextDelta, ToolCallRequested
from app.providers.openai_chat import OpenAIChatClient, _map_chunks, chat_result

LOCAL = Connection("http://localhost:11434/v1", None, "chat")
OPENAI = Connection(OPENAI_BASE_URL, "k", "chat")


def chunk(content: str | None = None, *, calls: list | None = None, finish: str | None = None, usage: Any = None) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=calls)
    choices = [SimpleNamespace(delta=delta, finish_reason=finish)] if (content is not None or calls or finish) else []
    return SimpleNamespace(choices=choices, usage=usage)


def fragment(index: int, *, id: str | None = None, name: str | None = None, args: str | None = None) -> Any:
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))


async def aiter(items: list[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


async def mapped(chunks: list[Any]) -> list[Any]:
    return [e async for e in _map_chunks(aiter(chunks))]


USAGE = SimpleNamespace(
    prompt_tokens=10, completion_tokens=4, prompt_tokens_details=SimpleNamespace(cached_tokens=3), completion_tokens_details=None
)


# ------------------------------------------------------------------ streaming


async def test_text_is_streamed_and_the_stream_completes_with_usage() -> None:
    events = await mapped([chunk("Bon"), chunk("jour"), chunk(finish="stop"), chunk(usage=USAGE)])
    assert events == [
        TextDelta("Bon"),
        TextDelta("jour"),
        Completed(usage={
            "input_tokens": 10, "output_tokens": 4,
            "input_tokens_details": {"cached_tokens": 3}, "output_tokens_details": {"reasoning_tokens": 0},
        }),
    ]


async def test_a_tool_call_is_assembled_from_its_fragments_and_emitted_once_complete() -> None:
    events = await mapped([
        chunk(calls=[fragment(0, id="call_a", name="display_board", args="")]),
        chunk(calls=[fragment(0, args='{"card":')]),
        chunk(calls=[fragment(0, args='{"kind":"title"}}')]),
        chunk(finish="tool_calls"),
    ])
    assert events == [
        ToolCallRequested("call_a", "display_board", '{"card":{"kind":"title"}}'),
        Completed(usage={}),
    ]


async def test_parallel_calls_keep_their_own_identities_in_index_order() -> None:
    events = await mapped([
        chunk(calls=[fragment(1, id="c2", name="clear_board", args="{}"), fragment(0, id="c1", name="start_section", args='{"section_id":')]),
        chunk(calls=[fragment(0, args='"s1"}')]),
        chunk(finish="tool_calls"),
    ])
    calls = [e for e in events if isinstance(e, ToolCallRequested)]
    assert [(c.call_id, c.name, c.arguments_json) for c in calls] == [
        ("c1", "start_section", '{"section_id":"s1"}'),
        ("c2", "clear_board", "{}"),
    ]


async def test_a_server_that_gives_no_call_id_or_arguments_still_yields_a_call() -> None:
    events = await mapped([chunk(calls=[fragment(0, name="clear_board")]), chunk(finish="stop")])
    assert events[0] == ToolCallRequested("call_0", "clear_board", "{}")


async def test_text_before_a_call_is_kept() -> None:
    events = await mapped([chunk("Je montre."), chunk(calls=[fragment(0, id="c", name="clear_board", args="{}")]), chunk(finish="tool_calls")])
    assert [type(e) for e in events] == [TextDelta, ToolCallRequested, Completed]


async def test_visible_thinking_never_reaches_the_student() -> None:
    events = await mapped([chunk("<think>je réfléchis"), chunk(" longtemps</think>\n\nBonjour"), chunk(finish="stop")])
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Bonjour"


async def test_reasoning_fields_of_the_delta_are_ignored() -> None:
    delta = SimpleNamespace(content="Salut", tool_calls=None, reasoning_content="secret", reasoning="more")
    stream = [SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)], usage=None), chunk(finish="stop")]
    events = await mapped(stream)
    assert events[0] == TextDelta("Salut") and "secret" not in str(events)


async def test_an_output_limit_is_a_failure_not_a_half_answer() -> None:
    (*_, last) = await mapped([chunk("coupé"), chunk(finish="length")])
    assert isinstance(last, Failed) and last.code == "provider_unavailable"


async def test_a_stream_that_ends_without_a_finish_reason_is_a_failure() -> None:
    (*_, last) = await mapped([chunk("début")])
    assert isinstance(last, Failed)


async def test_empty_chunks_and_missing_choices_are_ignored() -> None:
    events = await mapped([SimpleNamespace(choices=[], usage=None), SimpleNamespace(usage=None), chunk(finish="stop")])
    assert events == [Completed(usage={})]


# ------------------------------------------------------------------ the request


class _Raw:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks, self.closed = chunks, False

    async def __aenter__(self) -> _Raw:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[Any]:
        return aiter(self._chunks)


async def run_stream(client: OpenAIChatClient, monkeypatch: pytest.MonkeyPatch, chunks: list[Any], **call: Any):
    seen: dict[str, Any] = {}
    holder: list[_Raw] = []

    async def create(**kwargs: Any) -> _Raw:
        seen.update(kwargs)
        holder.append(_Raw(chunks))
        return holder[0]

    monkeypatch.setattr(client._client.chat.completions, "create", create)
    async with client.stream(**call) as stream:
        events = [e async for e in stream]
    return seen, events, holder[0]


TOOLS = [{"type": "function", "name": "t", "description": "d", "parameters": {"type": "object"}, "strict": True}]
ITEMS = [
    {"role": "developer", "content": [{"type": "input_text", "text": "rules", "prompt_cache_breakpoint": {"mode": "explicit"}}]},
    {"role": "user", "content": "salut"},
]


async def test_the_stream_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAIChatClient(LOCAL, "qwen3:8b", 5.0)
    seen, events, raw = await run_stream(client, monkeypatch, [chunk("ok"), chunk(finish="stop")], input=ITEMS, tools=TOOLS)
    assert seen["model"] == "qwen3:8b" and seen["stream"] is True and seen["stream_options"] == {"include_usage": True}
    assert seen["messages"] == [{"role": "system", "content": "rules"}, {"role": "user", "content": "salut"}]
    assert seen["tools"] == [{"type": "function", "function": {"name": "t", "description": "d", "parameters": {"type": "object"}}}]
    assert "reasoning_effort" not in seen and raw.closed and [type(e) for e in events] == [TextDelta, Completed]


async def test_strict_and_the_effort_go_only_where_they_are_meant(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAIChatClient(OPENAI, "m", 5.0, reasoning_effort="low")
    seen, _, _ = await run_stream(client, monkeypatch, [chunk(finish="stop")], input=ITEMS, tools=TOOLS)
    assert seen["tools"][0]["function"]["strict"] is True and seen["reasoning_effort"] == "low"


async def test_no_tools_means_no_tools_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen, _, _ = await run_stream(OpenAIChatClient(LOCAL, "m", 5.0), monkeypatch, [chunk(finish="stop")], input=ITEMS, tools=[])
    assert "tools" not in seen


async def test_a_refused_request_is_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAIChatClient(LOCAL, "m", 5.0)

    async def create(**_: Any) -> None:
        raise status_error(openai.BadRequestError, 400, "No user query found")

    monkeypatch.setattr(client._client.chat.completions, "create", create)
    with pytest.raises(ProviderRejectedRequest):
        async with client.stream(input=ITEMS, tools=[]) as stream:
            [_ async for _ in stream]


def test_the_models_name_is_readable() -> None:
    assert OpenAIChatClient(LOCAL, "qwen3:8b", 5.0).model == "qwen3:8b"


# ------------------------------------------------------------------ one-shot


def status_error(cls: type[openai.APIStatusError], status: int, message: str = "nope") -> Exception:
    request = httpx.Request("POST", "http://localhost/v1/chat/completions")
    response = httpx.Response(status, request=request, json={"error": {"message": message}})
    return cls(message, response=response, body=None)


def completion(text: str | None, finish: str = "stop", usage: Any = USAGE) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)], usage=usage)


def with_create(client: OpenAIChatClient, outcomes: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))  # type: ignore[assignment]
    return calls


async def test_a_plain_completion() -> None:
    client = OpenAIChatClient(LOCAL, "m", 5.0, reasoning_effort="medium")
    calls = with_create(client, [completion("# Titre")])
    result = await client.complete(role="authoring", instructions=["A", "B"], input=[{"role": "user", "content": "x"}], max_output_tokens=100)
    assert result.text == "# Titre" and result.data is None and result.usage["input_tokens"] == 10
    (request,) = calls
    assert request["messages"] == [{"role": "system", "content": "A\n\nB"}, {"role": "user", "content": "x"}]
    assert request["max_completion_tokens"] == 100 and "max_tokens" not in request
    assert request["reasoning_effort"] == "medium" and "response_format" not in request


async def test_schema_mode_sends_a_strict_json_schema() -> None:
    from app.services.authoring.schemas import CurriculumDraft

    client = OpenAIChatClient(LOCAL, "m", 5.0)
    calls = with_create(client, [completion('{"title": "T", "sections": []}')])
    result = await client.complete(role="authoring", instructions=["A"], input=[], schema=CurriculumDraft, schema_name="c", max_output_tokens=10)
    assert result.data == {"title": "T", "sections": []}
    fmt = calls[0]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True and fmt["json_schema"]["name"] == "c"
    section = fmt["json_schema"]["schema"]["$defs"]["SectionDraft"]
    assert set(section["required"]) == set(section["properties"])


async def test_json_mode_asks_for_an_object_and_reads_it_out_of_prose() -> None:
    from app.services.authoring.schemas import CurriculumDraft

    client = OpenAIChatClient(Connection(LOCAL.base_url, None, "chat", "json"), "m", 5.0)
    calls = with_create(client, [completion('<think>x</think>Voici :\n```json\n{"title": "T", "sections": []}\n```')])
    result = await client.complete(role="authoring", instructions=["A"], input=[], schema=CurriculumDraft, max_output_tokens=10)
    assert result.data == {"title": "T", "sections": []}
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["messages"][0]["content"].startswith("A\n\nOutput exactly one JSON object")


async def test_a_server_that_only_knows_max_tokens_is_asked_again_and_remembered() -> None:
    client = OpenAIChatClient(LOCAL, "m", 5.0)
    refusal = status_error(openai.BadRequestError, 400, "Unsupported parameter: 'max_completion_tokens'")
    calls = with_create(client, [refusal, completion("a"), completion("b")])
    assert (await client.complete(role="authoring", instructions=[], input=[], max_output_tokens=7)).text == "a"
    assert "max_completion_tokens" in calls[0] and calls[1]["max_tokens"] == 7 and "max_completion_tokens" not in calls[1]
    assert (await client.complete(role="authoring", instructions=[], input=[], max_output_tokens=7)).text == "b"
    assert calls[2]["max_tokens"] == 7  # not asked twice


async def test_another_refusal_is_not_retried() -> None:
    client = OpenAIChatClient(LOCAL, "m", 5.0)
    calls = with_create(client, [status_error(openai.BadRequestError, 400, "model does not support images")])
    with pytest.raises(ProviderRejectedRequest):
        await client.complete(role="transcription", instructions=[], input=[], max_output_tokens=7)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error, expected",
    [
        (status_error(openai.AuthenticationError, 401), ProviderAuthRejected),
        (status_error(openai.NotFoundError, 404), ProviderModelNotFound),
        (status_error(openai.RateLimitError, 429), ProviderRateLimited),
        (status_error(openai.InternalServerError, 500), ProviderUnavailable),
        (openai.APITimeoutError(httpx.Request("POST", "http://x")), ProviderTimeout),
    ],
)
async def test_sdk_errors_are_translated(error: Exception, expected: type) -> None:
    client = OpenAIChatClient(LOCAL, "m", 5.0)
    with_create(client, [error])
    with pytest.raises(expected):
        await client.complete(role="authoring", instructions=[], input=[], max_output_tokens=7)


def test_chat_results() -> None:
    assert chat_result(completion("# T"), parse_json=False).text == "# T"
    assert chat_result(completion("<think>x</think>\n# T"), parse_json=False).text == "# T"
    with pytest.raises(ProviderOutputTruncated):
        chat_result(completion("# Tit", finish="length"), parse_json=False)
    with pytest.raises(ProviderOutputInvalid):
        chat_result(completion("{not json"), parse_json=True)
    with pytest.raises(ProviderOutputInvalid):
        chat_result(completion("[1, 2]"), parse_json=True)
    with pytest.raises(ProviderOutputInvalid):
        chat_result(completion(None), parse_json=True)  # a model that only reasoned
    with pytest.raises(ProviderUnavailable):
        chat_result(SimpleNamespace(choices=[], usage=None), parse_json=False)
