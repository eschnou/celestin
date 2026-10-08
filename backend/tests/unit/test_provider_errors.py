"""Spec 016 §3.4: why a provider call failed, for the log."""

from __future__ import annotations

import httpx2
import openai
import pytest

from app.domain.errors import ProviderOutputInvalid, ProviderOutputTruncated
from app.providers._errors import classify, translate
from app.providers.base import StreamBroken, StreamTimeout


def status_error(cls: type[openai.APIStatusError], status: int, message: str = "nope", **body: object):
    request = httpx2.Request("POST", "https://api.example/v1/x")
    response = httpx2.Response(status, request=request, headers={"x-request-id": "req_abc123"})
    return cls(message, response=response, body={"message": message, **body})


@pytest.mark.parametrize(
    "exc, reason",
    [
        (StreamTimeout("first_event_timeout"), "first_event_timeout"),
        (StreamTimeout("idle_timeout"), "idle_timeout"),
        (StreamBroken("stream_ended", "provider_unavailable"), "stream_ended"),
        (StreamBroken("error_event", "provider_unavailable"), "error_event"),
        (openai.APITimeoutError(request=httpx2.Request("POST", "https://x")), "transport_timeout"),
        (openai.APIConnectionError(request=httpx2.Request("POST", "https://x")), "connection"),
        (status_error(openai.InternalServerError, 500), "http_status"),
        (status_error(openai.RateLimitError, 429), "http_status"),
        (status_error(openai.BadRequestError, 400, "Streaming is not supported"), "stream_unsupported"),
        (status_error(openai.BadRequestError, 400, "unknown parameter"), "http_status"),
        (ProviderOutputTruncated("length"), "truncated"),
        (ProviderOutputInvalid("not json"), "invalid_output"),
        (RuntimeError("anything else"), "other"),
    ],
)
def test_each_failure_has_its_reason(exc: Exception, reason: str) -> None:
    assert classify(exc).reason == reason


def test_a_status_error_carries_its_status_provider_code_and_request_id() -> None:
    found = classify(status_error(openai.InternalServerError, 503, code="overloaded"))
    assert (found.error_class, found.status_code, found.request_id) == ("InternalServerError", 503, "req_abc123")
    assert found.provider_code == "overloaded"


def test_the_provider_code_and_request_id_are_cut_to_64_characters() -> None:
    exc = status_error(openai.InternalServerError, 500)
    exc.code = "c" * 200  # type: ignore[assignment]
    exc.request_id = "r" * 200
    found = classify(exc)
    assert found.provider_code == "c" * 64 and found.request_id == "r" * 64


def test_the_message_is_read_for_the_stream_test_and_never_returned() -> None:
    found = classify(status_error(openai.BadRequestError, 400, "stream SECRET-PROMPT-TEXT"))
    assert found.reason == "stream_unsupported"
    assert "SECRET" not in repr(found)


def test_translate_maps_the_stream_exceptions() -> None:
    from app.domain.errors import ProviderRateLimited, ProviderTimeout, ProviderUnavailable

    assert isinstance(translate(StreamTimeout("idle_timeout")), ProviderTimeout)
    assert isinstance(translate(StreamBroken("error_event", "provider_rate_limited")), ProviderRateLimited)
    assert isinstance(translate(StreamBroken("error_event", "provider_timeout")), ProviderTimeout)
    assert isinstance(translate(StreamBroken("stream_ended", "provider_unavailable")), ProviderUnavailable)
