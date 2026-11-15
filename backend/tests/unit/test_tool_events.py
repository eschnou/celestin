from __future__ import annotations

import json

from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    SectionDoneEvent,
    SectionSkippedEvent,
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


def test_section_skipped_names_the_next_only_when_nothing_is_active() -> None:
    """Spec 019: skipping another section does not turn the page of the one being worked."""
    ev = event_of(registry.execute("skip_section", '{"section_id":"intro"}', ctx_for(Progress(active="intro"))))
    assert isinstance(ev, SectionSkippedEvent)
    assert (ev.section_id, ev.next_section_id, ev.marker) == ("intro", "exos", "section passée · 1. Introduction")
    ev = event_of(registry.execute("skip_section", '{"section_id":"exos"}', ctx_for(Progress(active="intro"))), "en")
    assert (ev.section_id, ev.next_section_id, ev.marker) == ("exos", None, "section skipped · 2. Exercices")
    last = ctx_for(Progress(done=frozenset({"intro", "exos"})))
    assert event_of(registry.execute("skip_section", '{"section_id":"bilan"}', last)).next_section_id is None
