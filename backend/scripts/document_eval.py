"""Documents through the real pipeline. Opt-in; the full run costs money.

    uv run python -m scripts.document_eval --render-only --pdf path/to/course.pdf
    uv run python -m scripts.document_eval --pdf path/to/course.pdf [--verify on|off]
    uv run python -m scripts.document_eval --images photos/ [--subject sciences] [--language en]

`--render-only` stops after rendering (free). Otherwise the document is transcribed
and authored by the real agent; outputs go to `backend/.eval/document/`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import re
import uuid

from app.domain.language import COURSE_LANGUAGES, DEFAULT_COURSE_LANGUAGE
from app.config import get_settings
from app.domain.chapter import RunUsage
from app.domain.transcription import split_pages
from app.services.authoring.agent import AuthoringAgent, AuthoringFailed
from app.services.documents import DocumentService
from app.services.prompts import PromptLibrary
from scripts import ai_clients

BACKEND = Path(__file__).resolve().parent.parent
OUT = BACKEND / ".eval" / "document"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def read_files(args: argparse.Namespace) -> list[bytes]:
    if args.pdf:
        return [args.pdf.read_bytes()]
    paths = sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    return [p.read_bytes() for p in paths]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--images", type=Path)
    p.add_argument("--render-only", action="store_true")
    p.add_argument("--subject", default="mathematics")
    p.add_argument("--language", choices=list(COURSE_LANGUAGES), default=DEFAULT_COURSE_LANGUAGE)
    p.add_argument("--verify", choices=["on", "off"])
    return p


async def render(args: argparse.Namespace):
    service = DocumentService(get_settings())
    started = time.monotonic()
    try:
        document = await service.prepare(read_files(args))
    finally:
        service.shutdown()
    print(json.dumps({
        "kind": document.kind,
        "pages": len(document.pages),
        "bytes_in": document.bytes_in,
        "jpeg_bytes": sum(len(p.jpeg) for p in document.pages),
        "pages_with_text_hint": sum(1 for p in document.pages if p.text_hint),
        "render_s": round(time.monotonic() - started, 1),
    }, indent=2))
    return document


def acceptance(transcription: str, attempts: dict | None) -> dict[str, bool]:
    """Requirements NFR 4.4.4, for courses/chapitre_1.pdf."""
    pages = split_pages(transcription)
    page5 = pages.get(5, "")
    flat = re.sub(r"\s", "", transcription)
    return {
        "all_pages": sorted(pages) == list(range(1, 17)),
        # The boxed 330 (33 · 10): read right, or marked uncertain; never 350 as sure.
        "p5_boxed_answer_not_misread": "330" in page5
        and not re.search(r"(?<!\| )(?<!\[incertain: )350", page5),
        "pattern_c_1_4_9": "1;4;9;16;25;36" in flat,
        "pack_on_first_or_second_attempt": bool(attempts) and attempts["pack"] <= 2,
    }


async def main() -> None:
    args = parser().parse_args()
    document = await render(args)
    if args.render_only:
        return
    settings = get_settings()
    if args.verify:
        settings = settings.model_copy(update={"transcription_verify_handwriting": args.verify == "on"})
    OUT.mkdir(parents=True, exist_ok=True)
    hub = ai_clients.hub(settings)
    assert hub.config is not None
    print(f"--- {ai_clients.describe(hub.config, 'authoring', 'transcription')} ---")
    agent = AuthoringAgent(hub.authoring_llm, PromptLibrary(settings.prompts_dir), settings, hub)
    usage = RunUsage()
    transcribed: dict[str, object] = {}

    async def on_transcribed(text: str, counts) -> None:  # noqa: ANN001
        transcribed.update(text=text, counts=counts)
        (OUT / "transcription.md").write_text(text, encoding="utf-8")

    started = time.monotonic()
    outcome: dict[str, object] = {"verify_handwriting": settings.transcription_verify_handwriting}
    attempts = None
    try:
        output = await agent.run(
            chapter_id=uuid.uuid4().hex, subject=args.subject, language=args.language, document=document,
            usage=usage,
            on_transcribed=on_transcribed,
        )
    except AuthoringFailed as exc:
        outcome["authoring"] = f"FAILED {exc.code} at {exc.stage}: {exc.detail}"
    else:
        attempts = {"transcription": usage.attempts_transcription, "pack": usage.attempts_pack,
                    "curriculum": usage.attempts_curriculum}
        (OUT / "pack.md").write_text(output.content.pack, encoding="utf-8")
        (OUT / "curriculum.json").write_text(
            json.dumps(output.content.curriculum.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        outcome["authoring"] = {
            "title": output.content.title,
            "sections": len(output.content.curriculum.sections),
            "exercises": len(output.content.index.exercises),
            "points_a_verifier": output.content.index.to_verify,
        }
    counts = transcribed.get("counts")
    outcome.update(
        attempts=attempts,
        markers=counts.__dict__ if counts else None,
        ms={"transcription": usage.transcription_ms, "pack": usage.pack_ms, "curriculum": usage.curriculum_ms,
            "total": round((time.monotonic() - started) * 1000)},
        cost_usd={"transcription": usage.transcription_cost_usd, "total": usage.cost_estimate_usd,
                  "per_page": round(usage.transcription_cost_usd / max(len(document.pages), 1), 4)},
    )
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    if args.pdf and args.pdf.name == "chapitre_1.pdf" and "text" in transcribed:
        checks = acceptance(str(transcribed["text"]), attempts)
        print(json.dumps(checks, indent=2))
        print("ACCEPTANCE OK" if all(checks.values()) else "ACCEPTANCE FAILED")
    print(f"outputs in {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
