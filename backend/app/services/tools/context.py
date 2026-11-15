"""What a tool handler may read during a turn (design 3.6), and what a stored call is
read back against (spec 018).

`progress` is replaced, never mutated in place, when a section tool succeeds, so a
second call in the same turn sees the new state; so is `noted`, when `record_result`
succeeds in a révision (spec 020).

A chapter mode (parcours, discussion) has one chapter: its `curriculum`, its `progress`, its
`pack`. A révision has several: `curriculum` is None, `progress` is empty and nothing reads
them, and `revision` holds the chapters it covers, each with its own curriculum and progress
(read only), `pack` every chosen pack. A context checks this when it is built, and code reads
the two through `chapter_path` and `scope`, which never answer None. A révision has no `save`
(the discussion's second lock) and no store at all: `record_result` notes in `noted` only, and
the controller writes a turn's results with its transcript when the turn ends (D6).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.domain import progress as progress_domain
from app.domain.curriculum import Curriculum
from app.domain.mode import DEFAULT_MODE, Mode
from app.domain.errors import ToolValidationError
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.marker import Marker
from app.domain.progress import Progress
from app.domain.revision import Outcome, RevisionChapter, RevisionScope

log = logging.getLogger(__name__)

SAVE_FAILED = by_language(
    fr="Je n'ai pas pu enregistrer ta progression. Réessaie.",
    en="I could not save your progress. Try again.",
    nl="Ik kon je voortgang niet opslaan. Probeer opnieuw.",
)


@dataclass
class TurnContext:
    # The chapter's path: None in a révision, which has several (`revision`). Read it through `chapter_path`.
    curriculum: Curriculum | None = None
    progress: Progress = field(default_factory=Progress)
    # Bound by the controller to the progress store (004 design 3.6). None in
    # unit tests and scripts: the transition is then only adopted in memory.
    save: Callable[[Progress], None] | None = None
    # For the logs (004 §9) and the usage ledger (spec 015: a turn with no user records nothing).
    user_id: str | None = None
    chapter_id: str | None = None
    # Also for the usage ledger (spec 015): the course the chapter belongs to.
    course_id: str | None = None
    # Which tools this turn may call (007 §3.6). A discussion is built with
    # `save=None` as well, so a section tool could not persist even if it ran.
    mode: Mode = DEFAULT_MODE
    # The chapter's pack, which a definition on the board must quote. None in
    # unit tests and scripts that do not exercise that check.
    pack: str | None = None
    # The student's interface language. Display only: the markers of the events this turn
    # emits are rendered in it. Nothing the model reads takes it (spec 010 §4.7).
    locale: Locale = DEFAULT_LOCALE
    # The course's language (spec 011): what the model path reads. Never the interface's.
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
    # Spec 018 D5: section id -> the cards shown in the closed, non-review séances of that section at the current
    # content version, oldest first; what the reprise note at the end of `start_section` lists. Bound by the
    # controller for the parcours, like `save`. None in unit tests and scripts: no note.
    earlier_cards: Callable[[str], list[dict[str, Any]]] | None = None
    # Spec 020: what a révision covers (its chapters, what was noted before it). None in a chapter mode. Read it
    # through `scope`.
    revision: RevisionScope | None = None
    # What this révision noted so far, latest per (chapter id, section id): the tally `record_result` answers.
    noted: Mapping[tuple[str, str], Outcome] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """A chapter mode has its chapter's path and no révision; a révision has its scope and no single path. A
        mis-built context fails here, where it is built, never later inside a tool."""
        if self.mode == "revision":
            if self.revision is None or self.curriculum is not None:
                raise ValueError("a révision turn context has its scope and no chapter path")
        elif self.curriculum is None or self.revision is not None:
            raise ValueError(f"a {self.mode} turn context has its chapter's path and no révision")

    @property
    def chapter_path(self) -> Curriculum:
        """The chapter's path, in a chapter mode (parcours, discussion): what the section tools, the overview and
        the state message read."""
        if self.curriculum is None:
            raise TypeError(f"a {self.mode} turn has no chapter path")  # `__post_init__` makes this unreachable
        return self.curriculum

    @property
    def scope(self) -> RevisionScope:
        """What a révision covers, in a révision: what `record_result` reads."""
        if self.revision is None:
            raise TypeError(f"a {self.mode} turn has no révision")  # `__post_init__` makes this unreachable
        return self.revision

    @classmethod
    def from_progress(
        cls,
        curriculum: Curriculum,
        done: list[str],
        active: str | None,
        save: Callable[[Progress], None] | None = None,
        user_id: str | None = None,
        chapter_id: str | None = None,
        mode: Mode = DEFAULT_MODE,
        pack: str | None = None,
        locale: Locale = DEFAULT_LOCALE,
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
        course_id: str | None = None,
        earlier_cards: Callable[[str], list[dict[str, Any]]] | None = None,
        skipped: list[str] | None = None,
    ) -> TurnContext:
        """From the stored record: inconsistent progress is repaired, never rejected."""
        return cls(
            curriculum=curriculum,
            progress=progress_domain.normalise(done, active, curriculum, skipped or ()),
            save=save,
            user_id=user_id,
            chapter_id=chapter_id,
            course_id=course_id,
            mode=mode,
            pack=pack,
            locale=locale,
            language=language,
            earlier_cards=earlier_cards,
        )

    def commit(self, progress: Progress) -> None:
        """Persist, then adopt. A failing store leaves `self.progress` untouched
        and raises a tool error, so the loop emits no event (004 NFR 4.4.2)."""
        if self.save is not None:
            where = {"user_id": self.user_id, "chapter_id": self.chapter_id}
            try:
                self.save(progress)
            except Exception:  # noqa: BLE001 - reported to the model, logged here
                log.exception("progress_save_failed", extra=where)
                raise ToolValidationError(SAVE_FAILED[self.language]) from None
            log.info(
                "progress_saved",
                extra={
                    **where,
                    "active": progress.active,
                    "done_count": len(progress.done),
                    "skipped_count": len(progress.skipped),
                },
            )
        self.progress = progress

    def note(self, chapter: RevisionChapter, section_id: str, outcome: Outcome) -> None:
        """Adopt a self-assessment in this turn's memory, so the tally counts it at once (spec 020). Nothing is
        written here: the controller writes the turn's results with its transcript, in one transaction, when the
        turn ends, so a stopped or failed turn leaves no result behind (D6)."""
        self.noted = {**self.noted, (chapter.id, section_id): outcome}


@dataclass(frozen=True)
class StoredView:
    """What a stored tool call is read back against when a transcript is restored
    (spec 018): the chapter's current curriculum (a section's label) and the progress
    now (where the page turns). A discussion has neither: it reads board calls only. A
    révision has the curricula of its chapters, by chapter id (a noted section's label)."""

    curriculum: Curriculum | None = None
    progress: Progress | None = None
    chapters: Mapping[str, Curriculum] | None = None


@dataclass(frozen=True)
class Shown:
    """What a stored call of a tool shows (the registry's `shown` hook): the marker the
    live call carried, built by the same function, and the wire fields its entry carries
    beside it (`review`, `next_section_id`). Rendered at the edge, in the reader's
    interface language."""

    marker: Marker | None = None
    fields: Mapping[str, Any] = field(default_factory=dict)
