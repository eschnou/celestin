"""Progress through a chapter: done, active and skipped sections (design 4.2, spec 019).

What is stored is repaired rather than rejected: unknown ids are dropped, an id both
done and skipped is done, and an `active` that is unknown, done or skipped is cleared.
States are recomputed from the curriculum order afterwards (`services/path.py`).
Starting a skipped section un-skips it: `with_active` does that, so normalisation
never sees a section both active and skipped from the tools.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from app.domain.curriculum import Curriculum

log = logging.getLogger(__name__)

# Where a section stands for a révision (spec 020): done, skipped, or neither (an active section is `todo`).
Studied = Literal["done", "skipped", "todo"]


@dataclass(frozen=True)
class Progress:
    done: frozenset[str] = frozenset()
    active: str | None = None
    # Spec 019 D2: the sections the student chose to pass, kept apart from done.
    skipped: frozenset[str] = frozenset()

    def with_active(self, section_id: str) -> Progress:
        """`section_id` becomes the active section; a skipped one leaves `skipped` (019 D2)."""
        return Progress(done=self.done, active=section_id, skipped=self.skipped - {section_id})

    def with_done(self, section_id: str) -> Progress:
        return Progress(done=self.done | {section_id}, active=None, skipped=self.skipped - {section_id})

    def with_skipped(self, section_id: str) -> Progress:
        """`section_id` is passed (019 D3); it is no longer active if it was."""
        active = None if self.active == section_id else self.active
        return Progress(done=self.done, active=active, skipped=self.skipped | {section_id})

    def state_of(self, section_id: str) -> Studied:
        """Done, skipped or neither (spec 020: what a révision reads, on its page and in its state message). Done
        wins, as normalisation keeps it."""
        if section_id in self.done:
            return "done"
        return "skipped" if section_id in self.skipped else "todo"


def normalise(
    done: list[str], active: str | None, curriculum: Curriculum, skipped: Iterable[str] = ()
) -> Progress:
    known = {s.id for s in curriculum.sections}
    skipped = list(skipped)
    unknown = [d for d in (*done, *skipped) if d not in known]
    if unknown:
        log.warning("progress_unknown_ids", extra={"ids": unknown})
    kept = frozenset(d for d in done if d in known)
    passed = frozenset(s for s in skipped if s in known and s not in kept)
    if active is not None and (active not in known or active in kept or active in passed):
        log.warning(
            "progress_inconsistent",
            extra={"active": active, "done": sorted(kept), "skipped": sorted(passed)},
        )
        active = None
    return Progress(done=kept, active=active, skipped=passed)
