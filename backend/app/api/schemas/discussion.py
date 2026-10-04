"""Discussion DTOs (007 design 4.3).

The parcours posts its transcript and gets nothing back but events. A discussion
reads its transcript from the server, so it needs a wire shape for a stored entry
— the same three kinds, plus the French marker the transcript shows for a tool
call. The backend owns that wording because it owns the tool semantics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.api.schemas.chat import Entry, Id, ToolEntry
from app.domain.board import marker_for
from app.domain.locale import DEFAULT_LOCALE, Locale

_settings = get_settings()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StoredEntry(_Model):
    kind: Literal["learner", "tutor", "tool"]
    text: str | None = None
    name: str | None = None
    arguments: dict[str, Any] | None = None
    marker: str | None = None

    @classmethod
    def of(cls, entry: Entry, locale: Locale = DEFAULT_LOCALE) -> StoredEntry:
        if isinstance(entry, ToolEntry):
            return cls(
                kind="tool",
                name=entry.name,
                arguments=entry.arguments,
                marker=marker_for(entry.name, entry.arguments, locale),
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
    message: Annotated[str, Field(min_length=1, max_length=_settings.max_message_chars)] | None = None


class VoiceTurnRequest(_Model):
    """A spoken turn, reported by the browser (007 deviation D1). The model's
    speech reaches the browser and never the server, so there is nothing else to
    observe; shape, size and count are validated and the caller owns the row."""

    course_id: Id
    chapter_id: Id
    conversation_id: Id
    entries: Annotated[list[Entry], Field(min_length=1, max_length=32)]
