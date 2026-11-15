"""A révision (spec 020): several chapters of one course, rehearsed together.

Pure data. What a révision covers is fixed when it starts (`RevisionChapter`, in course
order); what was noted is the student's own self-assessment of a section, one of three
words (D3: never a verdict from the model). The latest result per section is the one that
counts, and only results recorded against the chapter's current content version are read.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, get_args

from app.domain.curriculum import Curriculum
from app.domain.progress import Progress

Outcome = Literal["solid", "shaky", "todo"]
OUTCOMES: tuple[Outcome, ...] = get_args(Outcome)


@dataclass(frozen=True)
class Noted:
    """The latest result of one section: what the student said, and when."""

    outcome: Outcome
    at: datetime


# (chapter id, section id) -> its latest result
Results = Mapping[tuple[str, str], Noted]


@dataclass(frozen=True)
class RevisionChapter:
    """One chosen chapter, as a révision turn reads it. `number` is its position in the
    course, the number the prompt shows and `record_result` takes."""

    number: int
    id: str
    title: str
    version: int
    pack: str
    curriculum: Curriculum
    progress: Progress = field(default_factory=Progress)


@dataclass(frozen=True)
class RevisionScope:
    """What a révision covers: its chapters in course order, and what was noted before
    this turn (every révision of the course, latest per section, current versions only)."""

    id: str
    course_id: str
    chapters: tuple[RevisionChapter, ...]
    earlier: Results = field(default_factory=dict)

    def chapter(self, number: int) -> RevisionChapter | None:
        return next((c for c in self.chapters if c.number == number), None)

    @property
    def packs(self) -> str:
        """Every chosen pack, for the board's checks (a definition must quote one of them;
        a plotted function must be named by one of them)."""
        return "\n\n".join(c.pack for c in self.chapters)


@dataclass(frozen=True)
class NewResult:
    """A self-assessment to write, from a stored `record_result` call: the section, the word, and the chapter's
    content version the révision holds. Who and which révision come from the row it is written with (D6: a result
    never exists without its stored call)."""

    chapter_id: str
    section_id: str
    outcome: Outcome
    content_version: int


Tally = Mapping[Outcome, int]


def tally(noted: Iterable[Outcome]) -> dict[Outcome, int]:
    """How many sections this révision noted with each word."""
    counts: dict[Outcome, int] = {outcome: 0 for outcome in OUTCOMES}
    for outcome in noted:
        counts[outcome] += 1
    return counts
