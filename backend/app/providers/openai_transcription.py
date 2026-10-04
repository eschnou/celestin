"""Speech to text over `/audio/transcriptions` (dictation), on the voice connection's server.

Imports `openai`; nothing above `app/providers/` may.
"""

from __future__ import annotations

from typing import Any

from app.domain.ai_config import Connection
from app.providers._client import make_client
from app.providers._errors import translate
from app.providers.base import Transcript


class OpenAITranscriptionClient:
    def __init__(self, connection: Connection, model: str, timeout_s: float) -> None:
        self._client = make_client(connection, timeout_s)
        self.model = model

    async def transcribe(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        language: str | None = None,
    ) -> Transcript:
        options: dict[str, Any] = {"model": self.model, "file": (filename, audio, content_type), "response_format": "json"}
        if language:
            options["language"] = language
        try:
            result = await self._client.audio.transcriptions.create(**options)
        except Exception as exc:  # noqa: BLE001 - translated, then re-raised
            raise translate(exc) from exc
        return Transcript(text=(result.text or "").strip())
