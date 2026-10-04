"""OpenAI Realtime adapter: mints ephemeral client secrets (003 design 3.7), on the voice connection's server
(spec 014 R10).

Imports `openai`; nothing above `app/providers/` may.
"""

from __future__ import annotations

from typing import Any

from app.domain.ai_config import Connection
from app.providers._client import make_client
from app.providers._errors import translate
from app.providers.base import ClientSecret


class OpenAIRealtimeClient:
    def __init__(self, connection: Connection, timeout_s: float) -> None:
        self._client = make_client(connection, timeout_s)

    async def create_client_secret(
        self, *, session: dict[str, Any], ttl_s: int
    ) -> ClientSecret:
        try:
            res = await self._client.realtime.client_secrets.create(
                expires_after={"anchor": "created_at", "seconds": ttl_s},
                session=session,
            )
        except Exception as exc:  # noqa: BLE001 - translated, then re-raised
            raise translate(exc) from exc
        return ClientSecret(value=res.value, expires_at=int(res.expires_at))
