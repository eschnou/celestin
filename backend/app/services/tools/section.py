"""Section tools (design 3.6). The locked path is enforced here, not in the prompt.

A handler that succeeds also applies the transition to `ctx.progress`, so a second
call in the same turn sees the new state; the service only emits events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.chat import ToolEntry
from app.domain.curriculum import Curriculum, Section
from app.domain.errors import ToolValidationError
from app.domain.language import by_language
from app.domain.marker import Marker
from app.domain.progress import Progress
from app.services import curriculum_render, path
from app.services.tools.context import Shown, StoredView, TurnContext


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartSectionArgs(_Args):
    section_id: Annotated[str, Field(min_length=1, max_length=40)]


class CompleteSectionArgs(_Args):
    section_id: Annotated[str, Field(min_length=1, max_length=40)]
    summary: Annotated[str, Field(min_length=1, max_length=300)]


@dataclass(frozen=True)
class SectionStarted:
    section: Section
    review: bool
    output: str
    marker: Marker


@dataclass(frozen=True)
class SectionCompleted:
    section: Section
    next: Section | None
    summary: str
    output: str
    marker: Marker


def _start_marker(label: str, review: bool) -> Marker:
    return Marker("marker.section_review" if review else "marker.section_started", label=label)


def _done_marker(label: str) -> Marker:
    return Marker("marker.section_done", label=label)


def start_section(args: StartSectionArgs, ctx: TurnContext) -> SectionStarted:
    refusal = path.can_start(ctx.curriculum, ctx.progress, args.section_id, ctx.language)
    if refusal:
        raise ToolValidationError(refusal)
    section = ctx.curriculum.get(args.section_id)
    assert section is not None
    review = section.id in ctx.progress.done
    if not review:
        ctx.commit(ctx.progress.with_active(section.id))
    return SectionStarted(
        section=section,
        review=review,
        output=_brief(section, review, ctx),
        marker=_start_marker(section.label, review),
    )


def complete_section(args: CompleteSectionArgs, ctx: TurnContext) -> SectionCompleted:
    refusal = path.can_complete(ctx.curriculum, ctx.progress, args.section_id, ctx.language)
    if refusal:
        raise ToolValidationError(refusal)
    section = ctx.curriculum.get(args.section_id)
    assert section is not None
    ctx.commit(ctx.progress.with_done(section.id))
    return SectionCompleted(
        section=section,
        next=path.startable(ctx.curriculum, ctx.progress),
        summary=args.summary,
        output=curriculum_render.completion(ctx.curriculum, ctx.progress, ctx.language),
        marker=_done_marker(section.label),
    )


_UNKNOWN = by_language(
    fr="Section inconnue dans le parcours actuel.",
    en="Unknown section in the current path.",
    nl="Onbekende sectie in het huidige traject.",
)


def _brief(section: Section, review: bool, ctx: TurnContext) -> str:
    """The section's brief, ended by the reprise note when a section left unfinished in
    an earlier séance is taken up again (spec 018 D5). No note for a review, none
    without such a séance: the brief is then what it always was, byte for byte."""
    brief = curriculum_render.brief(ctx.curriculum, section, review, ctx.language)
    if review or ctx.earlier_cards is None:
        return brief
    note = curriculum_render.reprise(ctx.earlier_cards(section.id), ctx.language)
    return brief if note is None else f"{brief}\n\n{note}"


def recorded_review(entry: ToolEntry, progress: Progress | None) -> bool:
    """What a stored `start_section` call was: its recorded `review` (spec 018), else,
    for an entry recorded without it, what the progress says now (no progress: not a
    review). The one rule both the replay and the restored transcript read, so what
    the model is told and what the learner sees cannot disagree."""
    if entry.review is not None:
        return entry.review
    section_id = entry.arguments.get("section_id")
    return progress is not None and isinstance(section_id, str) and section_id in progress.done


def replay_start(entry: ToolEntry, ctx: TurnContext) -> str:
    """The brief again, for a replayed call (design 3.8). A lookup by id, no path
    check: the entry's `ok` and `review` say what the call was at the time, so a section
    completed since is replayed as it was started, reprise note included (decided by
    the same flag), and the replay says it again byte for byte (spec 018 D5): the note
    is built from closed séances only, which never change."""
    section = ctx.curriculum.get(str(entry.arguments.get("section_id", "")))
    if section is None:
        return _UNKNOWN[ctx.language]
    return _brief(section, recorded_review(entry, ctx.progress), ctx)


def replay_complete(entry: ToolEntry, ctx: TurnContext) -> str:
    if ctx.curriculum.get(str(entry.arguments.get("section_id", ""))) is None:
        return _UNKNOWN[ctx.language]
    return curriculum_render.completion(ctx.curriculum, ctx.progress, ctx.language)


def _label(entry: ToolEntry, curriculum: Curriculum | None) -> str:
    """The section's label in the current curriculum; its id when it is no longer there."""
    section_id = str(entry.arguments.get("section_id", ""))
    section = curriculum.get(section_id) if curriculum is not None else None
    return section.label if section is not None else section_id


def shown_start(entry: ToolEntry, view: StoredView) -> Shown:
    """A stored `start_section` call: the marker it carried, and whether it was a review
    (`recorded_review`, as the replay decides it)."""
    review = recorded_review(entry, view.progress)
    return Shown(_start_marker(_label(entry, view.curriculum), review), {"review": review})


def shown_complete(entry: ToolEntry, view: StoredView) -> Shown:
    """A stored `complete_section` call: its marker, and where the page turns **now**,
    from the current progress (the stored call does not keep it)."""
    following = (
        path.startable(view.curriculum, view.progress)
        if view.curriculum is not None and view.progress is not None
        else None
    )
    return Shown(
        _done_marker(_label(entry, view.curriculum)),
        {"next_section_id": following.id if following is not None else None},
    )
