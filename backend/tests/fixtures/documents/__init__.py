"""Documents for the upload tests, generated so no binary but one is committed.

`encrypted.pdf` is committed: nothing in the dependencies can encrypt a PDF. It was
made once with pypdf (`writer.encrypt("secret")`) from a one-page blank PDF.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent


def page_image(width: int = 1600, height: int = 2200, text: str = "Page", fmt: str = "JPEG", exif_rotate: bool = False) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(image).text((100, 100), text, fill="black")
    buffer = io.BytesIO()
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # orientation: rotate 90° clockwise to display
        image.save(buffer, format=fmt, exif=exif)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


def scanned_pdf(pages: int = 3) -> bytes:
    """Image-only pages, like a scanner's output: no text layer."""
    images = [Image.new("RGB", (1240, 1754), "white") for _ in range(pages)]
    for i, image in enumerate(images, start=1):
        ImageDraw.Draw(image).text((100, 100), f"Page scannée {i}", fill="black")
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:], resolution=150)
    return buffer.getvalue()


def text_pdf(lines_per_page: list[list[str]]) -> bytes:
    """A minimal PDF with a real text layer (Helvetica), one page per list."""
    objects: list[bytes] = []
    page_ids = []
    font_id = 3
    next_id = 4
    content: list[tuple[int, int, bytes]] = []
    for lines in lines_per_page:
        stream = b"BT /F1 12 Tf 72 780 Td 14 TL " + b" ".join(
            b"(" + line.encode("latin-1").replace(b"(", b"\\(").replace(b")", b"\\)") + b") Tj T*" for line in lines
        ) + b" ET"
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        page_ids.append(page_id)
        content.append((page_id, content_id, stream))
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append(b"2 0 obj << /Type /Pages /Kids [" + kids + b"] /Count %d >> endobj" % len(page_ids))
    objects.append(b"3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
    for page_id, content_id, stream in content:
        objects.append(
            b"%d 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >> endobj"
            % (page_id, font_id, content_id)
        )
        objects.append(b"%d 0 obj << /Length %d >> stream\n" % (content_id, len(stream)) + stream + b"\nendstream endobj")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj + b"\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def encrypted_pdf() -> bytes:
    return (HERE / "encrypted.pdf").read_bytes()
