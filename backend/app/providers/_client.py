"""The one place an SDK client is built (spec 014 §3.5). Imports `openai`; nothing above providers may."""

from __future__ import annotations

from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from app.domain.ai_config import Connection

# A server that needs no key still gets one: the SDK refuses to build a client without.
PLACEHOLDER_KEY = "no-key"


def make_client(connection: Connection, timeout_s: float) -> AsyncOpenAI:
    """A client for one connection. Redirects are not followed: the bearer key must go to the host the
    administrator named, and nowhere a server decides to send it. Nothing is retried by the SDK (spec 016 R1):
    a retried generation restarts from zero, is billed again and nobody sees it; the student retries."""
    return AsyncOpenAI(
        api_key=connection.api_key or PLACEHOLDER_KEY,
        base_url=connection.base_url,
        timeout=timeout_s,
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(timeout=timeout_s, follow_redirects=False),
    )
