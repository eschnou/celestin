from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.domain.errors import (
    ProviderOutputInvalid,
    ProviderOutputTruncated,
    ProviderAuthRejected,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderRejectedRequest,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.base import Completed, Failed, TextDelta, ToolCallRequested
from app.providers._errors import translate as _translate
from app.providers.openai_responses import OpenAIResponsesClient, _map_events, wire_input
from tests.fixtures.fake_stream import RawStream


OPENAI = Connection(OPENAI_BASE_URL, "k")
GROQ = Connection("https://api.groq.com/openai/v1", "g")


async def _events(raw: list[Any]) -> AsyncIterator[Any]:
    for item in raw:
        yield item


async def _mapped(raw: list[Any]) -> list[Any]:
    return [event async for event in _map_events(_events(raw))]


def _added(item_id: str, call_id: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="response.output_item.added",
        item=SimpleNamespace(type="function_call", id=item_id, call_id=call_id, name=name),
    )


async def test_text_delta_mapped() -> None:
    raw = [SimpleNamespace(type="response.output_text.delta", delta="Salut")]
    assert await _mapped(raw) == [TextDelta("Salut")]


async def test_tool_call_takes_its_name_from_the_earlier_item_added() -> None:
    raw = [
        _added("item_1", "call_abc", "display_board"),
        SimpleNamespace(
            type="response.function_call_arguments.done", item_id="item_1", arguments='{"card":{}}'
        ),
    ]
    assert await _mapped(raw) == [
        ToolCallRequested(call_id="call_abc", name="display_board", arguments_json='{"card":{}}')
    ]


async def test_argument_deltas_are_buffered_not_emitted() -> None:
    raw = [
        _added("i", "c", "clear_board"),
        SimpleNamespace(type="response.function_call_arguments.delta", delta="{"),
        SimpleNamespace(type="response.function_call_arguments.done", item_id="i", arguments="{}"),
    ]
    assert await _mapped(raw) == [ToolCallRequested("c", "clear_board", "{}")]


async def test_two_tool_calls_keep_their_own_identities() -> None:
    raw = [
        _added("i1", "c1", "display_board"),
        _added("i2", "c2", "clear_board"),
        SimpleNamespace(type="response.function_call_arguments.done", item_id="i2", arguments="{}"),
        SimpleNamespace(type="response.function_call_arguments.done", item_id="i1", arguments="{}"),
    ]
    assert [e.name for e in await _mapped(raw)] == ["clear_board", "display_board"]


async def test_unknown_item_id_still_yields_a_call() -> None:
    raw = [SimpleNamespace(type="response.function_call_arguments.done", item_id="ghost", arguments="{}")]
    (event,) = await _mapped(raw)
    assert isinstance(event, ToolCallRequested)
    assert event.name == ""


async def test_completed_carries_usage() -> None:
    usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 10})
    raw = [SimpleNamespace(type="response.completed", response=SimpleNamespace(usage=usage))]
    assert await _mapped(raw) == [Completed(usage={"input_tokens": 10})]


async def test_completed_without_usage() -> None:
    raw = [SimpleNamespace(type="response.completed", response=SimpleNamespace(usage=None))]
    assert await _mapped(raw) == [Completed(usage={})]


@pytest.mark.parametrize("kind", ["response.failed", "response.incomplete", "error"])
async def test_failures_mapped(kind: str) -> None:
    raw = [
        SimpleNamespace(
            type=kind,
            response=SimpleNamespace(error=SimpleNamespace(message="nope")),
            error=None,
        )
    ]
    (event,) = await _mapped(raw)
    assert isinstance(event, Failed)
    assert event.message == "nope"


async def test_unknown_events_ignored() -> None:
    assert await _mapped([SimpleNamespace(type="response.created")]) == []


def _api_error(cls: type) -> Exception:
    return cls.__new__(cls)


def test_error_translation() -> None:
    assert isinstance(_translate(_api_error(openai.RateLimitError)), ProviderRateLimited)
    assert isinstance(_translate(_api_error(openai.APITimeoutError)), ProviderTimeout)
    assert isinstance(_translate(_api_error(openai.APIError)), ProviderUnavailable)
    assert type(_translate(_api_error(openai.AuthenticationError))) is ProviderAuthRejected
    assert type(_translate(_api_error(openai.PermissionDeniedError))) is ProviderAuthRejected
    assert type(_translate(_api_error(openai.NotFoundError))) is ProviderModelNotFound
    assert type(_translate(_api_error(openai.BadRequestError))) is ProviderRejectedRequest
    assert type(_translate(_api_error(openai.UnprocessableEntityError))) is ProviderRejectedRequest
    for told_apart in (ProviderAuthRejected, ProviderModelNotFound, ProviderRejectedRequest):
        assert issubclass(told_apart, ProviderUnavailable)  # every existing handler still catches them
        assert told_apart().message("en") == ProviderUnavailable().message("en")
    assert isinstance(_translate(TimeoutError()), ProviderTimeout)
    keep = ValueError("unrelated")
    assert _translate(keep) is keep


async def test_store_is_false_on_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAIResponsesClient(OPENAI, "m", timeout_s=1.0)
    seen = await _stream_kwargs(client, monkeypatch, input=[{"role": "user", "content": "x"}], tools=[])
    assert seen["store"] is False and seen["stream"] is True
    assert seen["model"] == "m"


# --- one-shot completions (005 design 3.7) --------------------------------

from app.domain.errors import ProviderOutputInvalid, ProviderOutputTruncated  # noqa: E402
from app.providers.openai_responses import completion_request, completion_result  # noqa: E402


def _response(text: str, status: str = "completed", usage: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        output_text=text,
        incomplete_details=SimpleNamespace(reason="max_output_tokens") if status == "incomplete" else None,
        usage=SimpleNamespace(model_dump=lambda: usage or {"input_tokens": 3}),
    )


def test_plain_text_request_shape() -> None:
    request = completion_request(
        model="m", instructions=["A", "B"], input=[{"role": "user", "content": "x"}],
        schema=None, schema_name=None, reasoning_effort="medium", max_output_tokens=100,
    )
    assert request["store"] is False and request["max_output_tokens"] == 100
    assert request["reasoning"] == {"effort": "medium"}
    developer = request["input"][0]
    assert developer["role"] == "developer"
    assert developer["content"][0]["text"] == "A\n\nB"
    assert developer["content"][0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert request["input"][1] == {"role": "user", "content": "x"}
    assert "text" not in request


def test_schema_request_is_strict_with_every_field_required() -> None:
    from app.services.authoring.schemas import CurriculumDraft

    request = completion_request(
        model="m", instructions=["A"], input=[], schema=CurriculumDraft, schema_name="curriculum",
        reasoning_effort=None, max_output_tokens=10,
    )
    fmt = request["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["name"] == "curriculum"
    assert "reasoning" not in request
    section = fmt["schema"]["$defs"]["SectionDraft"]
    assert set(section["required"]) == set(section["properties"]) and section["additionalProperties"] is False


def test_result_text_and_json() -> None:
    plain = completion_result(_response("# Titre"), parse_json=False)
    assert plain.text == "# Titre" and plain.data is None and plain.usage == {"input_tokens": 3}
    parsed = completion_result(_response('{"title": "T", "sections": []}'), parse_json=True)
    assert parsed.data == {"title": "T", "sections": []}


def test_incomplete_is_truncated() -> None:
    with pytest.raises(ProviderOutputTruncated):
        completion_result(_response("# Tit", status="incomplete"), parse_json=False)


def test_a_truncated_or_invalid_answer_carries_what_it_was_billed() -> None:
    """Spec 015: the ledger and the authoring run count the provider's own tokens for an answer they cannot use."""
    billed = {"input_tokens": 90, "output_tokens": 40}
    with pytest.raises(ProviderOutputTruncated) as truncated:
        completion_result(_response("# Tit", status="incomplete", usage=billed), parse_json=False)
    assert truncated.value.usage == billed
    with pytest.raises(ProviderOutputInvalid) as invalid:
        completion_result(_response("{not json", usage=billed), parse_json=True)
    assert invalid.value.usage == billed


def test_a_cost_the_provider_reports_reaches_the_result() -> None:
    """OpenRouter puts `cost` in the usage block; the SDK keeps provider extras, so `model_dump` carries it."""
    usage = {"input_tokens": 3, "output_tokens": 1, "cost": 0.0042}
    assert completion_result(_response("ok", usage=usage), parse_json=False).usage["cost"] == 0.0042


def test_the_sdks_usage_model_keeps_a_provider_extra() -> None:
    from openai.types.responses import ResponseUsage

    usage = ResponseUsage.model_validate({
        "input_tokens": 3, "output_tokens": 1, "total_tokens": 4,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0}, "cost": 0.0042,
    })
    assert usage.model_dump()["cost"] == 0.0042


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"])
def test_bad_json_is_invalid(text: str) -> None:
    with pytest.raises(ProviderOutputInvalid):
        completion_result(_response(text), parse_json=True)


async def test_complete_translates_sdk_errors() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", timeout_s=1)

    async def boom(**_: Any) -> None:
        raise openai.APITimeoutError(request=SimpleNamespace())  # type: ignore[arg-type]

    client._client = SimpleNamespace(responses=SimpleNamespace(create=boom))  # type: ignore[assignment]
    with pytest.raises(ProviderTimeout):
        await client.complete(role="authoring", instructions=["A"], input=[], max_output_tokens=10)


async def test_complete_sends_the_request() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", timeout_s=1)
    seen: dict[str, Any] = {}

    async def create(**kwargs: Any) -> _RawStream:
        seen.update(kwargs)
        return _RawStream([_done("# T")])

    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))  # type: ignore[assignment]
    result = await client.complete(role="authoring", instructions=["A"], input=[], max_output_tokens=10)
    assert result.text == "# T" and seen["model"] == "m" and seen["store"] is False and seen["stream"] is True


# --- spec 014: any server that speaks the Responses API ------------------------------------------

BREAKPOINT = {"mode": "explicit"}


def _developer(text: str = "rules") -> dict[str, Any]:
    return {"role": "developer", "content": [{"type": "input_text", "text": text, "prompt_cache_breakpoint": BREAKPOINT}]}


class _RawStream:
    """What `responses.create(stream=True)` returns: an async iterator that is also a context manager."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events
        self.closed = False

    async def __aenter__(self) -> _RawStream:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[Any]:
        return _events(self._events)


async def _stream_kwargs(
    client: OpenAIResponsesClient, monkeypatch: pytest.MonkeyPatch, events: list[Any] | None = None, **call: Any
) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def fake_create(**kwargs: Any) -> _RawStream:
        seen.update(kwargs)
        return _RawStream(events or [])

    monkeypatch.setattr(client._client.responses, "create", fake_create)
    async with client.stream(**call) as stream:
        assert [e async for e in stream] == [e for e in await _mapped(events or [])]
    return seen


TOOLS = [{"type": "function", "name": "t", "description": "d", "parameters": {"type": "object"}, "strict": True}]


async def test_openai_gets_the_very_objects_it_always_got(monkeypatch: pytest.MonkeyPatch) -> None:
    input_ = [_developer(), {"role": "user", "content": "x"}]
    seen = await _stream_kwargs(OpenAIResponsesClient(OPENAI, "m", 1.0), monkeypatch, input=input_, tools=TOOLS)
    assert seen["input"] is input_ and seen["tools"] is TOOLS
    assert seen["input"][0]["content"][0]["prompt_cache_breakpoint"] == BREAKPOINT and seen["tools"][0]["strict"] is True
    assert set(seen) == {"model", "input", "tools", "store", "stream"}  # no reasoning unless asked


async def test_another_host_does_not_get_openai_only_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    input_ = [_developer(), {"role": "user", "content": "x"}, {"role": "user", "content": [{"type": "input_text", "text": "y"}]}]
    seen = await _stream_kwargs(OpenAIResponsesClient(GROQ, "m", 1.0), monkeypatch, input=input_, tools=TOOLS)
    assert seen["input"][0] == {"role": "system", "content": [{"type": "input_text", "text": "rules"}]}
    assert seen["input"][1] == input_[1] and seen["store"] is False
    assert "strict" not in seen["tools"][0] and seen["tools"][0]["name"] == "t"
    # the transcript is replayed every turn: the caller's items are never modified
    assert input_[0]["content"][0]["prompt_cache_breakpoint"] == BREAKPOINT and TOOLS[0]["strict"] is True


async def test_the_reasoning_effort_is_sent_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = await _stream_kwargs(OpenAIResponsesClient(GROQ, "m", 1.0, reasoning_effort="low"), monkeypatch, input=[], tools=[])
    assert seen["reasoning"] == {"effort": "low"}


async def test_a_server_whose_events_arrive_in_another_order_is_tolerated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The raw stream is mapped event by event: nothing folds them into a snapshot that could disagree."""
    events = [
        SimpleNamespace(type="response.output_text.delta", delta="Salut", output_index=3),  # an index never announced
        SimpleNamespace(type="response.completed", response=SimpleNamespace(usage=None)),
    ]
    client = OpenAIResponsesClient(GROQ, "m", 1.0)
    seen = await _stream_kwargs(client, monkeypatch, events, input=[], tools=[])
    assert seen["stream"] is True


async def test_the_raw_stream_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenAIResponsesClient(GROQ, "m", 1.0)
    holder: list[_RawStream] = []

    async def fake_create(**_: Any) -> _RawStream:
        holder.append(_RawStream([]))
        return holder[0]

    monkeypatch.setattr(client._client.responses, "create", fake_create)
    async with client.stream(input=[], tools=[]) as stream:
        [_ async for _ in stream]
    assert holder[0].closed


async def test_the_developer_messages_become_system_then_user_elsewhere_than_openai() -> None:
    items = [_developer("rules"), {"role": "user", "content": "x"}, {"role": "developer", "content": [{"type": "input_text", "text": "state"}]}]
    other = wire_input(items, openai=False)
    assert [i["role"] for i in other] == ["system", "user", "user"]
    assert other[0]["content"] == [{"type": "input_text", "text": "rules"}] and other[2]["content"][0]["text"] == "state"
    assert [i["role"] for i in items] == ["developer", "user", "developer"]  # untouched
    opening = wire_input([_developer("rules"), {"role": "developer", "content": [{"type": "input_text", "text": "state"}]}], openai=False)
    assert [i["role"] for i in opening] == ["system", "user"]  # the opening turn has a user message
    assert wire_input(items, openai=True) is items


def test_the_client_model_is_readable() -> None:
    assert OpenAIResponsesClient(GROQ, "openai/gpt-oss-120b", 1.0).model == "openai/gpt-oss-120b"


def test_completion_request_for_another_host_has_no_cache_breakpoint() -> None:
    request = completion_request(
        model="m", instructions=["A"], input=[], schema=None, schema_name=None, reasoning_effort="low",
        max_output_tokens=10, openai=False,
    )
    assert request["input"][0] == {"role": "system", "content": [{"type": "input_text", "text": "A"}]}
    assert request["reasoning"] == {"effort": "low"} and request["store"] is False
    # OpenAI's own request keeps its `developer` role and its breakpoint
    assert completion_request(
        model="m", instructions=["A"], input=[], schema=None, schema_name=None, reasoning_effort=None, max_output_tokens=10
    )["input"][0]["role"] == "developer"


def test_json_mode_asks_for_a_json_object_and_puts_the_schema_in_the_instructions() -> None:
    from app.services.authoring.schemas import CurriculumDraft

    request = completion_request(
        model="m", instructions=["A"], input=[], schema=CurriculumDraft, schema_name="c", reasoning_effort=None,
        max_output_tokens=10, openai=False, structured="json",
    )
    assert request["text"] == {"format": {"type": "json_object"}}
    text = request["input"][0]["content"][0]["text"]
    assert text.startswith("A\n\nOutput exactly one JSON object") and "SectionDraft" in text


def test_json_mode_reads_the_object_out_of_a_fence_or_prose() -> None:
    fenced = completion_result(_response('Voici :\n```json\n{"a": 1}\n```'), parse_json=True, extract=True)
    thinking = completion_result(_response('<think>hmm {x}</think>\n{"a": 2}'), parse_json=True, extract=True)
    assert fenced.data == {"a": 1} and thinking.data == {"a": 2}
    with pytest.raises(ProviderOutputInvalid):
        completion_result(_response("no object here"), parse_json=True, extract=True)
    with pytest.raises(ProviderOutputInvalid):
        completion_result(_response("[1]"), parse_json=True, extract=True)


async def test_complete_uses_the_clients_own_model_effort_and_mode() -> None:
    from app.services.authoring.schemas import CurriculumDraft

    client = OpenAIResponsesClient(
        Connection(GROQ.base_url, GROQ.api_key, "responses", "json"), "oss", 1, reasoning_effort="high"
    )
    seen: dict[str, Any] = {}

    async def create(**kwargs: Any) -> _RawStream:
        seen.update(kwargs)
        return _RawStream([_done('{"title": "T", "sections": []}')])

    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))  # type: ignore[assignment]
    result = await client.complete(
        role="transcription", instructions=["A"], input=[{"role": "user", "content": "x"}],
        schema=CurriculumDraft, max_output_tokens=10,
    )
    assert result.data == {"title": "T", "sections": []}
    assert seen["model"] == "oss" and seen["reasoning"] == {"effort": "high"} and seen["text"] == {"format": {"type": "json_object"}}
    assert "prompt_cache_breakpoint" not in str(seen["input"])


# --- spec 016: complete() is streamed --------------------------------------------------------------------------


def _delta(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="response.output_text.delta", delta=text)


def _done(text: str = "", status: str = "completed", usage: dict[str, Any] | None = None) -> SimpleNamespace:
    kind = "response.incomplete" if status == "incomplete" else "response.completed"
    return SimpleNamespace(type=kind, response=_response(text, status, usage))


def _scripted(client: OpenAIResponsesClient, *events: Any, seen: dict[str, Any] | None = None) -> _RawStream:
    raw = _RawStream(list(events))

    async def create(**kwargs: Any) -> _RawStream:
        if seen is not None:
            seen.update(kwargs)
        return raw

    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))  # type: ignore[assignment]
    return raw


CALL: dict[str, Any] = {"role": "authoring", "instructions": ["A"], "input": [], "max_output_tokens": 10}


async def test_the_request_is_todays_plus_the_stream_flag() -> None:
    """R2.5: nothing else about the request moved."""
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    seen: dict[str, Any] = {}
    _scripted(client, _done("x"), seen=seen)
    await client.complete(**CALL)
    expected = completion_request(
        model="m", instructions=["A"], input=[], schema=None, schema_name=None, reasoning_effort=None,
        max_output_tokens=10,
    )
    assert seen == {**expected, "stream": True}


async def test_the_text_is_assembled_from_the_deltas() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    raw = _scripted(client, _delta("# Ti"), _delta("tre"), _done("", usage={"input_tokens": 7}))
    result = await client.complete(**CALL)
    assert result.text == "# Titre" and result.usage == {"input_tokens": 7} and raw.closed


async def test_the_deltas_are_the_answer_and_the_final_text_is_only_a_fallback() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta("# Ti"), _delta("tre"), _done("something else"))
    assert (await client.complete(**CALL)).text == "# Titre"
    _scripted(client, _done("# Titre"))  # a server that streams no text deltas
    assert (await client.complete(**CALL)).text == "# Titre"


async def test_json_is_parsed_from_a_streamed_answer() -> None:
    from app.services.authoring.schemas import CurriculumDraft

    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta('{"title": "T", '), _delta('"sections": []}'), _done(""))
    result = await client.complete(**CALL, schema=CurriculumDraft)
    assert result.data == {"title": "T", "sections": []}


async def test_an_incomplete_stream_is_truncated_and_carries_its_usage() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta("# Tit"), _done("# Tit", status="incomplete", usage={"output_tokens": 40}))
    with pytest.raises(ProviderOutputTruncated) as raised:
        await client.complete(**CALL)
    assert raised.value.usage == {"output_tokens": 40}
    assert raised.value.diagnostics is not None and raised.value.diagnostics.reason == "truncated"


async def test_a_failed_event_is_unavailable_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    raw = _scripted(client, _delta("x"), SimpleNamespace(type="response.failed", response=SimpleNamespace(error=None)))
    with caplog.at_level("WARNING"), pytest.raises(ProviderUnavailable) as raised:
        await client.complete(**CALL)
    assert raised.value.diagnostics is not None and raised.value.diagnostics.reason == "error_event" and raw.closed
    (line,) = [r for r in caplog.records if r.getMessage() == "provider_call_failed"]
    assert line.reason == "error_event" and line.role == "authoring" and line.received_chars == 1  # type: ignore[attr-defined]


async def test_an_error_event_naming_a_rate_limit_is_rate_limited() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, SimpleNamespace(type="error", error=SimpleNamespace(code="rate_limit_exceeded", message="x")))
    with pytest.raises(ProviderRateLimited):
        await client.complete(**CALL)


async def test_a_stream_that_ends_without_a_completion_event_is_unavailable() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta("a half answer"))
    with pytest.raises(ProviderUnavailable) as raised:
        await client.complete(**CALL)
    assert raised.value.diagnostics is not None and raised.value.diagnostics.reason == "stream_ended"


async def test_unparseable_json_is_invalid_with_its_usage() -> None:
    from app.services.authoring.schemas import CurriculumDraft

    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta("{not json"), _done("", usage={"output_tokens": 9}))
    with pytest.raises(ProviderOutputInvalid) as raised:
        await client.complete(**CALL, schema=CurriculumDraft)
    assert raised.value.usage == {"output_tokens": 9}


async def test_a_quiet_provider_is_given_up_on_and_the_stream_closed() -> None:
    from app.providers.base import StreamLimits

    client = OpenAIResponsesClient(OPENAI, "m", 1, limits=StreamLimits(first_event_s=0.2, idle_s=0.03))

    raw = RawStream([_delta("a")], stall=True)

    async def create(**_: Any) -> _RawStream:
        return raw

    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))  # type: ignore[assignment]
    with pytest.raises(ProviderTimeout) as raised:
        await client.complete(**CALL)
    assert raised.value.diagnostics is not None and raised.value.diagnostics.reason == "idle_timeout" and raw.closed


async def test_progress_snapshots_reach_the_callback_with_counts_only() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta("abc"), _delta("de"), _done("abcde"))
    snapshots: list[Any] = []
    await client.complete(**CALL, on_progress=snapshots.append)
    assert snapshots and snapshots[-1].received_chars == 5 and snapshots[-1].events == 3


async def test_a_successful_call_logs_one_done_line(caplog: pytest.LogCaptureFixture) -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta("abc"), _done("abc", usage={"input_tokens": 3, "output_tokens": 1}))
    with caplog.at_level("INFO"):
        await client.complete(**CALL)
    (line,) = [r for r in caplog.records if r.getMessage() == "provider_call_done"]
    assert (line.received_chars, line.input_tokens, line.provider_host) == (3, 3, "api.openai.com")  # type: ignore[attr-defined]


async def test_a_server_that_refuses_streaming_is_a_rejected_request_not_a_silent_fallback() -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    calls: list[dict[str, Any]] = []

    async def refuse(**kwargs: Any) -> None:
        calls.append(kwargs)
        request = httpx2.Request("POST", "https://x/v1/responses")
        raise openai.BadRequestError(
            "stream is not supported", response=httpx2.Response(400, request=request), body=None
        )

    client._client = SimpleNamespace(responses=SimpleNamespace(create=refuse))  # type: ignore[assignment]
    with pytest.raises(ProviderRejectedRequest) as raised:
        await client.complete(**CALL)
    assert len(calls) == 1 and raised.value.diagnostics is not None
    assert raised.value.diagnostics.reason == "stream_unsupported"


async def test_a_tutor_stream_failure_is_logged_with_its_class(caplog: pytest.LogCaptureFixture) -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)

    async def boom(**_: Any) -> None:
        raise openai.APITimeoutError(request=SimpleNamespace())  # type: ignore[arg-type]

    client._client = SimpleNamespace(responses=SimpleNamespace(create=boom))  # type: ignore[assignment]
    with caplog.at_level("WARNING"), pytest.raises(ProviderTimeout):
        async with client.stream(input=[], tools=[]):
            pass
    (line,) = [r for r in caplog.records if r.getMessage() == "provider_call_failed"]
    assert (line.role, line.error_class, line.reason) == ("tutor", "APITimeoutError", "transport_timeout")  # type: ignore[attr-defined]


async def test_an_error_of_the_tutors_consumer_is_not_logged_as_a_provider_failure(caplog: pytest.LogCaptureFixture) -> None:
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    _scripted(client, _delta("x"))
    with caplog.at_level("WARNING"), pytest.raises(ValueError):
        async with client.stream(input=[], tools=[]):
            raise ValueError("the consumer's own")
    assert not [r for r in caplog.records if r.getMessage() == "provider_call_failed"]


async def test_no_log_line_of_a_streamed_call_carries_the_text_or_an_error_message(caplog: pytest.LogCaptureFixture) -> None:
    """Spec 016 NFR 4.3: counts, durations and class names only."""
    client = OpenAIResponsesClient(OPENAI, "m", 1)
    with caplog.at_level("DEBUG"):
        _scripted(client, _delta("SECRET-ANSWER-TEXT"), _done("SECRET-ANSWER-TEXT"))
        await client.complete(**CALL, on_progress=lambda snapshot: None)
        _scripted(
            client, _delta("SECRET-PARTIAL"),
            SimpleNamespace(type="error", error=SimpleNamespace(code="server_error", message="SECRET-ERROR-MESSAGE")),
        )
        with pytest.raises(ProviderUnavailable):
            await client.complete(**CALL)
    dump = " ".join(str(r.__dict__) for r in caplog.records)
    assert "SECRET" not in dump and "provider_call_done" in dump and "provider_call_failed" in dump
