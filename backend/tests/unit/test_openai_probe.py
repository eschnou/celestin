"""Specs 013 §3.6, 014 §3.5: what the probe makes of a server's answers. No network: a fake client."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.providers import openai_probe
from app.providers.base import ModelVisibility
from app.providers.openai_probe import MAX_LISTED, OpenAIConnectionProbe

KEY = "sk-very-secret-key-123456"
CONNECTION = Connection(OPENAI_BASE_URL, KEY)


def status_error(cls: type[openai.APIStatusError], status: int):
    request = httpx.Request("GET", "https://api.openai.com/v1/models")
    response = httpx.Response(status, request=request, json={"error": {"message": f"Incorrect API key: {KEY}"}})
    return cls(f"Incorrect API key provided: {KEY}", response=response, body=None)


class FakeModels:
    def __init__(self, listing=None, retrieve=None) -> None:
        self._listing, self._retrieve = listing, retrieve or {}
        self.retrieved: list[str] = []

    async def list(self):
        if isinstance(self._listing, Exception):
            raise self._listing
        ids = self._listing if isinstance(self._listing, list) else []
        return SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])

    async def retrieve(self, model: str):
        self.retrieved.append(model)
        outcome = self._retrieve.get(model)
        if isinstance(outcome, Exception):
            raise outcome
        return object()


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, models: FakeModels, **kwargs) -> None:
        self.models, self.kwargs, self.closed = models, kwargs, False
        FakeClient.instances.append(self)

    async def close(self) -> None:
        self.closed = True


def probe_with(monkeypatch, models: FakeModels) -> OpenAIConnectionProbe:
    FakeClient.instances = []
    monkeypatch.setattr(openai_probe, "make_client", lambda connection, timeout_s, **kwargs: FakeClient(
        models, connection=connection, timeout_s=timeout_s, **kwargs))
    return OpenAIConnectionProbe(timeout_s=3)


async def test_an_accepted_key_is_ok_and_the_client_is_closed(monkeypatch) -> None:
    result = await probe_with(monkeypatch, FakeModels()).check(CONNECTION)
    assert (result.status, result.limited, result.models) == ("ok", False, [])
    (client,) = FakeClient.instances
    assert client.closed and client.kwargs == {"connection": CONNECTION, "timeout_s": 3}


async def test_a_401_is_rejected(monkeypatch) -> None:
    result = await probe_with(monkeypatch, FakeModels(status_error(openai.AuthenticationError, 401))).check(CONNECTION, ["m"])
    assert result.status == "rejected" and result.models == []


async def test_a_403_is_ok_but_limited_and_the_models_are_unknown(monkeypatch) -> None:
    models = FakeModels(status_error(openai.PermissionDeniedError, 403))
    result = await probe_with(monkeypatch, models).check(CONNECTION, ["a", "b"])
    assert result.status == "ok" and result.limited is True
    assert result.models == [ModelVisibility("a", None), ModelVisibility("b", None)]
    assert models.retrieved == []


async def test_a_429_still_authenticated(monkeypatch) -> None:
    result = await probe_with(monkeypatch, FakeModels(status_error(openai.RateLimitError, 429))).check(CONNECTION)
    assert result.status == "ok" and result.limited is False


@pytest.mark.parametrize(
    "error",
    [
        openai.APIConnectionError(request=httpx.Request("GET", "https://api.openai.com")),
        openai.APITimeoutError(request=httpx.Request("GET", "https://api.openai.com")),
        status_error(openai.InternalServerError, 500),
        RuntimeError("boom"),
    ],
)
async def test_the_provider_that_cannot_be_asked_is_unreachable(monkeypatch, error) -> None:
    assert (await probe_with(monkeypatch, FakeModels(error)).check(CONNECTION)).status == "unreachable"


async def test_each_requested_model_is_looked_up(monkeypatch) -> None:
    models = FakeModels(
        retrieve={
            "gone": status_error(openai.NotFoundError, 404),
            "hidden": status_error(openai.PermissionDeniedError, 403),
            "flaky": RuntimeError("boom"),
        }
    )
    result = await probe_with(monkeypatch, models).check(CONNECTION, ["fine", "gone", "hidden", "flaky"])
    assert result.status == "ok"
    assert result.models == [
        ModelVisibility("fine", True),
        ModelVisibility("gone", False),
        ModelVisibility("hidden", None),
        ModelVisibility("flaky", None),
    ]


async def test_neither_the_key_nor_the_provider_text_is_logged(monkeypatch, caplog) -> None:
    models = FakeModels(status_error(openai.AuthenticationError, 401))
    with caplog.at_level(logging.DEBUG):
        result = await probe_with(monkeypatch, models).check(CONNECTION)
    assert KEY not in caplog.text and KEY not in repr(result)


async def test_the_listed_ids_are_sorted_unique_and_capped(monkeypatch) -> None:
    ids = [f"m{n:04d}" for n in range(MAX_LISTED + 50)] + ["m0001"]
    result = await probe_with(monkeypatch, FakeModels(ids)).check(CONNECTION)
    assert result.available == sorted(set(ids))[:MAX_LISTED] and len(result.available) == MAX_LISTED


@pytest.mark.parametrize("status", [404, 405, 501])
async def test_a_server_without_a_models_route_is_ok_but_limited(monkeypatch, status) -> None:
    models = FakeModels(status_error(openai.APIStatusError, status))
    result = await probe_with(monkeypatch, models).check(Connection("http://localhost:8080/v1"), ["m"])
    assert result.status == "ok" and result.limited is True and result.models == [ModelVisibility("m", None)]
    assert models.retrieved == []


async def test_a_redirect_or_other_status_is_unreachable(monkeypatch) -> None:
    result = await probe_with(monkeypatch, FakeModels(status_error(openai.APIStatusError, 302))).check(CONNECTION)
    assert result.status == "unreachable"


async def test_a_model_in_the_listing_is_visible_without_a_lookup(monkeypatch) -> None:
    """Ids with a slash (`openai/gpt-oss-120b`) are not found by a path-style lookup: the listing decides."""
    models = FakeModels(["openai/gpt-oss-120b", "qwen/qwen3.6-27b"], retrieve={"unlisted": status_error(openai.NotFoundError, 404)})
    result = await probe_with(monkeypatch, models).check(CONNECTION, ["openai/gpt-oss-120b", "unlisted"])
    assert result.models == [ModelVisibility("openai/gpt-oss-120b", True), ModelVisibility("unlisted", False)]
    assert models.retrieved == ["unlisted"]
