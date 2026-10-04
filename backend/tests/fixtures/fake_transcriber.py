"""Scripted TranscriptionClient: records what it was handed."""

from __future__ import annotations

from typing import Any

from app.providers.base import Transcript


class FakeTranscriber:
    def __init__(self, text: str = "La somme de deux entiers relatifs.") -> None:
        self._text = text
        self.calls: list[dict[str, Any]] = []

    async def transcribe(self, **kwargs: Any) -> Transcript:
        self.calls.append(kwargs)
        return Transcript(self._text)


class ExplodingTranscriber:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def transcribe(self, **_: Any) -> Transcript:
        raise self._error
