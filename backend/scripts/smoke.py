"""One real conversation. Opt-in, never part of the default test run.

    uv run python -m scripts.smoke [--language en]

Runs two turns through the same service the API uses, so the second proves prompt
caching engaged on the prefix production actually sends (design 7).
"""

from __future__ import annotations

import asyncio
import json

import sys

from app.api.schemas.chat import Entry, LearnerEntry
from app.api.schemas.events import (
    BoardSetEvent,
    ErrorEvent,
    SectionDoneEvent,
    SectionStartEvent,
    TextDeltaEvent,
    TurnEnd,
)
from app.config import get_settings
from app.domain.mode import MODES
from app.providers.hub import build_clients
from app.services.tutor_service import TutorService
from scripts import ai_clients


def language_of(argv: list[str]) -> str:
    """`--language fr|en` (default `fr`): the course language the script runs in."""
    from app.domain.language import COURSE_LANGUAGES

    language = argv[argv.index("--language") + 1] if "--language" in argv else "fr"
    if language not in COURSE_LANGUAGES:
        raise SystemExit(f"--language: {language!r} is not one of {', '.join(COURSE_LANGUAGES)}")
    return language


def load_lesson(settings, argv: list[str]):
    """`--chapter-dir <path>` (default `tests/fixtures/chapters/suites`, or the English fixture for
    `--language en`), `--subject <id>` (default `mathematics`) and `--language fr|en`: the
    chapter as a lesson, validated like the seed."""
    from pathlib import Path

    from app.services.prompts import PromptLibrary
    from scripts.chapter_files import default_chapter_dir, load_chapter_dir

    language = language_of(argv)
    directory = (
        Path(argv[argv.index("--chapter-dir") + 1]) if "--chapter-dir" in argv else default_chapter_dir(language)  # type: ignore[arg-type]
    )
    subject = argv[argv.index("--subject") + 1] if "--subject" in argv else "mathematics"
    prompts = PromptLibrary(settings.prompts_dir)
    return prompts, load_chapter_dir(directory, subject, prompts, language=language)  # type: ignore[arg-type]


def context_for(
    chapter, done: list[str] | None = None, active: str | None = None, mode: str = "parcours"
):
    from app.services.tools.context import TurnContext

    return TurnContext.from_progress(
        chapter.curriculum, done or [], active, mode=mode, pack=chapter.pack, language=chapter.language
    )


SECOND_TURN = {
    "fr": "Explique-moi la somme d'une suite géométrique.",
    "en": "Explain the sum of a geometric sequence to me.",
}


async def one_turn(
    tutor: TutorService, chapter, entries: list[Entry], mode: str = "parcours"
) -> dict:
    usage: dict = {}
    ctx = context_for(chapter, mode=mode)
    async for event in tutor.run_turn(tutor.build_input(chapter, entries, ctx), ctx):
        if isinstance(event, TextDeltaEvent):
            print(event.text, end="", flush=True)
        elif isinstance(event, BoardSetEvent):
            print(f"\n  [tableau] {event.marker} — {event.card.kind}")
        elif isinstance(event, (SectionStartEvent, SectionDoneEvent)):
            print(f"\n  [parcours] {event.marker}")
        elif isinstance(event, ErrorEvent):
            print(f"\n  [erreur] {event.code}")
        elif isinstance(event, TurnEnd):
            usage = event.usage
    print()
    return usage


async def main() -> None:
    settings = get_settings()
    prompts, chapter = load_lesson(settings, sys.argv)
    config = ai_clients.resolve(settings)
    tutor = TutorService(llm=build_clients(settings, config).tutor, prompts=prompts, settings=settings)

    print(f"--- {ai_clients.describe(config, 'tutor')} · chapter {chapter.id} ({chapter.subject}, {chapter.language}) ---")

    # Each mode has its own cached prefix (007 §1.1), so each is checked: a mode
    # whose prefix drifts would otherwise be billed in full on every turn.
    cached_by_mode: dict[str, int] = {}
    for mode in MODES:
        print(f"\n=== mode {mode} ===")
        print("--- turn 1: opening ---")
        print(json.dumps(await one_turn(tutor, chapter, [], mode), indent=2))

        print("\n--- turn 2: same prefix, expect a cache hit ---")
        second = await one_turn(
            tutor,
            chapter,
            [LearnerEntry(kind="learner", text=SECOND_TURN[chapter.language])],
            mode,
        )
        print(json.dumps(second, indent=2))
        cached_by_mode[mode] = (second.get("input_tokens_details") or {}).get("cached_tokens", 0)

    print()
    for mode, cached in cached_by_mode.items():
        print(f"cached_tokens on turn 2 ({mode}): {cached}")
    missed = [mode for mode, cached in cached_by_mode.items() if not cached]
    if missed and not config.tutor.connection.is_openai:
        # The cache breakpoint is OpenAI's; another server may cache by its own rules, or not at all.
        print(f"no cached tokens in {', '.join(missed)} on {config.tutor.connection.host} (not an error: not OpenAI)")
    elif missed:
        raise SystemExit(
            f"CACHE MISS in {', '.join(missed)} — something varies ahead of the breakpoint (design 7)"
        )
    else:
        print("CACHE OK")


if __name__ == "__main__":
    asyncio.run(main())
