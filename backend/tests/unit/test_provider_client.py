"""Spec 014 §3.5: the one place an SDK client is built."""

from __future__ import annotations

import httpx
import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.providers._client import PLACEHOLDER_KEY, make_client


def test_the_client_talks_to_the_connections_server_with_its_key() -> None:
    client = make_client(Connection("https://api.groq.com/openai/v1", "gsk-1"), 12.0)
    assert str(client.base_url) == "https://api.groq.com/openai/v1/" and client.api_key == "gsk-1"
    assert client.timeout == 12.0 and client.max_retries == 2


def test_a_keyless_server_gets_a_placeholder() -> None:
    assert make_client(Connection("http://localhost:11434/v1"), 5.0).api_key == PLACEHOLDER_KEY


def test_retries_can_be_turned_off() -> None:
    assert make_client(Connection(OPENAI_BASE_URL, "k"), 5.0, max_retries=0).max_retries == 0


async def test_a_redirect_is_not_followed_so_the_key_stays_with_the_named_host() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "api.example":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        return httpx.Response(200, json={"data": []})

    client = make_client(Connection("https://api.example/v1", "secret-key"), 5.0, max_retries=0)
    client._client._transport = httpx.MockTransport(handler)  # the SDK's httpx client, with a fake network
    with pytest.raises(Exception) as raised:
        await client.models.list()
    assert [r.url.host for r in seen] == ["api.example"]  # evil.example was never contacted
    assert "secret-key" not in str(raised.value)
