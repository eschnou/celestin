"""Révision DTOs (spec 020).

A révision is read back as a discussion is, with the same `StoredEntry` (its `record_result`
calls carry `chapter_id`, `section_id`, `outcome` and their marker, from the tool's `shown`
hook). The page also reads every chapter of the course with the state of each section, and
the latest self-assessment per section. A section's beats, exercise pools and `done_when`
never cross this wire: only its id, number, kind and title.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.chat import Id, Message
from app.api.schemas.discussion import StoredEntry
from app.domain.curriculum import Kind
from app.domain.progress import Studied
from app.domain.revision import Outcome


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RevisionDTO(_Model):
    id: Id
    chapter_ids: list[Id]  # in course order
    entries: list[StoredEntry]
    entry_count: int
    created_at: datetime


class RevisionSectionDTO(_Model):
    id: str
    index: int
    kind: Kind
    title: str
    state: Studied  # `todo`: neither done nor skipped (an active section is todo)


class RevisionChapterDTO(_Model):
    id: Id
    position: int
    title: str | None
    # Ready for a révision: the chapter has content that reads. `sections` is [] otherwise.
    ready: bool
    section_count: int
    done_count: int
    skipped_count: int
    sections: list[RevisionSectionDTO]


class RevisionResultDTO(_Model):
    chapter_id: Id
    section_id: str
    outcome: Outcome
    at: datetime


class RevisionView(_Model):
    """`GET /api/courses/{c}/revision`, and the answer of `POST` (with the révision it started): the live révision
    or null, every chapter of the course in course order, and the latest self-assessment per section (current
    content versions only)."""

    revision: RevisionDTO | None
    chapters: list[RevisionChapterDTO]
    results: list[RevisionResultDTO]


class StartRevisionRequest(_Model):
    # Empty is the service's `422 revision_no_chapter`, not a schema error. A course holds at most 40 chapters.
    chapter_ids: Annotated[list[Id], Field(max_length=100)]


class RevisionTurnRequest(_Model):
    course_id: Id
    revision_id: Id
    # None opens the révision: Célestin speaks first, and only while it is empty.
    message: Message | None = None
