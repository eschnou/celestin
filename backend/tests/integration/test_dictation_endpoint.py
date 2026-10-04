"""The dictation route: one recording in, the text out, offline."""

from __future__ import annotations

import pytest

from app.domain.errors import ProviderUnavailable
from tests.fixtures.fake_transcriber import ExplodingTranscriber, FakeTranscriber

AUDIO = b"\x1a\x45\xdf\xa3 not really opus"


def recording(content_type: str = "audio/webm;codecs=opus", data: bytes = AUDIO):
    return {"audio": ("dictation.webm", data, content_type)}


async def test_a_recording_becomes_text(make_dictation_client, caplog: pytest.LogCaptureFixture) -> None:
    transcriber = FakeTranscriber()
    async with make_dictation_client(transcriber) as client:
        with caplog.at_level("INFO"):
            r = await client.post(
                "/api/dictation", files=recording(), data={"language": "fr", "duration_ms": "4200"}
            )
    assert r.status_code == 200 and r.json() == {"text": "La somme de deux entiers relatifs."}
    call = transcriber.calls[0]
    assert (call["audio"], call["filename"], call["content_type"], call["language"]) == (
        AUDIO, "dictation.webm", "audio/webm", "fr",  # the codecs parameter is dropped: providers reject it
    )
    record = next(r for r in caplog.records if r.getMessage() == "dictation")
    assert (record.bytes, record.audio_s, record.chars) == (len(AUDIO), 4.2, 34)  # type: ignore[attr-defined]
    assert "somme" not in caplog.text  # what was said is never logged


async def test_the_course_language_is_passed_on(make_dictation_client) -> None:
    transcriber = FakeTranscriber("Hello")
    async with make_dictation_client(transcriber) as client:
        r = await client.post("/api/dictation", files=recording("audio/mp4", b"mp4!"), data={"language": "en"})
    assert r.status_code == 200
    assert (transcriber.calls[0]["language"], transcriber.calls[0]["filename"]) == ("en", "dictation.mp4")


async def test_a_recording_without_a_language_is_transcribed_without_a_hint(make_dictation_client) -> None:
    """A language course mixes two languages: the browser then sends no hint at all."""
    transcriber = FakeTranscriber("Ik heb een boek.")
    async with make_dictation_client(transcriber) as client:
        r = await client.post("/api/dictation", files=recording())
    assert r.status_code == 200 and transcriber.calls[0]["language"] is None


async def test_silence_is_an_empty_text_not_an_error(make_dictation_client) -> None:
    async with make_dictation_client(FakeTranscriber("")) as client:
        r = await client.post("/api/dictation", files=recording())
    assert r.status_code == 200 and r.json() == {"text": ""}


@pytest.mark.parametrize(
    "files",
    [recording("text/plain"), recording("application/octet-stream"), recording(data=b"")],
    ids=["text", "binary", "empty"],
)
async def test_what_is_not_audio_is_refused(make_dictation_client, files) -> None:
    transcriber = FakeTranscriber()
    async with make_dictation_client(transcriber) as client:
        r = await client.post("/api/dictation", files=files)
    assert r.status_code == 422 and r.json()["code"] == "invalid_audio" and transcriber.calls == []


async def test_a_language_the_course_cannot_have_is_refused(make_dictation_client) -> None:
    async with make_dictation_client(FakeTranscriber()) as client:
        r = await client.post("/api/dictation", files=recording(), data={"language": "de"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_language"


async def test_an_oversized_recording_is_refused_before_it_is_read(make_dictation_client) -> None:
    transcriber = FakeTranscriber()
    async with make_dictation_client(transcriber, dictation_max_bytes=1000) as client:
        r = await client.post("/api/dictation", files=recording(data=b"x" * 200_000))
    assert r.status_code == 413 and transcriber.calls == []


async def test_the_allowance_is_per_user(make_dictation_client) -> None:
    async with make_dictation_client(FakeTranscriber(), dictation_per_hour=2) as client:
        assert (await client.post("/api/dictation", files=recording())).status_code == 200
        assert (await client.post("/api/dictation", files=recording())).status_code == 200
        r = await client.post("/api/dictation", files=recording())
    assert r.status_code == 429 and r.json()["code"] == "dictation_rate_limited"


async def test_it_is_off_when_dictation_is_disabled(make_dictation_client) -> None:
    transcriber = FakeTranscriber()
    async with make_dictation_client(transcriber, dictation_enabled=False) as client:
        r = await client.post("/api/dictation", files=recording())
    assert r.status_code == 503 and r.json()["code"] == "dictation_disabled" and transcriber.calls == []


async def test_a_provider_failure_is_a_502(make_dictation_client) -> None:
    async with make_dictation_client(ExplodingTranscriber(ProviderUnavailable())) as client:
        r = await client.post("/api/dictation", files=recording())
    assert r.status_code == 502


async def test_a_visitor_who_is_not_signed_in_is_refused(make_dictation_client) -> None:
    async with make_dictation_client(FakeTranscriber(), anonymous=True) as client:
        r = await client.post("/api/dictation", files=recording())
    assert r.status_code == 401
