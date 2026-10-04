"""Uploaded documents as page images (006 design 3.3).

Bytes in, JPEG page images out, or a French refusal. `prepare` is pure and runs in
a worker process: pdfium and Pillow on untrusted input must neither block the event
loop nor be able to take the server down. Nothing here is written to disk.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import warnings
from concurrent.futures import Executor, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Any, Callable, Literal

from app.config import Settings
from app.domain.errors import DocumentInvalid, TooManyPages

log = logging.getLogger(__name__)

Kind = Literal["pdf", "images"]
FileType = Literal["pdf", "jpeg", "png", "webp"]
DOCUMENT_TYPES = ("application/pdf", "image/jpeg", "image/png", "image/webp")
TEXT_HINT_MIN_CHARS = 200
JPEG_QUALITY = 80
MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class PageImage:
    number: int
    jpeg: bytes
    text_hint: str | None = None

    @cached_property
    def data_url(self) -> str:
        """Encoded once, however many calls send the page (retries, splits, checks)."""
        return "data:image/jpeg;base64," + base64.b64encode(self.jpeg).decode("ascii")


@dataclass(frozen=True)
class Document:
    kind: Kind
    pages: list[PageImage]
    bytes_in: int


@dataclass(frozen=True)
class DocumentLimits:
    max_pages: int
    min_pixels: int
    dpi: int
    max_side_px: int

    @classmethod
    def from_settings(cls, settings: Settings) -> DocumentLimits:
        return cls(
            max_pages=settings.document_max_pages,
            min_pixels=settings.document_min_pixels,
            dpi=settings.transcription_dpi,
            max_side_px=settings.transcription_max_side_px,
        )


@dataclass(frozen=True)
class _Refusal:
    """What a worker returns instead of raising: exceptions with custom arguments
    do not survive pickling between processes."""

    reason: str
    key: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def exception(self) -> DocumentInvalid:
        if self.reason == "too_many_pages":
            return TooManyPages(**self.params)
        return DocumentInvalid(self.reason, key=self.key, **self.params)


def sniff(head: bytes) -> FileType | None:
    """The file type from its first bytes, whatever its name says."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _jpeg(image, max_side: int) -> bytes:  # noqa: ANN001 - a PIL image
    image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def _pdf_pages(data: bytes, limits: DocumentLimits, first_page: int) -> list[PageImage]:
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise DocumentInvalid("encrypted") from exc
        raise DocumentInvalid("unreadable", key="pdf_unreadable") from exc
    try:
        count = len(document)
        if count > limits.max_pages:
            raise TooManyPages(limits.max_pages)
        pages = []
        for index in range(count):
            page = document[index]
            # Rendered at the size that is sent, not larger and then shrunk.
            scale = min(limits.dpi / 72, limits.max_side_px / max(page.get_size()))
            image = page.render(scale=scale).to_pil()
            textpage = page.get_textpage()
            text = textpage.get_text_range().strip()
            textpage.close()
            page.close()
            hint = text if len("".join(text.split())) >= TEXT_HINT_MIN_CHARS else None
            pages.append(PageImage(first_page + index, _jpeg(image, limits.max_side_px), hint))
        return pages
    finally:
        document.close()


def _image_page(data: bytes, limits: DocumentLimits, number: int) -> PageImage:
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            # Pillow only warns between the limit and twice it: refuse before decoding.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
        image.load()  # decode here, so a truncated file is this photo's refusal
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError) as exc:
        raise DocumentInvalid("unreadable", key="photo_unreadable", number=number) from exc
    if min(image.size) < limits.min_pixels:
        raise DocumentInvalid("too_small", number=number, min_pixels=limits.min_pixels)
    return PageImage(number, _jpeg(image, limits.max_side_px))


def prepare(files: list[bytes], limits: DocumentLimits, first_page: int = 1) -> Document | _Refusal:
    """The document's pages, in order, or why it cannot be read. Runs in a worker."""
    try:
        if not files or not any(files):
            raise DocumentInvalid("empty")
        types = [sniff(data[:16]) for data in files]
        if None in types:
            raise DocumentInvalid("type", key="type_unknown")
        if "pdf" in types:
            if len(files) > 1:
                raise DocumentInvalid("type", key="type_mixed")
            pages = _pdf_pages(files[0], limits, first_page)
            kind: Kind = "pdf"
        else:
            if len(files) > limits.max_pages:
                raise TooManyPages(limits.max_pages)
            pages = [_image_page(data, limits, first_page + i) for i, data in enumerate(files)]
            kind = "images"
        if not pages:
            raise DocumentInvalid("empty")
        return Document(kind=kind, pages=pages, bytes_in=sum(map(len, files)))
    except DocumentInvalid as exc:  # TooManyPages is one, reason "too_many_pages"
        return _Refusal(exc.reason, key=exc.key, params=dict(exc.params))


class DocumentService:
    """Owns the worker pool. `prepare` raises `DocumentInvalid` (or `TooManyPages`)
    with a French message, including when rendering takes too long."""

    def __init__(
        self,
        settings: Settings,
        executor: Executor | None = None,
        target: Callable[..., Document | _Refusal] = prepare,
    ) -> None:
        self._limits = DocumentLimits.from_settings(settings)
        self._timeout = settings.document_render_timeout_s
        self._workers = settings.document_workers
        self._executor = executor
        self._target = target

    def _pool(self) -> Executor:
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=self._workers)
        return self._executor

    async def prepare(self, files: list[bytes], first_page: int = 1, min_pixels: int | None = None) -> Document:
        loop = asyncio.get_running_loop()
        pool = self._pool()
        limits = self._limits if min_pixels is None else replace(self._limits, min_pixels=min_pixels)
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(pool, self._target, files, limits, first_page), self._timeout
            )
        except Exception as exc:  # noqa: BLE001 - a worker failure is a refusal
            log.warning("document_render_failed", extra={"error": type(exc).__name__})
            if isinstance(exc, (TimeoutError, BrokenProcessPool)):
                self._reset(pool)  # a hung or dead worker; the others' renders are left alone otherwise
            raise DocumentInvalid("render_failed") from None
        if isinstance(result, _Refusal):
            raise result.exception()
        return result

    def _reset(self, failed: Executor) -> None:
        """A worker that timed out may still be running: drop the pool and its
        processes rather than let it hold a slot. Only the pool that failed: a late
        failure from an old pool must not take down its replacement."""
        if self._executor is not failed:
            return
        executor, self._executor = self._executor, None
        if isinstance(executor, ProcessPoolExecutor):
            for process in list(getattr(executor, "_processes", {}).values()):
                process.terminate()
            executor.shutdown(wait=False, cancel_futures=True)

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
