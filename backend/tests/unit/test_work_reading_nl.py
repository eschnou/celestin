"""Spec 017 task 5.7: a photo of a Dutch student's work is read with the Dutch prompt and the Dutch marks."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.routes.work import _NOTHING
from app.config import Settings
from app.services.work_reading import _DOUBT, _PHOTO_LABEL, WorkReader
from tests.fixtures.fake_completion import FakeCompletion, text
from tests.unit.test_authoring_agent_nl import PROMPTS


class _Documents:
    async def prepare(self, photos, *, min_pixels):  # noqa: ANN001, ANN201
        return SimpleNamespace(pages=[SimpleNamespace(data_url="data:image/jpeg;base64,AA==", jpeg=b"AA")])


def reader(fake: FakeCompletion) -> WorkReader:
    settings = Settings(openai_api_key="k", _env_file=None)
    return WorkReader(fake, _Documents(), PROMPTS, settings, SimpleNamespace(config=None))  # type: ignore[arg-type]


async def test_the_photo_is_read_with_the_dutch_prompt_and_label() -> None:
    fake = FakeCompletion([text("$x + 3 = 7$\n$x = 7 - 3 = 4$\n[onzeker: 4 | 9]")])
    result = await reader(fake).read(b"photo", "nl", "u1")
    assert result.startswith("$x + 3 = 7$") and "[onzeker: 4 | 9]" in result
    (call,) = fake.calls
    assert call["instructions"] == [PROMPTS.work("nl")]
    assert call["input"][0]["content"][0]["text"] == _PHOTO_LABEL["nl"] == "Hier is de foto van het werk van de leerling."


def test_the_dutch_marks_are_recognised_by_the_route_and_the_log() -> None:
    assert "[niets leesbaar]" in _NOTHING and "[rien de lisible]" in _NOTHING and "[nothing legible]" in _NOTHING
    assert len(_DOUBT.findall("a [onzeker: 1 | 7] b [uncertain: 2 | 3] c [incertain: 4 | 5]")) == 3
