"""What the two kinds of stored transcript share (007 design 3.8, spec 018).

A discussion and a parcours séance are both `conversations` rows: the same entry
shapes, built from a turn's events the same way, read back the same way, and closed
the same way when the chapter's content has changed under them. The services that
own each kind (`discussion.py`, `seance.py`) differ in what a turn reads and how it
is stored, not in this.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import TypeAdapter

from app.api.schemas.chat import Entry, LearnerEntry, ToolEntry, TutorEntry, stored_form
from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    SectionDoneEvent,
    SectionStartEvent,
    StepReadyEvent,
    TextDeltaEvent,
    TurnEvent,
)
from app.config import Settings
from app.db.repositories import ConversationRecord, Repositories
from app.domain.chapter import LessonChapter
from app.domain.errors import TutorError
from app.domain.mode import Mode

log = logging.getLogger(__name__)

_ENTRY = TypeAdapter(Entry)


def entries_from_events(events: list[TurnEvent]) -> list[Entry]:
    """The turn's events as transcript entries, mirroring what the browser records:
    one tutor entry per text block, one tool entry per successful call.

    A refused call emits no event and is not recorded, exactly as in the browser.
    The parcours tools (`start_section` with its `review`, `complete_section`,
    `propose_next_step`) are recorded as the lesson records them; a discussion
    cannot produce their events, since it is never offered the tools.
    """
    # A block's deltas are gathered as parts and joined once: a long reply arrives
    # in hundreds of them, and rebuilding the string per delta is quadratic.
    slots: list[Entry | list[str]] = []
    blocks: dict[int, int] = {}
    for event in events:
        if isinstance(event, TextDeltaEvent):
            index = blocks.get(event.block_id)
            if index is None:
                blocks[event.block_id] = len(slots)
                slots.append([event.text])
            else:
                parts = slots[index]
                assert isinstance(parts, list)
                parts.append(event.text)
        elif isinstance(event, BoardSetEvent):
            slots.append(
                ToolEntry(
                    kind="tool",
                    name="display_board",
                    arguments={"card": event.card.model_dump(mode="json")},
                )
            )
        elif isinstance(event, BoardClearEvent):
            slots.append(ToolEntry(kind="tool", name="clear_board", arguments={}))
        elif isinstance(event, SectionStartEvent):
            slots.append(
                ToolEntry(
                    kind="tool",
                    name="start_section",
                    arguments={"section_id": event.section_id},
                    review=event.review,
                )
            )
        elif isinstance(event, SectionDoneEvent):
            # The summary stays server-side (logged), as in the browser: a replay needs only the id.
            slots.append(
                ToolEntry(kind="tool", name="complete_section", arguments={"section_id": event.section_id})
            )
        elif isinstance(event, StepReadyEvent):
            slots.append(ToolEntry(kind="tool", name="propose_next_step", arguments={}))

    entries: list[Entry] = []
    for slot in slots:
        if isinstance(slot, list):
            text = "".join(slot)
            if text:
                entries.append(TutorEntry(kind="tutor", text=text))
        else:
            entries.append(slot)
    return entries


def stored_entries(conversation: ConversationRecord) -> list[Entry]:
    """What was said, as transcript entries: a stored row is parsed here, and only here."""
    return [_ENTRY.validate_python(raw) for raw in conversation.entries]


def is_ok_call(entry: Entry, name: str) -> bool:
    """A call of `name` that succeeded (a refused one was never shown)."""
    return isinstance(entry, ToolEntry) and entry.ok and entry.name == name


def card_of(entry: Entry) -> dict[str, Any] | None:
    """The card an entry put on the board, or None: what `card_count`, the reprise note
    and the cahier count and show."""
    if isinstance(entry, ToolEntry) and is_ok_call(entry, "display_board"):
        card = entry.arguments.get("card")
        if isinstance(card, dict):
            return card
    return None


def card_count(entries: list[Entry]) -> int:
    return sum(1 for entry in entries if card_of(entry) is not None)


def is_full(conversation: ConversationRecord, settings: Settings) -> bool:
    """Whether a row has reached either cap (`discussion_max_entries`, `discussion_max_chars`):
    a discussion is then refused, a séance rolls over (spec 018 D10)."""
    return (
        conversation.entry_count >= settings.discussion_max_entries
        or conversation.char_count >= settings.discussion_max_chars
    )


def opening(stored: list[Entry], message: str | None, started: type[TutorError]) -> list[Entry]:
    """What a turn adds before what it produces. `message is None` opens the row, valid
    only while it is empty (Célestin speaks first); otherwise `started` is raised, each
    mode with its own words. A message is a learner entry."""
    if message is None:
        if stored:
            raise started()
        return []
    return [LearnerEntry(kind="learner", text=message)]


def payload(entries: list[Entry]) -> list[dict[str, Any]]:
    """Entries as a row stores them."""
    return [stored_form(entry) for entry in entries]


def live_row(
    repos: Repositories, user_id: str, chapter: LessonChapter, mode: Mode, log_name: str
) -> ConversationRecord | None:
    """The live row of `mode`, or None. One held against an older version of the
    chapter is closed here rather than continued: its pack is gone (007 R8.3, spec 018
    D9). Lazy, so a content edit need not know about conversations."""
    conversation = repos.conversations.live(user_id, chapter.id, mode=mode)
    if conversation is None:
        return None
    if conversation.content_version != chapter.version:
        repos.conversations.close(conversation.id, "content_changed")
        log.info(
            log_name,
            extra={
                "conversation_id": conversation.id,
                "chapter_id": chapter.id,
                "reason": "content_changed",
            },
        )
        return None
    return conversation
