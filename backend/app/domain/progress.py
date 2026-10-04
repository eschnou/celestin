"""Progress through a chapter, as the browser reports it (design 4.2).

The backend holds none of this between requests. What arrives is untrusted and is
repaired rather than rejected: unknown ids are dropped, and an `active` that is
unknown or already done is cleared. States are recomputed from the curriculum
order afterwards, so nothing here can unlock a section.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.domain.curriculum import Curriculum

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Progress:
    done: frozenset[str] = frozenset()
    active: str | None = None

    def with_active(self, section_id: str) -> Progress:
        return Progress(done=self.done, active=section_id)

    def with_done(self, section_id: str) -> Progress:
        return Progress(done=self.done | {section_id}, active=None)


def normalise(done: list[str], active: str | None, curriculum: Curriculum) -> Progress:
    known = {s.id for s in curriculum.sections}
    unknown = [d for d in done if d not in known]
    if unknown:
        log.warning("progress_unknown_ids", extra={"ids": unknown})
    kept = frozenset(d for d in done if d in known)
    if active is not None and (active not in known or active in kept):
        log.warning("progress_inconsistent", extra={"active": active, "done": sorted(kept)})
        active = None
    return Progress(done=kept, active=active)
