from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.domain.errors import ProviderModelNotFound, ProviderRateLimited
from app.providers.base import Transcript
from app.providers.openai_transcription import OpenAITranscriptionClient


class _Transcriptions:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _client(outcome: Any) -> tuple[OpenAITranscriptionClient, _Transcriptions]:
    client = OpenAITranscriptionClient(Connection(OPENAI_BASE_URL, "k"), "gpt-4o-mini-transcribe", timeout_s=5)
    transcriptions = _Transcriptions(outcome)
    client._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))  # type: ignore[assignment]
    return client, transcriptions


def _http_error(cls: type, status: int) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    return cls("boom", response=httpx.Response(status, request=request, json={}), body=None)


async def test_the_call_names_the_model_the_file_and_the_language() -> None:
    client, transcriptions = _client(SimpleNamespace(text="  La somme de deux entiers.  "))
    out = await client.transcribe(audio=b"abc", filename="dictation.webm", content_type="audio/webm", language="fr")
    assert out == Transcript("La somme de deux entiers.")
    assert transcriptions.calls == [
        {
            "model": "gpt-4o-mini-transcribe",
            "file": ("dictation.webm", b"abc", "audio/webm"),
            "response_format": "json",
            "language": "fr",
        }
    ]


async def test_no_language_is_not_sent() -> None:
    client, transcriptions = _client(SimpleNamespace(text=None))
    out = await client.transcribe(audio=b"a", filename="d.mp4", content_type="audio/mp4")
    assert out.text == "" and "language" not in transcriptions.calls[0]


@pytest.mark.parametrize(
    "error, expected",
    [
        (lambda: _http_error(openai.RateLimitError, 429), ProviderRateLimited),
        (lambda: _http_error(openai.NotFoundError, 404), ProviderModelNotFound),
    ],
)
async def test_provider_failures_are_translated(error, expected) -> None:
    client, _ = _client(error())
    with pytest.raises(expected):
        await client.transcribe(audio=b"a", filename="d.webm", content_type="audio/webm")
