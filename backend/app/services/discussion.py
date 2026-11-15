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

from app.api.schemas.chat import Entry
from app.config import Settings
from app.db.repositories import ConversationRecord, Repositories
from app.domain.chapter import LessonChapter
from app.domain.errors import (
    ConversationClosed,
    ConversationFull,
    DiscussionQuota,
    EmptyTurnExpected,
    NotFound,
)
from app.domain.mode import ChapterMode
from app.services import conversations

log = logging.getLogger(__name__)

MODE: ChapterMode = "discussion"


class DiscussionService:
    def __init__(self, repos: Repositories, settings: Settings) -> None:
        self._repos = repos
        self._settings = settings

    # ------------------------------------------------------------ conversations

    def live(self, user_id: str, chapter: LessonChapter) -> ConversationRecord | None:
        """The live conversation, or None. A conversation held against an older
        version of the chapter is closed here rather than continued: its pack is
        gone (R8.3). Lazy, so a content edit need not know about conversations."""
        found = self._repos.conversations.live(user_id, chapter.id, mode=MODE)
        return conversations.live_row(self._repos, found, conversations.older_than(chapter), "conversation_closed")

    def start(self, user_id: str, chapter: LessonChapter) -> ConversationRecord:
        """A new empty conversation, closing any live one as `replaced`."""
        per_day = self._settings.discussion_conversations_per_day
        conversations.check_quota(self._repos, user_id, MODE, per_day, DiscussionQuota)
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
        conversations.append(self._repos, self._settings, conversation, entries)
