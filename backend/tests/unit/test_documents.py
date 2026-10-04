"""Uploaded documents as pages (006 design 3.3)."""

from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from app.config import Settings
from app.domain.errors import DocumentInvalid, TooManyPages
from app.services.documents import DocumentLimits, DocumentService, prepare, sniff
from tests.fixtures.documents import encrypted_pdf, page_image, scanned_pdf, text_pdf

LIMITS = DocumentLimits(max_pages=5, min_pixels=800, dpi=100, max_side_px=1200)


def refused(files: list[bytes], reason: str) -> str:
    result = prepare(files, LIMITS)
    assert not hasattr(result, "pages"), result
    assert result.reason == reason, result
    return result.exception().message()


def huge_png() -> bytes:
    """49 megapixels, over the 40 M limit but under Pillow's own 2× refusal."""
    buffer = io.BytesIO()
    Image.new("1", (7000, 7000)).save(buffer, format="PNG")
    return buffer.getvalue()


def size_of(jpeg: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(jpeg)).size


def test_sniff_by_content_not_name():
    assert sniff(b"%PDF-1.7\n") == "pdf"
    assert sniff(page_image()[:16]) == "jpeg"
    assert sniff(page_image(fmt="PNG")[:16]) == "png"
    assert sniff(page_image(fmt="WEBP")[:16]) == "webp"
    assert sniff(b"GIF89a....") is None


def test_scanned_pdf_pages_without_text_hint():
    document = prepare([scanned_pdf(3)], LIMITS)
    assert document.kind == "pdf" and [p.number for p in document.pages] == [1, 2, 3]
    assert all(p.text_hint is None for p in document.pages)
    assert max(size_of(document.pages[0].jpeg)) <= 1200


def test_text_layer_pdf_gives_a_hint_only_when_there_is_text():
    document = prepare([text_pdf([["Une suite numérique est une liste ordonnée. " * 8], ["x"]])], LIMITS)
    assert document.pages[0].text_hint and "suite" in document.pages[0].text_hint
    assert document.pages[1].text_hint is None


def test_images_in_order_with_first_page_offset():
    document = prepare([page_image(text="a"), page_image(fmt="PNG"), page_image(fmt="WEBP")], LIMITS, first_page=4)
    assert document.kind == "images" and [p.number for p in document.pages] == [4, 5, 6]
    assert all(p.jpeg.startswith(b"\xff\xd8") for p in document.pages)


def test_exif_rotation_is_applied():
    (page,) = prepare([page_image(1600, 1000, exif_rotate=True)], LIMITS).pages
    width, height = size_of(page.jpeg)
    assert height > width  # a landscape capture tagged « rotate 90° » comes out portrait


def test_downscale_bound():
    (page,) = prepare([page_image(4000, 3000)], LIMITS).pages
    assert max(size_of(page.jpeg)) == 1200


@pytest.mark.parametrize(
    "files, reason, fragment",
    [
        ([], "empty", "vide"),
        ([b""], "empty", "vide"),
        ([b"GIF89a" + b"0" * 100], "type", "PDF ou des photos"),
        ([page_image()[:16] + b"garbage"], "unreadable", "photo 1"),
        ([page_image(), page_image()[:2000]], "unreadable", "photo 2"),  # truncated: fails when decoded
        ([huge_png()], "unreadable", "photo 1"),
        ([scanned_pdf(1), scanned_pdf(1)], "type", "un seul PDF"),
        ([scanned_pdf(1), page_image()], "type", "un seul PDF"),
        ([encrypted_pdf()], "encrypted", "mot de passe"),
        ([b"%PDF-1.4\nnot really a pdf"], "unreadable", "illisible"),
        ([page_image(1600, 600)], "too_small", "800 pixels"),
    ],
)
def test_refusals_name_the_reason(files, reason, fragment):
    assert fragment in refused(files, reason)


def test_page_limit_for_pdf_and_images():
    for files in ([scanned_pdf(6)], [page_image()] * 6):
        result = prepare(files, LIMITS)
        assert result.reason == "too_many_pages"
        assert isinstance(result.exception(), TooManyPages)


async def test_service_raises_refusals_in_the_caller():
    service = DocumentService(Settings(openai_api_key="k", _env_file=None), executor=ThreadPoolExecutor(1))
    with pytest.raises(DocumentInvalid, match="mot de passe"):
        await service.prepare([encrypted_pdf()])
    document = await service.prepare([page_image()])
    assert len(document.pages) == 1


async def test_service_times_out_a_slow_render():
    def slow(*_args):
        time.sleep(0.5)

    settings = Settings(openai_api_key="k", _env_file=None, document_render_timeout_s=0.05)
    service = DocumentService(settings, executor=ThreadPoolExecutor(1), target=slow)
    with pytest.raises(DocumentInvalid) as exc:
        await service.prepare([page_image()])
    assert exc.value.reason == "render_failed"


async def test_service_uses_a_process_pool():
    service = DocumentService(Settings(openai_api_key="k", _env_file=None))
    try:
        document = await service.prepare([scanned_pdf(2)])
        assert len(document.pages) == 2
    finally:
        service.shutdown()


async def test_a_late_failure_from_an_old_pool_leaves_its_replacement_alone():
    service = DocumentService(Settings(openai_api_key="k", _env_file=None))
    old, new = ThreadPoolExecutor(1), ThreadPoolExecutor(1)
    service._executor = new  # the old pool was already dropped and replaced
    service._reset(old)
    assert service._executor is new
    service._reset(new)
    assert service._executor is None
    old.shutdown()
