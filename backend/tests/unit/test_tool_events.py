from __future__ import annotations

import json

from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    SectionDoneEvent,
    SectionStartEvent,
    StepReadyEvent,
)
from app.domain.progress import Progress
from app.services.tool_events import event_of
from app.services.tools import registry
from tests.fixtures.curricula import ctx_for

CARD = {"kind": "explanation", "title": "T", "blocks": [{"type": "text", "text": "x"}]}


def test_board_set() -> None:
    ev = event_of(registry.execute("display_board", json.dumps({"card": CARD}), ctx_for()))
    assert isinstance(ev, BoardSetEvent) and ev.card.kind == "explanation"


def test_board_clear() -> None:
    assert isinstance(event_of(registry.execute("clear_board", "{}", ctx_for())), BoardClearEvent)


def test_section_start() -> None:
    ev = event_of(registry.execute("start_section", '{"section_id":"intro"}', ctx_for()))
    assert isinstance(ev, SectionStartEvent) and ev.section_id == "intro" and ev.review is False


def test_section_done_names_the_next() -> None:
    ctx = ctx_for(Progress(active="intro"))
    ev = event_of(
        registry.execute("complete_section", '{"section_id":"intro","summary":"ok"}', ctx)
    )
    assert isinstance(ev, SectionDoneEvent) and ev.section_id == "intro"
    assert ev.next_section_id is not None


def test_step_ready() -> None:
    assert isinstance(event_of(registry.execute("propose_next_step", "{}", ctx_for())), StepReadyEvent)
