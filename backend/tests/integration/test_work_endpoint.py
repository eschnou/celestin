"""The photographed-work route: one photo in, the text it holds out, offline."""

from __future__ import annotations

import pytest

from app.domain.errors import ProviderUnavailable
from tests.conftest import COURSE_ID
from tests.fixtures.documents import page_image
from tests.fixtures.fake_completion import FakeCompletion, text

URL = f"/api/courses/{COURSE_ID}/work"
WORK = "$x + 3 = 7$\n$x = 7 + 3 = 10$\n[incertain: 10 | 40]"


def photo(data: bytes | None = None, name: str = "work.jpg", content_type: str = "image/jpeg"):
    return {"photo": (name, page_image(text="x = 10") if data is None else data, content_type)}


async def test_a_photo_becomes_text_the_student_can_correct(make_work_client, caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeCompletion([text(WORK, {"input_tokens": 1200, "output_tokens": 40})])
    async with make_work_client(fake) as client:
        with caplog.at_level("INFO"):
            r = await client.post(URL, files=photo())
    assert r.status_code == 200 and r.json() == {"text": WORK}
    (call,) = fake.calls
    assert call["role"] == "transcription"  # a vision model, not the tutor: the tutor never sees the picture
    (message,) = call["input"]
    kinds = [part["type"] for part in message["content"]]
    assert kinds == ["input_text", "input_image"]
    assert message["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
    assert "travail" in call["instructions"][0]  # the French prompt, for a French course
    record = next(r for r in caplog.records if r.getMessage() == "work_read")
    assert (record.doubts, record.chars, record.input_tokens) == (1, len(WORK), 1200)  # type: ignore[attr-defined]
    assert "x + 3" not in caplog.text  # what she wrote is never logged


async def test_nothing_written_is_an_empty_text_not_an_error(make_work_client) -> None:
    async with make_work_client(FakeCompletion([text("[rien de lisible]")])) as client:
        r = await client.post(URL, files=photo())
    assert r.status_code == 200 and r.json() == {"text": ""}


async def test_a_webcam_sized_photo_is_not_too_small(make_work_client) -> None:
    fake = FakeCompletion([text("$2 + 2 = 4$")])
    async with make_work_client(fake) as client:
        r = await client.post(URL, files=photo(page_image(width=640, height=480)))
    assert r.status_code == 200 and fake.calls  # the document limit (800 px) is for course pages, not for this


async def test_a_photo_too_small_even_for_this_is_refused(make_work_client) -> None:
    fake = FakeCompletion([])
    async with make_work_client(fake) as client:
        r = await client.post(URL, files=photo(page_image(width=200, height=150)))
    assert r.status_code == 422 and r.json()["code"] == "document_invalid" and fake.calls == []


@pytest.mark.parametrize("data", [b"not an image at all", b"%PDF-1.4 a pdf"], ids=["text", "pdf"])
async def test_what_is_not_a_photo_is_refused_before_the_model(make_work_client, data) -> None:
    fake = FakeCompletion([])
    async with make_work_client(fake) as client:
        r = await client.post(URL, files=photo(data))
    assert r.status_code == 422 and fake.calls == []


async def test_an_empty_upload_is_refused(make_work_client) -> None:
    async with make_work_client(FakeCompletion([])) as client:
        r = await client.post(URL, files=photo(b""))
    assert r.status_code == 422


async def test_another_students_course_is_not_found(make_work_client) -> None:
    fake = FakeCompletion([])
    async with make_work_client(fake) as client:
        r = await client.post("/api/courses/not-mine/work", files=photo())
    assert r.status_code == 404 and fake.calls == []


async def test_an_oversized_photo_is_refused_while_it_streams(make_work_client) -> None:
    fake = FakeCompletion([])
    async with make_work_client(fake, work_max_bytes=1000) as client:
        r = await client.post(URL, files=photo(b"\xff\xd8\xff" + b"x" * 200_000))
    assert r.status_code == 413 and fake.calls == []


async def test_the_allowance_is_per_user(make_work_client) -> None:
    fake = FakeCompletion([text("a"), text("b")])
    async with make_work_client(fake, work_per_hour=2) as client:
        assert (await client.post(URL, files=photo())).status_code == 200
        assert (await client.post(URL, files=photo())).status_code == 200
        r = await client.post(URL, files=photo())
    assert r.status_code == 429 and r.json()["code"] == "work_rate_limited"


async def test_a_provider_failure_is_a_502(make_work_client) -> None:
    async with make_work_client(FakeCompletion([ProviderUnavailable()])) as client:
        r = await client.post(URL, files=photo())
    assert r.status_code == 502


async def test_a_visitor_who_is_not_signed_in_is_refused(make_work_client) -> None:
    async with make_work_client(FakeCompletion([]), anonymous=True) as client:
        r = await client.post(URL, files=photo())
    assert r.status_code == 401
