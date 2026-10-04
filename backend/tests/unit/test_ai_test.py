"""Spec 014 §3.9: the live checks, each passing and each failing, with scripted clients. No network."""

from __future__ import annotations

import asyncio
import base64
import io
import logging

import pytest

from app.domain.ai_config import OPENAI_BASE_URL, AiConfig, Connection, RoleConfig
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
from app.providers.base import Completed, CompletionResult, Failed, TextDelta
from app.providers.hub import Clients
from app.services import ai_test
from app.services.ai_test import (
    EXPECTED_NUMBER,
    number_image_data_url,
    run_check,
    run_live_checks,
)
from tests.conftest import CARD, tool_call
from tests.fixtures.fake_completion import FakeCompletion, data, text
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM
from tests.fixtures.fake_realtime import ExplodingRealtime, FakeRealtime

CONN = Connection(OPENAI_BASE_URL, "k")
BOARD = tool_call("display_board", {"card": CARD})
PING = {"ok": True, "word": "bonjour"}
READ = text(f"The number is {EXPECTED_NUMBER}.")


def clients(
    tutor=None, authoring=None, transcription=None, realtime=None, voice: bool = True
) -> Clients:
    def role(name: str, model: str) -> RoleConfig:
        return RoleConfig(name, model, None, CONN)  # type: ignore[arg-type]

    config = AiConfig(role("tutor", "t"), role("authoring", "a"), role("transcription", "v"), role("voice", "rt") if voice else None)
    return Clients(
        config=config,
        tutor=tutor or FakeLLM([[BOARD, Completed()]]),
        authoring=authoring or FakeCompletion([data(PING)]),
        transcription=transcription or FakeCompletion([READ]),
        realtime=(realtime or FakeRealtime()) if voice else None,
    )


# ------------------------------------------------------------------ the tutor


async def test_a_tutor_that_calls_the_board_tool_correctly_passes() -> None:
    c = clients()
    assert await run_check("tutor", c) is None
    (call,) = c.tutor.calls  # type: ignore[attr-defined]
    names = [t["name"] for t in c.tutor.tools]  # type: ignore[attr-defined]
    assert "display_board" in names and len(names) == 5  # the application's own tools, not a toy
    assert [i["role"] for i in call["input"]] == ["developer", "user"]


@pytest.mark.parametrize(
    "events, code",
    [
        ([tool_call("display_board", {"title": "flat"}), Completed()], "tool_arguments"),
        ([tool_call("display_board", {}), Completed()], "tool_arguments"),
        ([tool_call("clear_board", {}), Completed()], "tool_arguments"),
        ([TextDelta("Bonjour"), Completed()], "no_tool_calls"),
        ([Completed()], "no_tool_calls"),
        ([Failed("provider_unavailable", "boom")], "other"),
        ([Failed("provider_unavailable", "provider failure"), Failed("provider_unavailable", "Tool call validation failed: …")], "tool_arguments"),
        ([Failed("provider_unavailable", "failed: tool call validation"), Failed("provider_unavailable", "provider failure")], "tool_arguments"),
    ],
)
async def test_a_tutor_that_cannot_call_the_board_tool_says_why(events, code) -> None:
    assert await run_check("tutor", clients(tutor=FakeLLM([events]))) == code


@pytest.mark.parametrize(
    "error, code",
    [
        (ProviderAuthRejected(), "rejected"),
        (ProviderModelNotFound(), "model_not_found"),
        (ProviderRejectedRequest(), "no_tool_calls"),
        (ProviderTimeout(), "unreachable"),
        (ProviderUnavailable(), "unreachable"),
        (ProviderRateLimited(), "other"),
        (RuntimeError("boom"), "other"),
    ],
)
async def test_a_tutor_request_that_fails_is_classified(error, code) -> None:
    assert await run_check("tutor", clients(tutor=ExplodingLLM(error))) == code


# ------------------------------------------------------------------ authoring


async def test_authoring_that_follows_a_schema_passes() -> None:
    c = clients()
    assert await run_check("authoring", c) is None
    (call,) = c.authoring.calls  # type: ignore[attr-defined]
    assert call["role"] == "authoring" and call["schema"].__name__ == "Ping"


@pytest.mark.parametrize(
    "outcome, code",
    [
        (ProviderOutputInvalid("not json"), "schema_unsupported"),
        (data({"unexpected": 1}), "schema_unsupported"),
        (data({"ok": "yes", "word": 3}), "schema_unsupported"),
        (CompletionResult(text="{}", data=None), "schema_unsupported"),
        (ProviderRejectedRequest(), "schema_unsupported"),
        (ProviderOutputTruncated("length"), "other"),
        (ProviderModelNotFound(), "model_not_found"),
        (ProviderAuthRejected(), "rejected"),
    ],
)
async def test_authoring_that_cannot_is_classified(outcome, code) -> None:
    assert await run_check("authoring", clients(authoring=FakeCompletion([outcome]))) == code


# ------------------------------------------------------------------ transcription


async def test_a_model_that_reads_the_image_passes_and_was_given_one() -> None:
    c = clients()
    assert await run_check("transcription", c) is None
    (call,) = c.transcription.calls  # type: ignore[attr-defined]
    assert call["role"] == "transcription"
    image = next(p for p in call["input"][0]["content"] if p["type"] == "input_image")
    assert image["image_url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    "outcome, code",
    [
        (text("I cannot see any image."), "no_image_input"),
        (text(""), "no_image_input"),
        (ProviderRejectedRequest(), "no_image_input"),
        (ProviderModelNotFound(), "model_not_found"),
        (ProviderUnavailable(), "unreachable"),
    ],
)
async def test_a_model_that_cannot_read_the_image_is_classified(outcome, code) -> None:
    assert await run_check("transcription", clients(transcription=FakeCompletion([outcome]))) == code


def test_the_test_image_is_a_real_png_that_says_42() -> None:
    from PIL import Image

    url = number_image_data_url()
    image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert image.format == "PNG" and image.size[0] >= 100
    dark = sum(image.convert("L").histogram()[:100])
    assert dark > 100  # there is something drawn on it
    assert number_image_data_url() is url  # drawn once


# ------------------------------------------------------------------ voice


async def test_voice_mints_a_secret_with_its_model_and_no_audio() -> None:
    realtime = FakeRealtime()
    assert await run_check("voice", clients(realtime=realtime)) is None
    assert realtime.sessions == [{"type": "realtime", "model": "rt"}] and realtime.ttls == [10]


@pytest.mark.parametrize(
    "error, code",
    [(ProviderAuthRejected(), "rejected"), (ProviderModelNotFound(), "model_not_found"),
     (ProviderRejectedRequest(), "other"), (ProviderUnavailable(), "unreachable")],
)
async def test_voice_that_cannot_mint_is_classified(error, code) -> None:
    assert await run_check("voice", clients(realtime=ExplodingRealtime(error))) == code


# ------------------------------------------------------------------ all of them


async def test_every_role_the_configuration_has_is_checked_together() -> None:
    results = await run_live_checks(clients())
    assert results == {"tutor": None, "authoring": None, "transcription": None, "voice": None}
    assert list(await run_live_checks(clients(voice=False))) == ["tutor", "authoring", "transcription"]


async def test_one_failing_role_does_not_stop_the_others() -> None:
    results = await run_live_checks(clients(authoring=FakeCompletion([ProviderOutputInvalid("x")])))
    assert results["authoring"] == "schema_unsupported" and results["tutor"] is None


async def test_a_check_that_takes_too_long_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_test, "CHECK_TIMEOUT_S", 0.05)
    slow = FakeCompletion([data(PING)], delay_s=1.0)
    assert await run_check("authoring", clients(authoring=slow)) == "unreachable"


async def test_the_log_carries_the_outcome_and_nothing_the_provider_said(caplog: pytest.LogCaptureFixture) -> None:
    secret_text = "sk-secret-provider-text"
    with caplog.at_level(logging.INFO):
        await run_check("authoring", clients(authoring=FakeCompletion([RuntimeError(secret_text)])))
        await run_check("tutor", clients())
    records = [r for r in caplog.records if r.message == "ai_test"]
    assert [(r.role, r.live) for r in records] == [("authoring", "other"), ("tutor", "ok")]  # type: ignore[attr-defined]
    assert secret_text not in caplog.text and all(isinstance(r.ms, int) for r in records)  # type: ignore[attr-defined]
