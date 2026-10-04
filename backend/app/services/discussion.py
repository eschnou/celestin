"""Stored discussions (007 design 3.8).

The parcours posts its transcript on every turn; a discussion's lives here, so a
reload finds the thread where it was. Two rules carry the weight:

- **One write per turn.** The route buffers the turn's events and appends
  `[learner, *produced]` once, only when the stream reached its end. A provider
  failure, a disconnect or a cancellation appends nothing, so a half-finished reply
  is never replayed to the model as a finished message (NFR 4.4.1).
- **A conversation belongs to one content version.** Editing a chapter deletes its
  progress and leaves its conversations pointing at a pack that no longer exists;
  `live` closes such a conversation instead of continuing it (R8.3).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from pydantic import TypeAdapter

from app.api.schemas.chat import Entry, LearnerEntry, ToolEntry, TutorEntry
from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    TextDeltaEvent,
    TurnEvent,
)
from app.config import Settings
from app.db.base import utcnow
from app.db.repositories import ConversationRecord, Repositories
from app.domain.chapter import LessonChapter
from app.domain.errors import (
    ConversationClosed,
    ConversationFull,
    DiscussionQuota,
    EmptyTurnExpected,
    NotFound,
)

log = logging.getLogger(__name__)

_ENTRY = TypeAdapter(Entry)


def entries_from_events(events: list[TurnEvent]) -> list[Entry]:
    """The turn's events as transcript entries, mirroring what the browser records:
    one tutor entry per text block, one tool entry per successful call.

    A refused call emits no event and is not recorded, exactly as in the browser.
    The three section events cannot occur in a discussion.
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

    entries: list[Entry] = []
    for slot in slots:
        if isinstance(slot, list):
            text = "".join(slot)
            if text:
                entries.append(TutorEntry(kind="tutor", text=text))
        else:
            entries.append(slot)
    return entries


class DiscussionService:
    def __init__(self, repos: Repositories, settings: Settings) -> None:
        self._repos = repos
        self._settings = settings

    # ------------------------------------------------------------ conversations

    def live(self, user_id: str, chapter: LessonChapter) -> ConversationRecord | None:
        """The live conversation, or None. A conversation held against an older
        version of the chapter is closed here rather than continued: its pack is
        gone (R8.3). Lazy, so a content edit need not know about conversations."""
        conversation = self._repos.conversations.live(user_id, chapter.id)
        if conversation is None:
            return None
        if conversation.content_version != chapter.version:
            self._repos.conversations.close(conversation.id, "content_changed")
            log.info(
                "conversation_closed",
                extra={
                    "conversation_id": conversation.id,
                    "chapter_id": chapter.id,
                    "reason": "content_changed",
                },
            )
            return None
        return conversation

    def start(self, user_id: str, chapter: LessonChapter) -> ConversationRecord:
        """A new empty conversation, closing any live one as `replaced`."""
        maximum = self._settings.discussion_conversations_per_day
        since = utcnow() - timedelta(days=1)
        if self._repos.conversations.started_since(user_id, since) >= maximum:
            log.warning("discussion_quota", extra={"user_id": user_id})
            raise DiscussionQuota(maximum)
        conversation = self._repos.conversations.start(user_id, chapter.id, chapter.version)
        log.info(
            "conversation_started",
            extra={
                "conversation_id": conversation.id,
                "user_id": user_id,
                "chapter_id": chapter.id,
            },
        )
        return conversation

    def open_conversation(
        self, user_id: str, chapter: LessonChapter, conversation_id: str
    ) -> ConversationRecord:
        """The conversation a turn names, ready to be continued. Unknown or another
        student's is a 404, as every other ownership lookup is; closed or full a 409."""
        conversation = self._repos.conversations.get_owned(user_id, chapter.id, conversation_id)
        if conversation is None:
            raise NotFound()
        if not conversation.live:
            raise ConversationClosed(conversation.closed_reason or "replaced")
        if conversation.content_version != chapter.version:
            self._repos.conversations.close(conversation.id, "content_changed")
            raise ConversationClosed("content_changed")
        if conversation.entry_count >= self._settings.discussion_max_entries:
            raise ConversationFull()
        if conversation.char_count >= self._settings.discussion_max_chars:
            raise ConversationFull()
        return conversation

    # -------------------------------------------------------------------- turns

    def stored_entries(self, conversation: ConversationRecord) -> list[Entry]:
        """What was said, as transcript entries. The voice seed reads this instead
        of a posted transcript (007 §3.10)."""
        return [_ENTRY.validate_python(raw) for raw in conversation.entries]

    def turn_entries(
        self, conversation: ConversationRecord, message: str | None
    ) -> tuple[list[Entry], list[Entry]]:
        """`(what the model reads, what the turn adds)`.

        `message is None` opens the conversation and is only valid while it is
        empty: Célestin speaks first, as in the parcours (R2.5).
        """
        stored = self.stored_entries(conversation)
        if message is None:
            if stored:
                raise EmptyTurnExpected()
            return [], []
        learner = LearnerEntry(kind="learner", text=message)
        return [*stored, learner], [learner]

    def append(self, conversation: ConversationRecord, entries: list[Entry]) -> None:
        """One write, after the turn ended (NFR 4.4.1)."""
        if not entries:
            return
        payload = [entry.model_dump(mode="json") for entry in entries]
        try:
            after = self._repos.conversations.append(
                conversation.id,
                payload,
                expected_count=conversation.entry_count,
                max_entries=self._settings.discussion_max_entries,
                max_chars=self._settings.discussion_max_chars,
            )
        except Exception as exc:
            # The turn reached the learner but is lost to the store: the one case
            # where the screen and the record disagree, so it is logged by name.
            log.warning(
                "conversation_append_failed",
                extra={
                    "conversation_id": conversation.id,
                    "added": len(payload),
                    "reason": type(exc).__name__,
                },
            )
            raise
        log.info(
            "conversation_appended",
            extra={
                "conversation_id": conversation.id,
                "added": len(payload),
                "entry_count": after.entry_count,
                "char_count": after.char_count,
                "closed": after.closed_reason,
            },
        )
