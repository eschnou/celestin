"""Spec 016 R2.6: reading photographed work goes through the streamed `complete()` with no progress callback."""

from __future__ import annotations

from types import SimpleNamespace

from app.config import Settings
from app.domain.ai_config import OPENAI_BASE_URL, Connection
from app.providers.openai_responses import OpenAIResponsesClient
from app.services.work_reading import WorkReader
from tests.fixtures.fake_stream import RawStream, delta, done


class _Documents:
    async def prepare(self, photos, *, min_pixels):  # noqa: ANN001, ANN201
        page = SimpleNamespace(data_url="data:image/jpeg;base64,AA==", jpeg=b"AA")
        return SimpleNamespace(pages=[page])


class _Prompts:
    def work(self, language):  # noqa: ANN001, ANN201
        return "read the work"


async def test_a_photo_is_read_over_a_streamed_call() -> None:
    seen: dict = {}
    client = OpenAIResponsesClient(Connection(OPENAI_BASE_URL, "k"), "m", 1)

    async def create(**kwargs):  # noqa: ANN003, ANN202
        seen.update(kwargs)
        return RawStream([delta("x = "), delta("3"), done(usage={"input_tokens": 5, "output_tokens": 2})])

    client._client = SimpleNamespace(responses=SimpleNamespace(create=create))  # type: ignore[assignment]
    settings = Settings(openai_api_key="k", _env_file=None)
    reader = WorkReader(client, _Documents(), _Prompts(), settings, SimpleNamespace(config=None))  # type: ignore[arg-type]
    assert await reader.read(b"photo", "fr", "u1") == "x = 3"
    assert seen["stream"] is True
