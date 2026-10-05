"""Dictation: one recording in, the written text out.

The recording is read, transcribed and forgotten: nothing is stored, not the audio and not the text (the
browser puts the text in the composer, and what the student sends is an ordinary message). The route spends
money on request, so it is rate-limited per user like the voice mint.
"""

from __future__ import annotations

import logging
import time

from app.config import Settings
from app.domain.ai_config import priced
from app.domain.errors import InvalidAudio
from app.domain.usage import UsageScope, usage_scope
from app.providers.base import AiConfigSource, TranscriptionClient

log = logging.getLogger(__name__)

# What a browser's MediaRecorder produces (Chrome and Firefox: webm or ogg; Safari: mp4), and what the
# providers' transcription endpoints accept besides.
_EXTENSIONS: dict[str, str] = {
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


def audio_extension(content_type: str | None) -> str | None:
    """The file extension for a content type (`audio/webm;codecs=opus` is webm), None for anything else."""
    base = (content_type or "").split(";", 1)[0].strip().lower()
    return _EXTENSIONS.get(base)


class DictationService:
    def __init__(self, transcriber: TranscriptionClient, settings: Settings, ai: AiConfigSource) -> None:
        self._transcriber = transcriber
        self._s = settings
        self._ai = ai

    async def dictate(
        self, *, audio: bytes, content_type: str | None, language: str | None, duration_ms: int | None, user_id: str
    ) -> str:
        extension = audio_extension(content_type)
        if extension is None or not audio:
            raise InvalidAudio()
        started = time.monotonic()
        seconds = min(max(duration_ms or 0, 0) / 1000, self._s.dictation_max_s)
        with usage_scope(UsageScope(user_id, "dictation", audio_seconds=round(seconds, 1))):  # the usage ledger (spec 015)
            transcript = await self._transcriber.transcribe(
                audio=audio,
                filename=f"dictation.{extension}",
                content_type=(content_type or "").split(";", 1)[0].strip().lower(),
                language=language,
            )
        config = self._ai.config
        connection = config.dictation.connection if config and config.dictation else None
        # OpenAI's prices only mean something for OpenAI (or a price the operator set).
        cost = (
            round(seconds / 60 * self._s.dictation_price_per_min, 5)
            if priced(self._s, connection, "dictation_price_per_min")
            else 0.0
        )
        log.info(
            "dictation",
            extra={
                "user_id": user_id,
                "language": language,
                "bytes": len(audio),
                "audio_s": round(seconds, 1),
                "chars": len(transcript.text),
                "ms": round((time.monotonic() - started) * 1000),
                "cost_usd": cost,
            },
        )
        return transcript.text
