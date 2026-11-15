"""Stored discussions (007 design 3.8).

A discussion's transcript lives here, so a reload finds the thread where it was (the
parcours keeps its séances the same way since spec 018: `seance.py`; what the two
share is `conversations.py`). Two rules carry the weight:

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

from app.api.schemas.chat import Entry
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
from app.domain.mode import Mode
from app.services import conversations

log = logging.getLogger(__name__)

MODE: Mode = "discussion"


class DiscussionService:
    def __init__(self, repos: Repositories, settings: Settings) -> None:
        self._repos = repos
        self._settings = settings

    # ------------------------------------------------------------ conversations

    def live(self, user_id: str, chapter: LessonChapter) -> ConversationRecord | None:
        """The live conversation, or None. A conversation held against an older
        version of the chapter is closed here rather than continued: its pack is
        gone (R8.3). Lazy, so a content edit need not know about conversations."""
        return conversations.live_row(self._repos, user_id, chapter, MODE, "conversation_closed")

    def start(self, user_id: str, chapter: LessonChapter) -> ConversationRecord:
        """A new empty conversation, closing any live one as `replaced`."""
        maximum = self._settings.discussion_conversations_per_day
        since = utcnow() - timedelta(days=1)
        if self._repos.conversations.started_since(user_id, since, mode=MODE) >= maximum:
            log.warning("discussion_quota", extra={"user_id": user_id})
            raise DiscussionQuota(maximum)
        conversation = self._repos.conversations.start(user_id, chapter.id, chapter.version, mode=MODE)
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
        conversation = self._repos.conversations.get_owned(user_id, chapter.id, conversation_id, mode=MODE)
        if conversation is None:
            raise NotFound()
        if not conversation.live:
            raise ConversationClosed(conversation.closed_reason or "replaced")
        if conversation.content_version != chapter.version:
            self._repos.conversations.close(conversation.id, "content_changed")
            raise ConversationClosed("content_changed")
        if conversations.is_full(conversation, self._settings):
            raise ConversationFull()
        return conversation

    # -------------------------------------------------------------------- turns

    def turn_entries(
        self, conversation: ConversationRecord, message: str | None
    ) -> tuple[list[Entry], list[Entry]]:
        """`(what the model reads, what the turn adds)`.

        `message is None` opens the conversation and is only valid while it is
        empty: Célestin speaks first, as in the parcours (R2.5).
        """
        stored = conversations.stored_entries(conversation)
        added = conversations.opening(stored, message, EmptyTurnExpected)
        return [*stored, *added], added

    def append(self, conversation: ConversationRecord, entries: list[Entry]) -> None:
        """One write, after the turn ended (NFR 4.4.1)."""
        if not entries:
            return
        payload = conversations.payload(entries)
        try:
            after = self._repos.conversations.append(
                conversation.id,
                payload,
                expected_count=conversation.entry_count,
                max_entries=self._settings.discussion_max_entries,
                max_chars=self._settings.discussion_max_chars,
                cards=conversations.card_count(entries),
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
