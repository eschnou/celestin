"""Transcript DTOs (design 4.1).

The browser owns conversation state and posts the whole transcript back each turn.
Markers and error entries are client-side presentation and are not sent back.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.domain.progress import Progress

_settings = get_settings()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearnerEntry(_Model):
    kind: Literal["learner"]
    text: Annotated[str, Field(min_length=1, max_length=_settings.max_message_chars)]


class TutorEntry(_Model):
    kind: Literal["tutor"]
    text: str


class ToolEntry(_Model):
    kind: Literal["tool"]
    name: Annotated[str, Field(min_length=1, max_length=64)]
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None


Entry = Annotated[Union[LearnerEntry, TutorEntry, ToolEntry], Field(discriminator="kind")]


class ProgressDTO(_Model):
    """Where the learner is (002 design 4.2). Since 004 a response type only: the
    server owns the record."""

    done: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=40)] = []
    active: Annotated[str, Field(max_length=40)] | None = None

    @classmethod
    def from_progress(cls, progress: Progress) -> ProgressDTO:
        return cls(done=sorted(progress.done), active=progress.active)


# Course and chapter ids are uuid4 hex (005 design 4.3).
Id = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]


class ChatRequest(_Model):
    course_id: Id
    chapter_id: Id
    history: Annotated[list[Entry], Field(max_length=_settings.max_history_entries)] = []
