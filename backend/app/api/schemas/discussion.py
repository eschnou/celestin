"""Discussion DTOs (007 design 4.3), and the stored entry both modes read back.

A discussion, and since spec 018 a parcours séance, reads its transcript from the
server, so it needs a wire shape for a stored entry — the same three kinds, plus the
marker the transcript shows for a tool call, in the reader's interface language. The
backend owns that wording because it owns the tool semantics: each tool says what a
stored call of it shows (`registry.shown`, asked by `app/api/stored.py`, which hands
the marker and the extra fields here), so this DTO knows no tool by name and imports
nothing from the services.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas.chat import Entry, Id, Message, ToolEntry, reported_problem
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.marker import Marker


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StoredEntry(_Model):
    """A stored entry as the browser reads it back. A tool's own wire fields (a
    `start_section`'s `review`, a `complete_section`'s `next_section_id`) are extra keys,
    on the entries whose tool adds them only: a discussion's entries keep their shape."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["learner", "tutor", "tool"]
    text: str | None = None
    name: str | None = None
    arguments: dict[str, Any] | None = None
    marker: str | None = None

    @classmethod
    def of(
        cls,
        entry: Entry,
        locale: Locale = DEFAULT_LOCALE,
        marker: Marker | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> StoredEntry:
        """A tool entry with what its tool says a stored call shows: its `marker`,
        rendered here in `locale`, and its extra wire `fields`. A text entry takes neither."""
        if isinstance(entry, ToolEntry):
            return cls(
                kind="tool",
                name=entry.name,
                arguments=entry.arguments,
                marker=marker.render(locale) if marker is not None else None,
                **(fields or {}),
            )
        return cls(kind=entry.kind, text=entry.text)


class ConversationDTO(_Model):
    id: Id
    chapter_id: Id
    entries: list[StoredEntry]
    entry_count: int
    created_at: datetime


class ConversationResponse(_Model):
    conversation: ConversationDTO | None


class DiscussionTurnRequest(_Model):
    course_id: Id
    chapter_id: Id
    conversation_id: Id
    # None opens the conversation: Célestin speaks first, and only while it is empty.
    message: Message | None = None


class ReportedTurn(_Model):
    """A turn the browser reports: a spoken one (007 deviation D1), whose speech reaches
    the browser and never the server, or a parcours turn the learner stopped (spec 018
    D7). Shape, count and size are validated here, and every `display_board` entry's card
    must be a valid board card (the cahier draws it); what needs the chapter (a section
    id, a tool the mode offers) is the service's to check, and the caller owns the row."""

    course_id: Id
    chapter_id: Id
    entries: Annotated[list[Entry], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def _entries_fit(self) -> ReportedTurn:
        for index, entry in enumerate(self.entries):
            problem = reported_problem(entry)
            if problem is not None:
                raise ValueError(f"entries[{index}]: {problem}")
        return self


class VoiceTurnRequest(ReportedTurn):
    """A discussion's spoken turn: it names its conversation."""

    conversation_id: Id
