"""Spec 015 §3.2: every provider call becomes one ledger entry, and recording never touches the call."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from app.domain.errors import ProviderOutputInvalid, ProviderOutputTruncated, ProviderRateLimited, ProviderTimeout
from app.domain.usage import UsageEntry, UsageScope, usage_scope
from app.providers.base import Completed, CompletionResult, Failed, TextDelta, ToolCallRequested
from app.providers.recording import (
    RecordingCompletion,
    RecordingLLM,
    RecordingTranscriber,
    UsageRecorder,
)
from tests.fixtures.fake_completion import FakeCompletion, text
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM
from tests.fixtures.fake_stream import RawStream, delta
from tests.fixtures.fake_transcriber import ExplodingTranscriber, FakeTranscriber

SCOPE = UsageScope("u1", "tutor_turn", "c1", "ch1", "turn1")
USAGE = {
    "input_tokens": 120, "output_tokens": 30,
    "input_tokens_details": {"cached_tokens": 100}, "output_tokens_details": {"reasoning_tokens": 10},
}


class ListSink:
    def __init__(self) -> None:
        self.entries: list[UsageEntry] = []

    def record(self, entry: UsageEntry) -> None:
        self.entries.append(entry)

    @property
    def one(self) -> UsageEntry:
        assert len(self.entries) == 1, self.entries
        return self.entries[0]


class RaisingSink:
    def record(self, entry: UsageEntry) -> None:
        raise RuntimeError("sink down")


def tutor(rounds: list, sink: Any, inner: Any = None) -> RecordingLLM:
    return RecordingLLM(inner or FakeLLM(rounds), model="tutor-model", host="api.test", sink=sink)


async def consume(client: RecordingLLM) -> list:
    async with client.stream(input=[{"role": "user", "content": "SECRET"}], tools=[]) as events:
        return [event async for event in events]


# ------------------------------------------------------------------ streaming


async def test_a_stream_is_one_ok_entry_with_usage_and_ttft() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        events = await consume(tutor([[TextDelta("Bon"), TextDelta("jour"), Completed(usage=USAGE)]], sink))
    assert len(events) == 3  # the events pass through untouched
    entry = sink.one
    assert (entry.user_id, entry.course_id, entry.chapter_id, entry.correlation_id) == ("u1", "c1", "ch1", "turn1")
    assert (entry.role, entry.feature, entry.model, entry.provider, entry.status, entry.error_code) == (
        "tutor", "tutor_turn", "tutor-model", "api.test", "ok", None)
    assert (entry.input_tokens, entry.cached_tokens, entry.output_tokens, entry.reasoning_tokens) == (120, 100, 30, 10)
    assert entry.ttft_ms is not None and entry.latency_ms is not None and entry.latency_ms >= entry.ttft_ms
    assert entry.cost_usd is None and entry.created_at.tzinfo is not None


async def test_a_tool_only_round_has_no_ttft() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        await consume(tutor([[ToolCallRequested("c", "display_board", "{}"), Completed(usage=USAGE)]], sink))
    assert sink.one.ttft_ms is None and sink.one.status == "ok"


async def test_a_cost_the_provider_reported_is_recorded() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        await consume(tutor([[TextDelta("x"), Completed(usage={**USAGE, "cost": 0.0042})]], sink))
    assert sink.one.cost_usd == 0.0042


async def test_a_provider_that_reports_nothing_gives_nulls() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        await consume(tutor([[TextDelta("x"), Completed()]], sink))
    entry = sink.one
    assert (entry.input_tokens, entry.cached_tokens, entry.output_tokens, entry.cost_usd) == (None, None, None, None)


async def test_a_failed_event_is_a_failed_entry_with_its_code() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        await consume(tutor([[TextDelta("x"), Failed(code="provider_rate_limited", message="PROVIDER TEXT")]], sink))
    assert (sink.one.status, sink.one.error_code) == ("failed", "provider_rate_limited")


async def test_an_error_on_entry_is_a_failed_entry_and_still_raises() -> None:
    sink = ListSink()

    client = RecordingLLM(ExplodingLLM(ProviderTimeout()), model="m", host="h", sink=sink)
    with usage_scope(SCOPE), pytest.raises(ProviderTimeout):
        await consume(client)
    assert (sink.one.status, sink.one.error_code, sink.one.input_tokens) == ("failed", "provider_timeout", None)


async def test_an_exception_of_the_caller_before_the_provider_finished_is_failed_and_propagates() -> None:
    sink = ListSink()
    with usage_scope(SCOPE), pytest.raises(ProviderRateLimited):
        async with tutor([[TextDelta("x"), Completed(usage=USAGE)]], sink).stream(input=[], tools=[]) as events:
            raise ProviderRateLimited()
            async for _ in events:  # pragma: no cover
                pass
    assert (sink.one.status, sink.one.error_code, sink.one.input_tokens) == ("failed", "provider_rate_limited", None)


async def test_a_consumer_that_fails_after_the_provider_finished_does_not_make_a_failed_call() -> None:
    """The call was made, finished and billed: what the caller does with the answer is not its outcome."""
    sink = ListSink()
    with usage_scope(SCOPE), pytest.raises(RuntimeError):
        async with tutor([[TextDelta("x"), Completed(usage=USAGE)]], sink).stream(input=[], tools=[]) as events:
            async for _ in events:
                pass
            raise RuntimeError("a bug in the event mapping")
    assert (sink.one.status, sink.one.error_code, sink.one.input_tokens) == ("ok", None, 120)


async def test_the_latency_is_the_providers_not_the_consumers() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        async with tutor([[TextDelta("x"), Completed(usage=USAGE)]], sink).stream(input=[], tools=[]) as events:
            async for _ in events:
                pass
            await asyncio.sleep(0.2)  # the consumer is slow after the provider has ended
    assert sink.one.latency_ms is not None and sink.one.latency_ms < 150


async def test_a_consumer_that_leaves_early_is_cancelled_with_no_usage() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        async with tutor([[TextDelta("x"), ToolCallRequested("c", "n", "{}"), Completed(usage=USAGE)]], sink).stream(
            input=[], tools=[]
        ) as events:
            async for event in events:
                if isinstance(event, TextDelta):
                    break
    assert (sink.one.status, sink.one.input_tokens) == ("cancelled", None)


async def test_a_cancelled_task_leaves_a_cancelled_row() -> None:
    sink = ListSink()
    started = asyncio.Event()

    class Hanging:
        model = "x"

        def stream(self, **_: Any):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def cm():
                async def events():
                    yield TextDelta("x")
                    started.set()
                    await asyncio.sleep(60)

                yield events()

            return cm()

    async def run() -> None:
        with usage_scope(SCOPE):
            await consume(RecordingLLM(Hanging(), model="m", host="h", sink=sink))  # type: ignore[arg-type]

    task = asyncio.create_task(run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sink.one.status == "cancelled" and sink.one.ttft_ms is not None


async def test_the_model_comes_from_the_wrapper_not_the_inner_client() -> None:
    sink = ListSink()
    with usage_scope(SCOPE):
        await consume(tutor([[Completed()]], sink))
    assert sink.one.model == "tutor-model"  # FakeLLM says "fake-model"
    assert tutor([[]], sink).model == "fake-model"  # the property still answers for the inner client


async def test_a_discussion_scope_names_its_feature() -> None:
    sink = ListSink()
    with usage_scope(UsageScope("u1", "discussion_turn")):
        await consume(tutor([[Completed()]], sink))
    assert sink.one.feature == "discussion_turn" and sink.one.course_id is None


# ------------------------------------------------------------------ one-shot


def completion(script: list, role: str = "authoring", sink: Any = None) -> tuple[RecordingCompletion, FakeCompletion]:
    fake = FakeCompletion(script)
    return RecordingCompletion(fake, role=role, model="auth-model", host="api.test", sink=sink or ListSink()), fake  # type: ignore[arg-type]


async def call(client: RecordingCompletion, role: str = "authoring") -> CompletionResult:
    return await client.complete(role=role, instructions=["SECRET"], input=[], max_output_tokens=10)  # type: ignore[arg-type]


async def test_complete_ok_records_the_result_usage() -> None:
    sink = ListSink()
    client, _ = completion([text("hi", USAGE)], sink=sink)
    with usage_scope(UsageScope("u1", "authoring", "c1", "ch1", "run1")):
        assert (await call(client)).text == "hi"
    entry = sink.one
    assert (entry.role, entry.feature, entry.status, entry.correlation_id) == ("authoring", "authoring", "ok", "run1")
    assert (entry.input_tokens, entry.output_tokens, entry.ttft_ms) == (120, 30, None)


async def test_a_transcription_call_of_an_authoring_run_is_document_reading() -> None:
    sink = ListSink()
    client, _ = completion([text("p1", USAGE)], role="transcription", sink=sink)
    with usage_scope(UsageScope("u1", "authoring")):
        await call(client, "transcription")
    assert (sink.one.role, sink.one.feature) == ("transcription", "document_reading")


async def test_a_truncated_answer_keeps_the_tokens_it_was_billed() -> None:
    sink = ListSink()
    client, _ = completion([ProviderOutputTruncated("length", USAGE)], sink=sink)
    with usage_scope(SCOPE), pytest.raises(ProviderOutputTruncated):
        await call(client)
    assert (sink.one.status, sink.one.error_code, sink.one.input_tokens) == ("truncated", None, 120)


async def test_an_invalid_answer_is_failed_with_its_tokens() -> None:
    sink = ListSink()
    client, _ = completion([ProviderOutputInvalid("not json: SECRET", USAGE)], sink=sink)
    with usage_scope(SCOPE), pytest.raises(ProviderOutputInvalid):
        await call(client)
    assert (sink.one.status, sink.one.error_code, sink.one.output_tokens) == ("failed", "provider_output_invalid", 30)


class _ForeignError(Exception):
    """Not ours, with a `code` like an SDK or a library error has: it must not be recorded."""

    code = "SECRET-from-a-library"


@pytest.mark.parametrize(
    ("error", "code"),
    [(ProviderTimeout(), "provider_timeout"), (ValueError("SECRET"), "unknown"), (_ForeignError("SECRET"), "unknown")],
)
async def test_another_failure_is_failed_and_reraised_untouched(error: Exception, code: str) -> None:
    sink = ListSink()
    client, _ = completion([error], sink=sink)
    with usage_scope(SCOPE), pytest.raises(type(error)) as caught:
        await call(client)
    assert caught.value is error
    assert (sink.one.status, sink.one.error_code, sink.one.input_tokens) == ("failed", code, None)


async def test_a_cancelled_complete_is_cancelled() -> None:
    sink = ListSink()
    fake = FakeCompletion([text("x")], delay_s=60)
    client = RecordingCompletion(fake, role="authoring", model="m", host="h", sink=sink)  # type: ignore[arg-type]

    async def run() -> None:
        with usage_scope(SCOPE):
            await call(client)

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sink.one.status == "cancelled"


async def test_each_attempt_is_its_own_row() -> None:
    sink = ListSink()
    client, _ = completion([ProviderTimeout(), text("ok", USAGE)], sink=sink)
    with usage_scope(SCOPE):
        with pytest.raises(ProviderTimeout):
            await call(client)
        await call(client)
    assert [e.status for e in sink.entries] == ["failed", "ok"]


async def test_a_gathered_child_carries_the_scope() -> None:
    sink = ListSink()
    client, _ = completion([text("a", USAGE), text("b", USAGE)], sink=sink)
    with usage_scope(UsageScope("u1", "authoring", correlation_id="run1")):
        await asyncio.gather(call(client), call(client))
    assert [e.correlation_id for e in sink.entries] == ["run1", "run1"]


# ------------------------------------------------------------------ dictation


async def test_dictation_is_recorded_under_voice_with_the_scopes_audio_length() -> None:
    sink = ListSink()
    client = RecordingTranscriber(FakeTranscriber("SECRET"), model="stt", host="api.test", sink=sink)  # type: ignore[arg-type]
    with usage_scope(UsageScope("u1", "dictation", audio_seconds=4.5)):
        result = await client.transcribe(audio=b"SECRET", filename="f.webm", content_type="audio/webm")
    assert result.text == "SECRET"
    entry = sink.one
    assert (entry.role, entry.feature, entry.model, entry.status, entry.audio_seconds) == ("voice", "dictation", "stt", "ok", 4.5)
    assert (entry.input_tokens, entry.cost_usd) == (None, None)


async def test_a_failed_dictation_is_recorded_and_raised() -> None:
    sink = ListSink()
    client = RecordingTranscriber(ExplodingTranscriber(ProviderTimeout()), model="stt", host="h", sink=sink)  # type: ignore[arg-type]
    with usage_scope(UsageScope("u1", "dictation")), pytest.raises(ProviderTimeout):
        await client.transcribe(audio=b"x", filename="f", content_type="audio/webm")
    assert (sink.one.status, sink.one.error_code) == ("failed", "provider_timeout")


# ------------------------------------------------------------------ never in the way


async def test_without_a_scope_nothing_is_recorded() -> None:
    sink = ListSink()
    await consume(tutor([[TextDelta("x"), Completed(usage=USAGE)]], sink))
    client, _ = completion([text("x")], sink=sink)
    await call(client)
    assert sink.entries == []


async def test_a_sink_that_raises_does_not_touch_the_call(caplog: pytest.LogCaptureFixture) -> None:
    with usage_scope(SCOPE), caplog.at_level("ERROR"):
        events = await consume(tutor([[TextDelta("x"), Completed(usage=USAGE)]], RaisingSink()))
        client, _ = completion([text("fine")], sink=RaisingSink())
        result = await call(client)
    assert len(events) == 2 and result.text == "fine"
    logged = [r for r in caplog.records if r.getMessage() == "ai_usage_not_stored"]
    assert len(logged) == 2 and {r.error for r in logged} == {"RuntimeError"}  # type: ignore[attr-defined]
    assert "sink down" not in caplog.text


async def test_a_sink_that_raises_does_not_hide_the_calls_own_error() -> None:
    client, _ = completion([ProviderTimeout()], sink=RaisingSink())
    with usage_scope(SCOPE), pytest.raises(ProviderTimeout):
        await call(client)


# ------------------------------------------------------------------ the production sink


def entry() -> UsageEntry:
    from datetime import UTC, datetime

    return UsageEntry(datetime.now(UTC), "u1", "tutor", "tutor_turn", "m", "h", "ok")


async def test_the_recorder_writes_off_the_loop_thread_and_drains() -> None:
    seen: list[int] = []
    release = threading.Event()

    def write(_: UsageEntry) -> None:
        release.wait(2)
        seen.append(threading.get_ident())

    recorder = UsageRecorder(write)
    recorder.record(entry())
    assert seen == []  # record() returned before the write ran: it was not awaited
    release.set()
    await recorder.drain()
    assert len(seen) == 1 and seen[0] != threading.get_ident()


async def test_the_recorder_logs_and_swallows_a_failed_write(caplog: pytest.LogCaptureFixture) -> None:
    def write(_: UsageEntry) -> None:
        raise OSError("disk full: SECRET")

    recorder = UsageRecorder(write)
    with caplog.at_level("ERROR"):
        recorder.record(entry())
        await recorder.drain()
    (record,) = [r for r in caplog.records if r.getMessage() == "ai_usage_not_stored"]
    assert (record.error, record.role) == ("OSError", "tutor")  # type: ignore[attr-defined]
    assert "SECRET" not in caplog.text


def test_the_recorder_without_a_running_loop_writes_inline() -> None:
    written: list[UsageEntry] = []
    UsageRecorder(written.append).record(entry())
    assert len(written) == 1


async def test_a_row_can_be_handed_over_by_a_task_being_cancelled() -> None:
    written: list[UsageEntry] = []
    recorder = UsageRecorder(written.append)

    async def run() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            recorder.record(entry())

    task = asyncio.create_task(run())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await recorder.drain()
    assert len(written) == 1


# --- spec 016: streamed calls ---------------------------------------------------------------------------------


async def test_the_progress_callback_is_forwarded_untouched() -> None:
    client, fake = completion([text("hi", USAGE)])
    seen: list = []
    with usage_scope(UsageScope("u1", "authoring")):
        await client.complete(
            role="authoring", instructions=[], input=[], max_output_tokens=1, on_progress=seen.append
        )
    assert fake.calls and seen == []  # the fake emitted nothing; what matters is the keyword was accepted


async def test_a_stream_cut_before_its_final_event_records_failed_with_no_tokens() -> None:
    """R2.7: nothing is estimated for a stream that never reported its usage."""
    from types import SimpleNamespace

    from app.domain.ai_config import OPENAI_BASE_URL, Connection
    from app.providers.base import StreamLimits
    from app.providers.openai_responses import OpenAIResponsesClient

    inner = OpenAIResponsesClient(
        Connection(OPENAI_BASE_URL, "k"), "m", 1, limits=StreamLimits(first_event_s=0.2, idle_s=0.03)
    )

    async def create(**_: Any) -> RawStream:
        return RawStream([delta("half an answ")], stall=True)

    inner._client = SimpleNamespace(responses=SimpleNamespace(create=create))  # type: ignore[assignment]
    sink = ListSink()
    client = RecordingCompletion(inner, role="authoring", model="m", host="api.test", sink=sink)
    with usage_scope(SCOPE), pytest.raises(ProviderTimeout):
        await call(client)
    entry = sink.one
    assert (entry.status, entry.error_code) == ("failed", "provider_timeout")
    assert (entry.input_tokens, entry.output_tokens, entry.cost_usd) == (None, None, None)
