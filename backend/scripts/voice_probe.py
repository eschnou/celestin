"""Spoken-maths probes for the voice block of the prompt (003 NFR 4.5.2).

The voice block is prompt text, so it has no unit test. This sends three learner
messages through the text pipeline with the *voice* rendering of the prompt as
the developer message, and checks the answers read like speech: maths in words,
no `$…$` in the prose, formulas pushed to the board.

    uv run python -m scripts.voice_probe [--language en|nl]

`--language en` runs the English probes on the English chapter, and also fails on a way of
writing maths that cannot be said out loud: an exponent (`x^2`), a subscript (`u_n`), a
backslash command (`\\frac`) or a decimal comma (`2,5`: « two point five »).
"""

from __future__ import annotations

import asyncio
import re
import sys

from app.api.schemas.events import BoardSetEvent, TextDeltaEvent
from app.config import get_settings
from app.domain.language import by_language
from app.services.tutor_service import TutorService
from app.services.voice_service import VoiceService
from scripts import ai_clients
from scripts.smoke import context_for, load_lesson

PROBES = by_language(
    fr=[
        "Redis-moi la définition d'une suite arithmétique.",
        "C'est quoi la formule du terme général d'une suite géométrique ?",
        "Dans quel intervalle doit être q pour que la suite tende vers zéro ?",
    ],
    en=[
        "Tell me the definition of an arithmetic sequence again.",
        "What is the formula for the general term of a geometric sequence?",
        "In which interval does q have to be for the sequence to tend to zero?",
    ],
    nl=[
        "Geef me de definitie van een rekenkundige rij nog eens.",
        "Wat is de formule voor de algemene term van een meetkundige rij?",
        "In welk interval moet q liggen opdat de rij naar nul gaat?",
    ],
)
_NO_LATEX = re.compile(r"\$[^$]+\$|\\[A-Za-z]+|[A-Za-z0-9)][\^_][A-Za-z0-9({]")
# What a voice cannot say: LaTeX, and written-out maths. English also refuses a decimal comma.
UNSPEAKABLE = by_language(
    fr=_NO_LATEX,
    en=re.compile(_NO_LATEX.pattern + r"|\d,(?!\d{3}(?!\d))\d"),
    # Dutch writes a decimal comma, like French: only the LaTeX and the written-out maths are unspeakable.
    nl=_NO_LATEX,
)


def unspeakable(text: str, language: str = "fr") -> bool:
    return bool(UNSPEAKABLE[language].search(text))


async def main() -> int:
    settings = get_settings()
    prompts, chapter = load_lesson(settings, sys.argv)
    curriculum = chapter.curriculum
    hub = ai_clients.hub(settings)
    instructions = VoiceService(hub.realtime, prompts, settings, hub).instructions(chapter)
    tutor = TutorService(llm=hub.llm, prompts=prompts, settings=settings)
    failures = 0
    for message in PROBES[chapter.language]:
        # Every section done: no probe can be refused for being off the path.
        done = [section.id for section in curriculum.sections]
        ctx = context_for(chapter, done, None)
        items = [
            {"role": "developer", "content": [{"type": "input_text", "text": instructions}]},
            {"role": "user", "content": message},
        ]
        spoken: list[str] = []
        boards = 0
        async for event in tutor.run_turn(items, ctx):
            if isinstance(event, TextDeltaEvent):
                spoken.append(event.text)
            elif isinstance(event, BoardSetEvent):
                boards += 1
        text = "".join(spoken)
        has_tex = unspeakable(text, chapter.language)
        ok = not has_tex
        failures += 0 if ok else 1
        print(f"\n→ {message}\n  cartes : {boards}  LaTeX dans la parole : {has_tex}  {'OK' if ok else 'À REVOIR'}\n  {text.strip()}")
    print("\nVOICE PROBE OK" if failures == 0 else f"\n{failures} probe(s) à revoir")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
