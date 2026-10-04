"""Asks a server whether a connection works, without spending a token (spec 013 §3.6, spec 014 §3.5).

`GET <base>/models` authenticates the key and is free. A restricted OpenAI key without the models scope is
answered `403` although it is valid for the Responses API, and a local server may have no models route at
all, so only `401` means « rejected »: a `403`, or a missing route, is `ok` and `limited`.

Nothing here logs or re-raises the provider's text: it can echo part of the key.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import openai
from openai import AsyncOpenAI

from app.domain.ai_config import Connection
from app.providers._client import make_client
from app.providers.base import ModelVisibility, ProbeResult

MAX_LISTED = 500
# The listing says « I have no such route »: the server may still answer the calls the application makes.
_NO_LISTING = (404, 405, 501)


class OpenAIConnectionProbe:
    def __init__(self, timeout_s: float = 15.0) -> None:
        self._timeout_s = timeout_s

    async def check(self, connection: Connection, models: Sequence[str] = ()) -> ProbeResult:
        client = make_client(connection, self._timeout_s, max_retries=0)
        wanted = list(models)
        try:
            available: list[str] = []
            try:
                listing = await client.models.list()
                available = sorted({item.id for item in getattr(listing, "data", [])})[:MAX_LISTED]
            except openai.AuthenticationError:
                return ProbeResult("rejected")
            except openai.PermissionDeniedError:
                return ProbeResult("ok", limited=True, models=[ModelVisibility(m, None) for m in wanted])
            except openai.APIStatusError as exc:
                if exc.status_code in _NO_LISTING:
                    return ProbeResult("ok", limited=True, models=[ModelVisibility(m, None) for m in wanted])
                if exc.status_code != 429:  # a limit means it authenticated: the key is not at fault
                    return ProbeResult("unreachable")
            except Exception:  # noqa: BLE001 - connection, timeout, bad body: the server could not be asked
                return ProbeResult("unreachable")
            seen = await asyncio.gather(*(_visibility(client, m, available) for m in wanted))
            return ProbeResult("ok", models=list(seen), available=available)
        finally:
            await client.close()


async def _visibility(client: AsyncOpenAI, model: str, listed: list[str]) -> ModelVisibility:
    """In the listing: visible. Not in it: ask for the model itself (a listing can be capped or leave out an
    alias), which a server answers `404` for an id it does not know. The listing comes first because many
    open-model ids hold a slash (`openai/gpt-oss-120b`) that a path-style lookup does not resolve."""
    if model in listed:
        return ModelVisibility(model, True)
    try:
        await client.models.retrieve(model)
    except openai.NotFoundError:
        return ModelVisibility(model, False)
    except Exception:  # noqa: BLE001 - restricted, rate-limited, unreachable: the key cannot tell
        return ModelVisibility(model, None)
    return ModelVisibility(model, True)
