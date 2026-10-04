"""Mint one real Realtime client secret. Opt-in, never part of the default test run.

    uv run python -m scripts.voice_smoke

Proves the session configuration (prompt, pack, tools, audio settings) is accepted
by the API. No audio is exchanged and nothing is billed beyond the request.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.services.voice_service import VoiceService
from scripts import ai_clients
from scripts.smoke import context_for, load_lesson


async def main() -> int:
    settings = get_settings()
    prompts, chapter = load_lesson(settings, sys.argv)
    hub = ai_clients.hub(settings)
    assert hub.config is not None
    if hub.config.voice is None:
        print("No voice connection: voice needs OpenAI as the default connection, or a connection of its own (VOICE_BASE_URL).")
        return 1
    print(f"--- {ai_clients.describe(hub.config, 'voice')} ---")
    service = VoiceService(hub.realtime, prompts, settings, hub)
    try:
        res = await service.create_session(chapter, [], context_for(chapter))
    except Exception as exc:  # noqa: BLE001 - a smoke script reports and exits
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    print(f"secret: {res.secret[:6]}… expires_at={res.expires_at}")
    print(f"model: {res.model}  voice: {res.voice}  seed items: {len(res.seed)}  opening: {res.opening}")
    print("VOICE OK" if res.secret.startswith("ek_") else "unexpected secret prefix")
    return 0 if res.secret.startswith("ek_") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
