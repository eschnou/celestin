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
    # Spec 019: what a `skip_section` or `complete_section` call answered at the time, so a later turn replays
    # exactly that (`section.py`'s `replay` hooks): the section the page turned to (`next_section_id`, null while
    # a section was still active, both null when the chapter was finished) and, on a skip, the section still
    # being worked (`active_section_id`). Recorded means present: a key left out was not recorded (an entry
    # stored before spec 019 is replayed from the progress now), so `stored_form` keeps an explicit null.
    # Never sent to the model.
    next_section_id: Annotated[str, Field(max_length=40)] | None = None
    active_section_id: Annotated[str, Field(max_length=40)] | None = None

    @model_validator(mode="after")
    def _recorded_on_their_tool_only(self) -> ToolEntry:
        if self.review is not None and self.name != "start_section":
            raise ValueError("review is only recorded on a start_section entry")
        if "next_section_id" in self.model_fields_set and self.name not in ("skip_section", "complete_section"):
            raise ValueError("next_section_id is only recorded on a skip_section or complete_section entry")
        if "active_section_id" in self.model_fields_set and self.name != "skip_section":
            raise ValueError("active_section_id is only recorded on a skip_section entry")
        return self

    def recorded(self, name: str) -> bool:
        """Whether the call recorded `name` (one of the fields above), null included."""
        return name in self.model_fields_set


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


_RECORDED = ("next_section_id", "active_section_id")


def stored_form(entry: Entry) -> dict[str, Any]:
    """An entry as a stored row holds it. `review` is left out when it is not set, and the
    spec-019 fields when they were not recorded, so a discussion's rows (and every other
    tool's entries) keep the bytes they always had."""
    exclude: set[str] | None = None
    if isinstance(entry, ToolEntry):
        exclude = {name for name in _RECORDED if not entry.recorded(name)}
        if entry.review is None:
            exclude.add("review")
    return entry.model_dump(mode="json", exclude=exclude or None)


class ProgressDTO(_Model):
    """Where the learner is (002 design 4.2). Since 004 a response type only: the
    server owns the record."""

    done: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=40)] = []
    active: Annotated[str, Field(max_length=40)] | None = None
    # Spec 019: the sections the student chose to pass, sorted; kept apart from `done`.
    skipped: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=40)] = []

    @classmethod
    def from_progress(cls, progress: Progress) -> ProgressDTO:
        return cls(done=sorted(progress.done), active=progress.active, skipped=sorted(progress.skipped))


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
