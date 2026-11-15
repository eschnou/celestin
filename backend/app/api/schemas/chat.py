"""Transcript DTOs (design 4.1).

Since spec 018 the server owns the transcript of both modes: a turn posts the
learner's message, and these shapes are what a stored row holds and what the model
input is mapped from. Markers and error entries are presentation and are not stored.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from app.config import get_settings
from app.domain.board import BoardCard
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
    # Spec 018: what a `start_section` call was at the time, like `ok`: a review or not. Only that tool carries
    # it, and it is never sent to the model (`history.to_provider_input` reads the name and the arguments).
    review: bool | None = None

    @model_validator(mode="after")
    def _review_on_start_only(self) -> ToolEntry:
        if self.review is not None and self.name != "start_section":
            raise ValueError("review is only recorded on a start_section entry")
        return self


Entry = Annotated[Union[LearnerEntry, TutorEntry, ToolEntry], Field(discriminator="kind")]


# What a reported entry may weigh (spec 018 D10). A model turn's entries are bounded by
# what the model can produce; a reported one only by these, so they are generous for a
# real turn and small against the row's 200 000-character cap:
# - a text block: a tutor reply runs to a few thousand characters, a spoken one is cut at
#   `voice_max_output_tokens` (1024 tokens, about 4 000 characters); 20 000 is five
#   times the longest we have seen and still a tenth of a row;
# - a tool call's arguments, as JSON: a real card is 0.3 to 5 KB (an explanation of a few
#   blocks, a chart of a dozen values, a plot of three curves). The schema would allow a
#   pathological explanation of 12 blocks of 2 000 characters each, about 30 000, so the
#   limit sits above that: 40 000 refuses nothing a model could have shown. (The
#   `display_board` declaration is ~30 000 characters, but it describes every block; a
#   card holds one or two.)
REPORTED_TEXT_MAX = 20_000
REPORTED_ARGUMENTS_MAX = 40_000

_CARD = TypeAdapter(BoardCard)


def reported_problem(entry: Entry) -> str | None:
    """Why a reported entry cannot be stored, or None. Shape only: what needs the chapter
    (its section ids, the tools its mode offers) is checked by the service."""
    if isinstance(entry, (LearnerEntry, TutorEntry)):
        return f"text over {REPORTED_TEXT_MAX} characters" if len(entry.text) > REPORTED_TEXT_MAX else None
    if len(json.dumps(entry.arguments, ensure_ascii=False)) > REPORTED_ARGUMENTS_MAX:
        return f"arguments over {REPORTED_ARGUMENTS_MAX} characters"
    if entry.name == "display_board":
        try:
            _CARD.validate_python(entry.arguments.get("card"))
        except ValidationError:
            return "card is not a valid board card"
    return None


def stored_form(entry: Entry) -> dict[str, Any]:
    """An entry as a stored row holds it. `review` is left out when it is not set, so a
    discussion's rows keep the bytes they always had."""
    exclude = {"review"} if isinstance(entry, ToolEntry) and entry.review is None else None
    return entry.model_dump(mode="json", exclude=exclude)


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


Message = Annotated[str, Field(min_length=1, max_length=_settings.max_message_chars)]


class ChatRequest(_Model):
    """A parcours turn (spec 018 D1): the learner's message, not the transcript. The
    server reads the live séance; `message: null` is the opening turn, accepted only
    while the séance is empty or there is none."""

    course_id: Id
    chapter_id: Id
    message: Message | None = None
