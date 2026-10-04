"""Scripted ConnectionProbe: what a server says about a connection, without the network (specs 013, 014)."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.ai_config import Connection
from app.providers.base import ProbeResult


class FakeProbe:
    """One answer for every connection (`result`), or one per host (`by_host`)."""

    def __init__(self, result: ProbeResult | None = None, by_host: dict[str, ProbeResult] | None = None) -> None:
        self.result = result or ProbeResult("ok")
        self.by_host = by_host or {}
        self.calls: list[tuple[Connection, list[str]]] = []

    async def check(self, connection: Connection, models: Sequence[str] = ()) -> ProbeResult:
        self.calls.append((connection, list(models)))
        return self.by_host.get(connection.host, self.result)

    @property
    def hosts(self) -> list[str]:
        return [connection.host for connection, _ in self.calls]
