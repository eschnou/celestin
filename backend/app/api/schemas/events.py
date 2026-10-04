"""SSE events (design 3.2).

This event set is a two-sided contract with the frontend. Changing it means
changing the frontend types and the design document in the same breath.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Union

from pydantic import BaseModel

from app.domain.board import BoardCard

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class TurnStart(BaseModel):
    event: Literal["turn.start"] = "turn.start"
    turn_id: str


class TextDeltaEvent(BaseModel):
    event: Literal["text.delta"] = "text.delta"
    block_id: int
    text: str


class BoardSetEvent(BaseModel):
    event: Literal["board.set"] = "board.set"
    card: BoardCard
    marker: str


class BoardClearEvent(BaseModel):
    event: Literal["board.clear"] = "board.clear"
    marker: str


class SectionStartEvent(BaseModel):
    event: Literal["section.start"] = "section.start"
    section_id: str
    review: bool
    marker: str


class SectionDoneEvent(BaseModel):
    event: Literal["section.done"] = "section.done"
    section_id: str
    next_section_id: str | None
    marker: str


class StepReadyEvent(BaseModel):
    """The tutor proposed the next step: the board's button turns green."""

    event: Literal["step.ready"] = "step.ready"
    marker: str


class TurnEnd(BaseModel):
    event: Literal["turn.end"] = "turn.end"
    reason: Literal["end", "max_rounds", "cancelled"]
    usage: dict[str, Any] = {}


class ErrorEvent(BaseModel):
    event: Literal["error"] = "error"
    code: str
    message: str


TurnEvent = Union[
    TurnStart,
    TextDeltaEvent,
    BoardSetEvent,
    BoardClearEvent,
    SectionStartEvent,
    SectionDoneEvent,
    StepReadyEvent,
    TurnEnd,
    ErrorEvent,
]


def to_sse(event: TurnEvent) -> str:
    """`event: <name>\\ndata: <json>\\n\\n`, one line of JSON, accents intact."""
    payload = event.model_dump(mode="json", exclude={"event"})
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {data}\n\n"


HEARTBEAT = ": ping\n\n"
