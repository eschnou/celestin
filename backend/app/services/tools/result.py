"""`record_result`, the révision's tool (spec 020).

After a question is settled, the student says how it went — acquis, fragile, à revoir — and
Célestin notes exactly that, for the section of the chapter the question belongs to (D3: the
student's own judgement, never a verdict from the model; that it is hers is prompt text, what
the tool accepts is not). The chapter is named by its number, as the prompt shows it; the
section by its id in that chapter's path. Anything outside the révision is refused, in the
course's language.

The result is noted in the turn's memory (`ctx.note`), and the call answers this révision's tally.
Nothing is written here: the controller writes a turn's results with its transcript when the turn
ends, from the stored calls (D6). A stored call records the chapter's id and that tally on its
entry, so a later turn replays exactly what it answered, whatever was noted since.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.chat import ToolEntry
from app.domain.curriculum import Section
from app.domain.errors import ToolValidationError
from app.domain.language import by_language
from app.domain.marker import Marker
from app.domain.revision import OUTCOMES, Outcome, RevisionChapter, Tally, tally
from app.services import curriculum_render
from app.services.tools.context import Shown, StoredView, TurnContext


class RecordResultArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter: Annotated[int, Field(ge=1, le=999)]
    section_id: Annotated[str, Field(min_length=1, max_length=40)]
    outcome: Outcome


@dataclass(frozen=True)
class ResultRecorded:
    chapter: RevisionChapter
    section: Section
    outcome: Outcome
    tally: Tally
    output: str
    marker: Marker


@dataclass(frozen=True)
class _Words:
    unknown_chapter: str  # {number} {numbers}
    unknown_section: str  # {section_id} {number} {ids}


# Between two numbers or ids of a refusal, in every course language.
_SEPARATOR = ", "


_WORDS = by_language(
    fr=_Words(
        unknown_chapter="Le chapitre {number} ne fait pas partie de cette révision. Chapitres de la révision : {numbers}.",
        unknown_section="La section « {section_id} » n'est pas dans le chapitre {number}. Sections de ce chapitre : {ids}.",
    ),
    en=_Words(
        unknown_chapter="Chapter {number} is not part of this revision. Chapters in the revision: {numbers}.",
        unknown_section="The section “{section_id}” is not in chapter {number}. Sections of this chapter: {ids}.",
    ),
    nl=_Words(
        unknown_chapter="Hoofdstuk {number} hoort niet bij deze herhaling. Hoofdstukken van de herhaling: {numbers}.",
        unknown_section="De sectie “{section_id}” zit niet in hoofdstuk {number}. Secties van dit hoofdstuk: {ids}.",
    ),
)


def result_marker(outcome: Outcome, label: str) -> Marker:
    """« noté : fragile · 2. Suites arithmétiques »: what was noted, and for which section. One key per word, so the
    word is in the reader's interface language."""
    return Marker(f"marker.revision_result.{outcome}", label=label)


def record_result(args: RecordResultArgs, ctx: TurnContext) -> ResultRecorded:
    w = _WORDS[ctx.language]
    scope = ctx.scope
    chapter = scope.chapter(args.chapter)
    if chapter is None:
        numbers = _SEPARATOR.join(str(c.number) for c in scope.chapters)
        raise ToolValidationError(w.unknown_chapter.format(number=args.chapter, numbers=numbers))
    section = chapter.curriculum.get(args.section_id)
    if section is None:
        ids = _SEPARATOR.join(s.id for s in chapter.curriculum.sections)
        raise ToolValidationError(
            w.unknown_section.format(section_id=args.section_id, number=chapter.number, ids=ids)
        )
    ctx.note(chapter, section.id, args.outcome)
    counts = tally(ctx.noted.values())
    return ResultRecorded(
        chapter=chapter,
        section=section,
        outcome=args.outcome,
        tally=counts,
        output=curriculum_render.revision_tally(counts, ctx.language),
        marker=result_marker(args.outcome, section.label),
    )


def replay_record(entry: ToolEntry, ctx: TurnContext) -> str:
    """The tally the call answered, from the counts its entry recorded: never from what was noted since."""
    return curriculum_render.revision_tally(entry.tally or {}, ctx.language)


def _outcome(entry: ToolEntry) -> Outcome | None:
    value = entry.arguments.get("outcome")
    return value if value in OUTCOMES else None


def shown_record(entry: ToolEntry, view: StoredView) -> Shown:
    """A stored `record_result` call when a révision is read back: its marker (the section's label in the chapter's
    current path, its id when it is no longer there), and the chapter, section and outcome it noted."""
    section_id = str(entry.arguments.get("section_id", ""))
    curriculum = (view.chapters or {}).get(entry.chapter_id or "")
    section = curriculum.get(section_id) if curriculum is not None else None
    outcome = _outcome(entry)
    marker = result_marker(outcome, section.label if section is not None else section_id) if outcome else None
    return Shown(marker, {"chapter_id": entry.chapter_id, "section_id": section_id, "outcome": outcome})
