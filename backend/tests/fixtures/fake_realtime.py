"""Scripted RealtimeClient: records the session it was handed."""

from __future__ import annotations

from typing import Any

from app.providers.base import ClientSecret


class FakeRealtime:
    def __init__(self, secret: str = "ek_test_secret", expires_at: int = 1_800_000_000) -> None:
        self._secret = ClientSecret(value=secret, expires_at=expires_at)
        self.sessions: list[dict[str, Any]] = []
        self.ttls: list[int] = []

    async def create_client_secret(self, *, session: dict[str, Any], ttl_s: int) -> ClientSecret:
        self.sessions.append(session)
        self.ttls.append(ttl_s)
        return self._secret


class ExplodingRealtime:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    async def create_client_secret(self, **_: Any) -> ClientSecret:
        self.calls += 1
        raise self._error
