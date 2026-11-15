"""What the kinds of stored transcript share (007 design 3.8, spec 018, spec 020).

A discussion, a parcours séance and a révision are all `conversations` rows: the same
entry shapes, built from a turn's events the same way, read back the same way, and closed
the same way when the content has changed under them. The services that own each kind
(`discussion.py`, `seance.py`, `revision.py`) differ in what a turn reads and how it is
stored, not in this.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any

from pydantic import TypeAdapter

from app.api.schemas.chat import Entry, LearnerEntry, ToolEntry, TutorEntry, stored_form
from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    RevisionResultEvent,
    SectionDoneEvent,
    SectionSkippedEvent,
    SectionStartEvent,
    StepReadyEvent,
    TextDeltaEvent,
    TurnEvent,
)
from app.config import Settings
from app.db.base import utcnow
from app.db.repositories import ConversationRecord, Repositories
from app.domain.chapter import LessonChapter
from app.domain.errors import TutorError
from app.domain.mode import Mode
from app.domain.revision import NewResult

log = logging.getLogger(__name__)

_ENTRY = TypeAdapter(Entry)


def entries_from_events(events: list[TurnEvent]) -> list[Entry]:
    """The turn's events as transcript entries, mirroring what the browser records:
    one tutor entry per text block, one tool entry per successful call.

    A refused call emits no event and is not recorded, exactly as in the browser.
    The parcours tools (`start_section` with its `review`, `complete_section` with the
    `next_section_id` it answered, `propose_next_step`, `skip_section` with its
    `next_section_id` and `active_section_id`) are recorded as the lesson records them, so a
    later turn replays what the call answered (spec 019); a discussion
    cannot produce their events, since it is never offered the tools. A révision's
    `record_result` is recorded with the chapter's id and the tally it answered (spec 020).
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
            # The summary stays server-side (logged), as in the browser: a replay needs the id and what it answered.
            slots.append(
                ToolEntry(
                    kind="tool",
                    name="complete_section",
                    arguments={"section_id": event.section_id},
                    next_section_id=event.next_section_id,
                )
            )
        elif isinstance(event, SectionSkippedEvent):
            slots.append(
                ToolEntry(
                    kind="tool",
                    name="skip_section",
                    arguments={"section_id": event.section_id},
                    next_section_id=event.next_section_id,
                    active_section_id=event.active_section_id,
                )
            )
        elif isinstance(event, StepReadyEvent):
            slots.append(ToolEntry(kind="tool", name="propose_next_step", arguments={}))
        elif isinstance(event, RevisionResultEvent):
            # Spec 020: the call as the model made it, plus the chapter's id and the tally it answered.
            slots.append(
                ToolEntry(
                    kind="tool",
                    name="record_result",
                    arguments={"chapter": event.chapter, "section_id": event.section_id, "outcome": event.outcome},
                    chapter_id=event.chapter_id,
                    tally=dict(event.tally),
                )
            )

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
    repos: Repositories,
    found: ConversationRecord | None,
    stale: Callable[[ConversationRecord], bool],
    log_name: str,
) -> ConversationRecord | None:
    """`found`, the live row of a mode, or None. One that is `stale` (held against content
    that is gone: an older version of the chapter, or for a révision a chapter changed or
    deleted) is closed here `content_changed` rather than continued (007 R8.3, spec 018 D9,
    spec 020 D6). Lazy, so a content edit need not know about conversations."""
    if found is None:
        return None
    if stale(found):
        repos.conversations.close(found.id, "content_changed")
        where = {"chapter_id": found.chapter_id} if found.course_id is None else {"course_id": found.course_id}
        log.info(log_name, extra={"conversation_id": found.id, **where, "reason": "content_changed"})
        return None
    return found


def older_than(chapter: LessonChapter) -> Callable[[ConversationRecord], bool]:
    """A chapter mode's staleness: the row was started on another content version."""
    return lambda conversation: conversation.content_version != chapter.version


def check_quota(
    repos: Repositories, user_id: str, mode: Mode, per_day: int, refused: Callable[[int], TutorError], **extra: Any
) -> None:
    """At most `per_day` rows of `mode` started by the student in 24 hours: a discussion's
    or a révision's daily quota, each mode with its own error and log line."""
    since = utcnow() - timedelta(days=1)
    if repos.conversations.started_since(user_id, since, mode=mode) >= per_day:
        log.warning(f"{mode}_quota", extra={"user_id": user_id, **extra})
        raise refused(per_day)


def append(
    repos: Repositories,
    settings: Settings,
    conversation: ConversationRecord,
    entries: list[Entry],
    results: Sequence[NewResult] = (),
) -> None:
    """One write, after the turn ended (007 NFR 4.4.1): a discussion's or a révision's turn, `[learner?,
    *produced]`, appended whole under the optimistic guard, with a révision's results (spec 020 D6) in the same
    transaction; crossing a cap closes the row `capped`. Another turn that appended first is `ConversationBusy`.
    Nothing to append writes nothing."""
    if not entries:
        return
    stored = payload(entries)
    try:
        after = repos.conversations.append(
            conversation.id,
            stored,
            expected_count=conversation.entry_count,
            max_entries=settings.discussion_max_entries,
            max_chars=settings.discussion_max_chars,
            cards=card_count(entries),
            results=results,
        )
    except Exception as exc:
        # The turn reached the learner but is lost to the store: the one case
        # where the screen and the record disagree, so it is logged by name.
        log.warning(
            "conversation_append_failed",
            extra={
                "conversation_id": conversation.id,
                "added": len(stored),
                "reason": type(exc).__name__,
            },
        )
        raise
    log.info(
        "conversation_appended",
        extra={
            "conversation_id": conversation.id,
            "added": len(stored),
            "entry_count": after.entry_count,
            "char_count": after.char_count,
            "closed": after.closed_reason,
        },
    )
