"""Section tools (design 3.6, spec 019). The path's rules are enforced here, not in the prompt:
any section may be started, only the active one completed, any not done one skipped.

A handler that succeeds also applies the transition to `ctx.progress`, so a second
call in the same turn sees the new state; the service only emits events.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.chat import ToolEntry
from app.domain.curriculum import Curriculum, Section
from app.domain.errors import ToolValidationError
from app.domain.language import CourseLanguage, by_language
from app.domain.marker import Marker
from app.domain.progress import Progress
from app.services import curriculum_render, path
from app.services.tools.context import Shown, StoredView, TurnContext


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartSectionArgs(_Args):
    section_id: Annotated[str, Field(min_length=1, max_length=40)]


class SkipSectionArgs(_Args):
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


@dataclass(frozen=True)
class SectionSkipped:
    """`active` is the section still being worked after the skip (passing another section
    does not turn its page), `next` the section the page turns to when none is (`path.page_turn`);
    both None: the chapter is finished."""

    section: Section
    active: Section | None
    next: Section | None
    output: str
    marker: Marker


def _start_marker(label: str, review: bool) -> Marker:
    return Marker("marker.section_review" if review else "marker.section_started", label=label)


def _done_marker(label: str) -> Marker:
    return Marker("marker.section_done", label=label)


def _skip_marker(label: str) -> Marker:
    return Marker("marker.section_skipped", label=label)


def _after(curriculum: Curriculum, progress: Progress) -> tuple[Section | None, Section | None]:
    """What comes next, from a progress: the section being worked, and where the page turns
    (`path.page_turn`, None while one is). What a live completion or skip answers."""
    active = curriculum.get(progress.active) if progress.active is not None else None
    return active, path.page_turn(curriculum, progress)


def start_section(args: StartSectionArgs, ctx: TurnContext) -> SectionStarted:
    refusal = path.can_start(ctx.curriculum, args.section_id, ctx.language)
    if refusal:
        raise ToolValidationError(refusal)
    section = ctx.curriculum.get(args.section_id)
    assert section is not None
    review = section.id in ctx.progress.done
    if not review:
        # Any section, in any order (019 D1); a skipped one leaves `skipped` (D2), and
        # the section that was active is simply no longer (D4).
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
    active, following = _after(ctx.curriculum, ctx.progress)  # nothing is active after a completion
    return SectionCompleted(
        section=section,
        next=following,
        summary=args.summary,
        output=curriculum_render.completion(active, following, ctx.language),
        marker=_done_marker(section.label),
    )


def skip_section(args: SkipSectionArgs, ctx: TurnContext) -> SectionSkipped:
    """Spec 019 D3: only the student decides, the prompt says so; the tool refuses an
    unknown or a done section. Skipping an already skipped section changes nothing."""
    refusal = path.can_skip(ctx.curriculum, ctx.progress, args.section_id, ctx.language)
    if refusal:
        raise ToolValidationError(refusal)
    section = ctx.curriculum.get(args.section_id)
    assert section is not None
    after = ctx.progress.with_skipped(section.id)
    if after != ctx.progress:
        ctx.commit(after)
    active, following = _after(ctx.curriculum, ctx.progress)
    return SectionSkipped(
        section=section,
        active=active,
        next=following,
        output=curriculum_render.skipped(active, following, ctx.language),
        marker=_skip_marker(section.label),
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


def _recorded_after(entry: ToolEntry, curriculum: Curriculum) -> tuple[Section | None, Section | None] | None:
    """What a stored `complete_section` or `skip_section` call answered at the time (spec 019):
    the sections it recorded (`active_section_id`, `next_section_id`), looked up in the
    curriculum. None when it recorded nothing (an entry stored before spec 019), or names a
    section the curriculum no longer has."""
    if not entry.recorded("next_section_id"):
        return None
    found: list[Section | None] = []
    for section_id in (entry.active_section_id, entry.next_section_id):
        section = curriculum.get(section_id) if section_id is not None else None
        if section_id is not None and section is None:
            return None
        found.append(section)
    return found[0], found[1]


_Say = Callable[[Section | None, Section | None, CourseLanguage], str]


def _replay(say: _Say) -> Callable[[ToolEntry, TurnContext], str]:
    """A stored completion or skip answers again exactly what it answered live, from what it
    recorded, whatever the progress has become since (the student may have started the
    section it proposed, or the one it said was still being worked). An entry that recorded
    nothing is answered from the progress now, as before spec 019."""

    def replay(entry: ToolEntry, ctx: TurnContext) -> str:
        if ctx.curriculum.get(str(entry.arguments.get("section_id", ""))) is None:
            return _UNKNOWN[ctx.language]
        recorded = _recorded_after(entry, ctx.curriculum)
        active, following = recorded if recorded is not None else _after(ctx.curriculum, ctx.progress)
        return say(active, following, ctx.language)

    return replay


replay_complete = _replay(curriculum_render.completion)
replay_skip = _replay(curriculum_render.skipped)


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


def _shown(marker: Callable[[str], Marker], with_active: bool) -> Callable[[ToolEntry, StoredView], Shown]:
    """A stored `complete_section` or `skip_section` call when a séance is read back: its
    marker, and where the page turns **now** (`path.page_turn` on the current progress, not
    what the call recorded: the button must propose something valid today), with, for a
    skip, the section being worked now. Every restored entry reads the same progress, so
    they cannot disagree with each other."""

    def shown(entry: ToolEntry, view: StoredView) -> Shown:
        following = (
            path.page_turn(view.curriculum, view.progress)
            if view.curriculum is not None and view.progress is not None
            else None
        )
        fields: dict[str, str | None] = {"next_section_id": following.id if following is not None else None}
        if with_active:
            fields["active_section_id"] = view.progress.active if view.progress is not None else None
        return Shown(marker(_label(entry, view.curriculum)), fields)

    return shown


shown_complete = _shown(_done_marker, with_active=False)
shown_skip = _shown(_skip_marker, with_active=True)


def _names_sections(entry: ToolEntry, curriculum: Curriculum) -> bool:
    """Whether a reported call names sections of the chapter: its `section_id`, and the
    sections it recorded, when it recorded any."""
    section_id = entry.arguments.get("section_id")
    if not isinstance(section_id, str) or curriculum.get(section_id) is None:
        return False
    recorded = (entry.next_section_id, entry.active_section_id)
    return all(sid is None or curriculum.get(sid) is not None for sid in recorded)


def check_section(entry: ToolEntry, view: StoredView) -> ToolEntry | None:
    """A reported `complete_section` or `skip_section` call (spec 018 D10): kept as sent when
    every section it names is the chapter's, else refused (None)."""
    assert view.curriculum is not None
    return entry if _names_sections(entry, view.curriculum) else None


def check_start(entry: ToolEntry, view: StoredView) -> ToolEntry | None:
    """A reported `start_section` call: as `check_section`, and given its `review` from the
    progress when it was reported without one (`recorded_review`'s rule), so the stored
    call says what it was and the reprise note never depends on a later progress."""
    if check_section(entry, view) is None:
        return None
    if entry.review is not None:
        return entry
    return entry.model_copy(update={"review": recorded_review(entry, view.progress)})
