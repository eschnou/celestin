"""Section tools (design 3.6). The locked path is enforced here, not in the prompt.

A handler that succeeds also applies the transition to `ctx.progress`, so a second
call in the same turn sees the new state; the service only emits events.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.curriculum import Section
from app.domain.errors import ToolValidationError
from app.domain.language import by_language
from app.domain.marker import Marker
from app.services import curriculum_render, path
from app.services.tools.context import TurnContext


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
        output=curriculum_render.brief(ctx.curriculum, section, review, ctx.language),
        marker=Marker("marker.section_review" if review else "marker.section_started", label=section.label),
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
        next=path.next_section(ctx.curriculum, ctx.progress),
        summary=args.summary,
        output=curriculum_render.completion(ctx.curriculum, ctx.progress, ctx.language),
        marker=Marker("marker.section_done", label=section.label),
    )


_UNKNOWN = by_language(
    fr="Section inconnue dans le parcours actuel.",
    en="Unknown section in the current path.",
    nl="Onbekende sectie in het huidige traject.",
)


def replay_start(arguments: dict[str, Any], ctx: TurnContext) -> str:
    """The brief again, for a replayed call (design 3.8). A lookup by id, no path
    check: the entry's `ok` flag says what happened at the time."""
    section = ctx.curriculum.get(str(arguments.get("section_id", "")))
    if section is None:
        return _UNKNOWN[ctx.language]
    return curriculum_render.brief(ctx.curriculum, section, section.id in ctx.progress.done, ctx.language)


def replay_complete(arguments: dict[str, Any], ctx: TurnContext) -> str:
    if ctx.curriculum.get(str(arguments.get("section_id", ""))) is None:
        return _UNKNOWN[ctx.language]
    return curriculum_render.completion(ctx.curriculum, ctx.progress, ctx.language)
