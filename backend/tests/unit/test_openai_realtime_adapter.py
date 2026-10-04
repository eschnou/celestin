from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.domain.errors import ProviderRateLimited, ProviderRejectedRequest, ProviderTimeout
from app.providers.base import ClientSecret
from app.providers.openai_realtime import OpenAIRealtimeClient


class _Secrets:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(outcomes: list[Any]) -> tuple[OpenAIRealtimeClient, _Secrets]:
    client = OpenAIRealtimeClient(Connection(OPENAI_BASE_URL, "k"), timeout_s=5)
    secrets = _Secrets(outcomes)
    client._client = SimpleNamespace(realtime=SimpleNamespace(client_secrets=secrets))  # type: ignore[assignment]
    return client, secrets


def _http_error(cls: type, status: int, message: str) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/realtime/client_secrets")
    response = httpx.Response(status, request=request, json={"error": {"message": message}})
    return cls(message, response=response, body=None)


OK = SimpleNamespace(value="ek_abc", expires_at=1_800_000_000)


async def test_call_shape_and_mapping() -> None:
    client, secrets = _client([OK])
    out = await client.create_client_secret(session={"type": "realtime", "model": "m"}, ttl_s=90)
    assert out == ClientSecret(value="ek_abc", expires_at=1_800_000_000)
    assert secrets.calls == [
        {"expires_after": {"anchor": "created_at", "seconds": 90}, "session": {"type": "realtime", "model": "m"}}
    ]


async def test_rate_limit_translated() -> None:
    client, _ = _client([_http_error(openai.RateLimitError, 429, "slow down")])
    with pytest.raises(ProviderRateLimited):
        await client.create_client_secret(session={}, ttl_s=10)


async def test_timeout_translated() -> None:
    client, _ = _client([openai.APITimeoutError(httpx.Request("POST", "https://x"))])
    with pytest.raises(ProviderTimeout):
        await client.create_client_secret(session={}, ttl_s=10)


async def test_bad_request_translated() -> None:
    client, secrets = _client([_http_error(openai.BadRequestError, 400, "bad voice")])
    with pytest.raises(ProviderRejectedRequest):  # a ProviderUnavailable, told apart
        await client.create_client_secret(session={"reasoning": {"effort": "low"}}, ttl_s=10)
    assert len(secrets.calls) == 1


def test_the_client_talks_to_the_connections_server() -> None:
    client = OpenAIRealtimeClient(Connection("https://realtime.example/v1", "k"), timeout_s=5)
    assert str(client._client.base_url) == "https://realtime.example/v1/"
    assert client._client.api_key == "k"
