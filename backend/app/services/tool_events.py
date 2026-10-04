"""Tool outcome → turn event (003 design 3.4).

One function, shared by the SSE turn loop and the voice tool endpoint, so the
two channels cannot drift in what a tool call shows the learner.
"""

from __future__ import annotations

from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    SectionDoneEvent,
    SectionStartEvent,
    StepReadyEvent,
    TurnEvent,
)
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.services.tools.board import BoardCleared, BoardSet
from app.services.tools.pace import NextStepProposed
from app.services.tools.registry import ToolOutcome
from app.services.tools.section import SectionCompleted, SectionStarted


def event_of(outcome: ToolOutcome, locale: Locale = DEFAULT_LOCALE) -> TurnEvent:
    """The event for a tool outcome. Its marker is rendered here, in the language of the
    request: the one place a marker becomes text (spec 010 §4.6)."""
    marker = outcome.marker.render(locale)
    if isinstance(outcome, BoardSet):
        return BoardSetEvent(card=outcome.card, marker=marker)
    if isinstance(outcome, BoardCleared):
        return BoardClearEvent(marker=marker)
    if isinstance(outcome, SectionStarted):
        return SectionStartEvent(
            section_id=outcome.section.id, review=outcome.review, marker=marker
        )
    if isinstance(outcome, NextStepProposed):
        return StepReadyEvent(marker=marker)
    if isinstance(outcome, SectionCompleted):
        return SectionDoneEvent(
            section_id=outcome.section.id,
            next_section_id=outcome.next.id if outcome.next else None,
            marker=marker,
        )
    raise TypeError(f"no event for outcome {type(outcome).__name__}")
