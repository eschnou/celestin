"""Spec 014 §3.5: the one place an SDK client is built."""

from __future__ import annotations

import httpx
import httpx2
import openai
import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.providers._client import PLACEHOLDER_KEY, make_client


def test_the_client_talks_to_the_connections_server_with_its_key() -> None:
    client = make_client(Connection("https://api.groq.com/openai/v1", "gsk-1"), 12.0)
    assert str(client.base_url) == "https://api.groq.com/openai/v1/" and client.api_key == "gsk-1"
    assert client.timeout == 12.0 and client.max_retries == 0


def test_a_keyless_server_gets_a_placeholder() -> None:
    assert make_client(Connection("http://localhost:11434/v1"), 5.0).api_key == PLACEHOLDER_KEY


def test_nothing_is_retried_and_nothing_can_turn_retries_back_on() -> None:
    """Spec 016 R1: a retried generation restarts from zero, is billed again, and nobody sees it."""
    import inspect

    assert make_client(Connection(OPENAI_BASE_URL, "k"), 5.0).max_retries == 0
    assert "max_retries" not in inspect.signature(make_client).parameters


async def test_a_server_error_is_raised_on_the_first_failure_and_sent_once() -> None:
    sent: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(500, json={"error": {"message": "boom"}})

    client = make_client(Connection("https://api.example/v1", "k"), 5.0)
    client._client._transport = httpx2.MockTransport(handler)  # the SDK's own httpx
    with pytest.raises(openai.InternalServerError):
        await client.chat.completions.create(model="m", messages=[])
    assert len(sent) == 1


async def test_a_rate_limit_is_not_waited_out() -> None:
    sent: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(429, headers={"retry-after": "1"}, json={"error": {"message": "slow down"}})

    client = make_client(Connection("https://api.example/v1", "k"), 5.0)
    client._client._transport = httpx2.MockTransport(handler)
    with pytest.raises(openai.RateLimitError):
        await client.chat.completions.create(model="m", messages=[])
    assert len(sent) == 1


async def test_a_redirect_is_not_followed_so_the_key_stays_with_the_named_host() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "api.example":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        return httpx.Response(200, json={"data": []})

    client = make_client(Connection("https://api.example/v1", "secret-key"), 5.0)
    client._client._transport = httpx.MockTransport(handler)  # the SDK's httpx client, with a fake network
    with pytest.raises(Exception) as raised:
        await client.models.list()
    assert [r.url.host for r in seen] == ["api.example"]  # evil.example was never contacted
    assert "secret-key" not in str(raised.value)
