from __future__ import annotations

import json

from app.api.schemas.events import (
    BoardClearEvent,
    ErrorEvent,
    SectionDoneEvent,
    SectionStartEvent,
    TextDeltaEvent,
    TurnEnd,
    TurnStart,
    to_sse,
)


def test_frame_format_exact() -> None:
    assert to_sse(TurnStart(turn_id="abc")) == 'event: turn.start\ndata: {"turn_id":"abc"}\n\n'


def test_json_is_single_line() -> None:
    frame = to_sse(TextDeltaEvent(block_id=1, text="a\nb"))
    body = frame.split("data: ", 1)[1].rstrip("\n")
    assert "\n" not in body
    assert json.loads(body) == {"block_id": 1, "text": "a\nb"}


def test_unicode_survives() -> None:
    assert "à toi" in to_sse(TextDeltaEvent(block_id=0, text="à toi"))


def test_every_frame_ends_with_a_blank_line() -> None:
    for event in (
        TurnStart(turn_id="t"),
        TextDeltaEvent(block_id=0, text="x"),
        BoardClearEvent(marker="tableau effacé"),
        TurnEnd(reason="end"),
        ErrorEvent(code="internal", message="oups"),
    ):
        assert to_sse(event).endswith("\n\n")


def test_event_name_is_not_duplicated_in_data() -> None:
    assert "event" not in json.loads(to_sse(TurnEnd(reason="end")).split("data: ")[1])


def test_section_events_frame() -> None:
    assert to_sse(SectionStartEvent(section_id="a", review=False, marker="section commencée · 1. A")) == (
        'event: section.start\ndata: {"section_id":"a","review":false,"marker":"section commencée · 1. A"}\n\n'
    )
    frame = to_sse(SectionDoneEvent(section_id="a", next_section_id=None, marker="m"))
    assert json.loads(frame.split("data: ")[1]) == {"section_id": "a", "next_section_id": None, "marker": "m"}
