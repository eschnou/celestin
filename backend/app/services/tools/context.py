"""What a tool handler may read during a turn (design 3.6).

`progress` is replaced, never mutated in place, when a section tool succeeds, so a
second call in the same turn sees the new state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.domain import progress as progress_domain
from app.domain.curriculum import Curriculum
from app.domain.mode import DEFAULT_MODE, Mode
from app.domain.errors import ToolValidationError
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.progress import Progress

log = logging.getLogger(__name__)

SAVE_FAILED = by_language(
    fr="Je n'ai pas pu enregistrer ta progression. Réessaie.",
    en="I could not save your progress. Try again.",
)


@dataclass
class TurnContext:
    curriculum: Curriculum
    progress: Progress
    # Bound by the controller to the progress store (004 design 3.6). None in
    # unit tests and scripts: the transition is then only adopted in memory.
    save: Callable[[Progress], None] | None = None
    # For the logs only (004 §9); nothing branches on them.
    user_id: str | None = None
    chapter_id: str | None = None
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
    ) -> TurnContext:
        """From the stored record: inconsistent progress is repaired, never rejected."""
        return cls(
            curriculum=curriculum,
            progress=progress_domain.normalise(done, active, curriculum),
            save=save,
            user_id=user_id,
            chapter_id=chapter_id,
            mode=mode,
            pack=pack,
            locale=locale,
            language=language,
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
                extra={**where, "active": progress.active, "done_count": len(progress.done)},
            )
        self.progress = progress
