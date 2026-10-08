"""Spec 016 R2.2: the two adapters hand back the same result, or the same error with the same usage, for one answer."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.domain.errors import ProviderOutputInvalid, ProviderOutputTruncated
from app.providers.openai_chat import OpenAIChatClient
from app.providers.openai_responses import OpenAIResponsesClient
from app.services.authoring.schemas import CurriculumDraft
from tests.fixtures.fake_stream import RawStream, delta, done

PACK = "# Les suites\n\n## 1. Objectif\n\nUne suite est une liste de nombres.\n"
USAGE = {"input_tokens": 10, "output_tokens": 4}
CALL: dict[str, Any] = {"role": "authoring", "instructions": ["A"], "input": [], "max_output_tokens": 10}


def chunk(content: str | None = None, *, finish: str | None = None, usage: Any = None) -> Any:
    choices = [SimpleNamespace(delta=SimpleNamespace(content=content), finish_reason=finish)] if (content or finish) else []
    return SimpleNamespace(choices=choices, usage=usage)


def responses(text: str, *, truncated: bool = False) -> OpenAIResponsesClient:
    client = OpenAIResponsesClient(Connection(OPENAI_BASE_URL, "k"), "m", 1)
    half = len(text) // 2
    events = [delta(text[:half]), delta(text[half:]), done("", "incomplete" if truncated else "completed", USAGE)]

    async def create(**_: Any) -> RawStream:
        return RawStream(events)

    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))  # type: ignore[assignment]
    return client


def chat(text: str, *, truncated: bool = False) -> OpenAIChatClient:
    client = OpenAIChatClient(Connection("http://localhost:11434/v1", None, "chat"), "m", 1)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=4)
    half = len(text) // 2
    stream = RawStream(
        [chunk(text[:half]), chunk(text[half:]), chunk(finish="length" if truncated else "stop"), chunk(usage=usage)]
    )

    async def create(**_: Any) -> RawStream:
        return stream

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))  # type: ignore[assignment]
    return client


async def outcome(client: Any, **extra: Any) -> tuple[Any, ...]:
    try:
        result = await client.complete(**CALL, **extra)
    except (ProviderOutputTruncated, ProviderOutputInvalid) as exc:
        return (type(exc).__name__, exc.usage)
    return ("ok", result.text, result.data, result.usage)


@pytest.mark.parametrize(
    "text, truncated, extra",
    [
        (PACK, False, {}),
        ('{"title": "T", "sections": []}', False, {"schema": CurriculumDraft}),
        ("{not json", False, {"schema": CurriculumDraft}),
        ("# Les suit", True, {}),
    ],
    ids=["pack", "curriculum", "invalid json", "truncated"],
)
async def test_both_adapters_agree(text: str, truncated: bool, extra: dict[str, Any]) -> None:
    assert await outcome(responses(text, truncated=truncated), **extra) == await outcome(chat(text, truncated=truncated), **extra)
