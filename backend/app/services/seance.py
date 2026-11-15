"""Stored séances: the parcours transcript on the server (spec 018).

The parcours used to post its whole transcript on every turn; since spec 018 it is
kept here as a discussion's is (`discussion.py`, sharing `conversations.py`), one
`conversations` row per stretch of work on one section. The rules:

- **One live séance per student and chapter** (D2). A turn reads it and the
  learner's message, nothing of earlier séances (D4): the pack and the trailing
  state message carry the rest.
- **The split happens when a turn is stored** (D3). An ok `start_section` of
  another section closes the live row (`done` if it holds the completion of its own
  section, else `left`) and starts the next one with that entry; what was said
  before it stays with the section it was said in.
- **A full séance rolls over when the next turn opens** (D10): closed `capped`, and
  the next row of the same section starts with a synthetic `start_section`, so the
  brief (and the reprise note) is in front of the model again, when the section is
  still the active one or the row was a review (`_carried_on`); otherwise the next
  row starts unsectioned and empty.
- **A section taken up again gets a reprise note** (D5), built by `earlier_cards`
  from its closed, non-review séances. Closed rows are final, so the note is the
  same on every replay, and the cards it lists are read and parsed once per set of
  rows (a small process-wide cache keyed by their ids), not once per turn.
- **A turn the browser reports** (D7, D10: a spoken one, or one the learner stopped)
  is the one write without a model call: its section ids must be the chapter's and its
  tools the parcours's, and a chapter holding `seance_max_rows` séances refuses it.
- **The notebook** (D8) reads every séance of the current content version.

What the model reads takes the course language only; nothing here knows the
interface's (markers are rendered by the DTOs, at the edge).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.api.schemas.chat import Entry, LearnerEntry, ToolEntry, TutorEntry
from app.config import Settings
from app.db.repositories import ConversationRecord, Repositories, SeanceSegment, StoredSeance
from app.domain.chapter import LessonChapter
from app.domain.errors import ConversationBusy, SeanceBusy, SeanceFull, SeanceReportInvalid, SeanceStarted
from app.domain.mode import ChapterMode
from app.domain.progress import Progress
from app.services import conversations
from app.services.tools import registry
from app.services.tools.context import StoredView

log = logging.getLogger(__name__)

MODE: ChapterMode = "parcours"


def _section_of(entry: Entry) -> str | None:
    if not isinstance(entry, ToolEntry):
        return None
    value = entry.arguments.get("section_id")
    return value if isinstance(value, str) and value else None


def _completes(entries: list[Entry], section_id: str | None) -> bool:
    """Whether `entries` hold an ok `complete_section` of `section_id`."""
    return section_id is not None and any(
        conversations.is_ok_call(e, "complete_section") and _section_of(e) == section_id for e in entries
    )


def _segment(section_id: str | None, entries: list[Entry], closed_reason: str | None) -> SeanceSegment:
    return SeanceSegment(
        section_id, conversations.payload(entries), conversations.card_count(entries), closed_reason
    )


def split(
    section_id: str | None, entries: list[Entry], completed: Callable[[], bool] = lambda: False
) -> list[SeanceSegment]:
    """A turn's entries `[learner?, *produced]` cut into the rows they belong to (D3).

    `section_id` is the live row's section (None: a fresh row, or none yet), and
    `completed` says whether that row already holds the completion of its own section:
    asked only when the turn starts another section. The first segment is the live
    row's (a new one when there is none), every later one a new row; each but the last
    carries the reason its row closes with.
    """
    section = section_id
    segments: list[SeanceSegment] = []
    pending: list[Entry] = []
    first = True
    for entry in entries:
        target = _section_of(entry) if conversations.is_ok_call(entry, "start_section") else None
        if target is not None and section is not None and target != section:
            done = (first and completed()) or _completes(pending, section)
            segments.append(_segment(section, pending, "done" if done else "left"))
            pending, first = [], False
        if target is not None:
            section = target  # adopted by a fresh row, unchanged for its own section, or the new row's
        pending.append(entry)
    segments.append(_segment(section, pending, None))
    return segments


def _opened_as_review(section_id: str | None, entries: list[Entry]) -> bool:
    """A séance opened as a review: its first ok `start_section` of its own section said so."""
    for entry in entries:
        if isinstance(entry, ToolEntry) and conversations.is_ok_call(entry, "start_section"):
            if _section_of(entry) == section_id:
                return bool(entry.review)
    return False


def _carried_on(record: ConversationRecord, progress: Progress) -> list[Entry]:
    """What the row after a full one starts with (D10): a synthetic ok `start_section` of the
    full row's section, so its brief (and reprise note) is in front of the model again, only
    when that call tells the truth: the section is the active one (not a review), or the row
    was a review of a done section (a review again). A section skipped, left or finished in
    the full row is neither: the next row starts unsectioned and empty, as a fresh one."""
    section_id = record.section_id
    if section_id is None:
        return []
    if section_id == progress.active:
        review = False
    elif section_id in progress.done and _opened_as_review(section_id, conversations.stored_entries(record)):
        review = True
    else:
        return []
    return [ToolEntry(kind="tool", name="start_section", arguments={"section_id": section_id}, review=review)]


class _CardCache:
    """Row ids -> the cards those closed séances list, bounded and least recently used
    first out. Closed rows are final (D2), so a set of ids always lists the same cards:
    the transcripts are read and parsed once, not on every turn that replays the brief.
    Process-wide and thread-safe (the turns run in the threadpool); nothing in it is
    tied to an event loop or an app instance, and a miss only costs a read."""

    def __init__(self, max_entries: int = 256) -> None:
        self._max = max_entries
        self._items: OrderedDict[tuple[str, ...], tuple[dict[str, Any], ...]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, ...]) -> tuple[dict[str, Any], ...] | None:
        with self._lock:
            found = self._items.get(key)
            if found is not None:
                self._items.move_to_end(key)
            return found

    def put(self, key: tuple[str, ...], cards: tuple[dict[str, Any], ...]) -> None:
        with self._lock:
            self._items[key] = cards
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)


_EARLIER_CARDS = _CardCache()


def earlier_cards(
    repos: Repositories, user_id: str, chapter_id: str, content_version: int, section_id: str
) -> list[dict[str, Any]]:
    """The cards shown in the closed, non-review séances of a section at this content
    version, oldest first: what the reprise note lists (D5).

    A light query first (the ids of the section's closed rows that hold a card: a row
    without one adds nothing to the note), then the cache; only a new set of rows is
    read and parsed. Review rows are told apart by their content, so they are part of
    the key and filtered when the set is parsed."""
    ids = tuple(repos.conversations.closed_seance_ids(user_id, chapter_id, content_version, section_id))
    if not ids:
        return []
    cached = _EARLIER_CARDS.get(ids)
    if cached is None:
        found: list[dict[str, Any]] = []
        for row in repos.conversations.seances_by_id(user_id, list(ids)):
            entries = conversations.stored_entries(row)
            if not _opened_as_review(row.section_id, entries):
                found.extend(card for entry in entries if (card := conversations.card_of(entry)) is not None)
        cached = tuple(found)
        _EARLIER_CARDS.put(ids, cached)
    return list(cached)


def card_loader(
    repos: Repositories, user_id: str, chapter_id: str, content_version: int
) -> Callable[[str], list[dict[str, Any]]]:
    """`earlier_cards` for one turn, as `TurnContext.earlier_cards`: read once per section.
    Closed séances do not change while a turn runs."""
    cache: dict[str, list[dict[str, Any]]] = {}

    def load(section_id: str) -> list[dict[str, Any]]:
        if section_id not in cache:
            cache[section_id] = earlier_cards(repos, user_id, chapter_id, content_version, section_id)
        return cache[section_id]

    return load


@dataclass(frozen=True)
class NotebookItem:
    """One thing the cahier shows: a card, or what Célestin or the learner said."""

    kind: Literal["card", "tutor", "learner"]
    card: dict[str, Any] | None = None
    text: str | None = None


@dataclass(frozen=True)
class NotebookSection:
    """A section's part of the cahier, in the order things were shown and said."""

    section_id: str
    items: list[NotebookItem]


@dataclass(frozen=True)
class SeanceTurn:
    """A parcours turn about to run, as the store needs it once the stream is over:
    the live row it continues (`live_id` None: the first stored turn will create one),
    by ids and counts only, and what the turn adds before what it produces. `completed`
    says whether the live row holds the completion of its own section (the split asks
    it only when the turn starts another section)."""

    user_id: str
    chapter_id: str
    content_version: int
    live_id: str | None
    expected_count: int
    section_id: str | None
    completed: Callable[[], bool]
    added: list[Entry]


class SeanceService:
    def __init__(self, repos: Repositories, settings: Settings) -> None:
        self._repos = repos
        self._settings = settings

    # ------------------------------------------------------------------ the séance

    def live(self, user_id: str, chapter: LessonChapter) -> ConversationRecord | None:
        """The live séance, or None. A pure read apart from the lazy `content_changed`
        close (D9): a full one is returned as it is and rolls over on the next turn."""
        found = self._repos.conversations.live(user_id, chapter.id, mode=MODE)
        return conversations.live_row(self._repos, found, conversations.older_than(chapter), "seance_closed")

    def current(self, user_id: str, chapter: LessonChapter, progress: Progress) -> ConversationRecord | None:
        """The séance a turn continues: the live one, rolled over first when it is full
        (D10): one `store_seance` write closes it `capped` and starts the next row, of the
        same section with a synthetic ok `start_section` when that tells the truth
        (`_carried_on`), else unsectioned and empty."""
        record = self.live(user_id, chapter)
        if record is None or not conversations.is_full(record, self._settings):
            return record
        entries = _carried_on(record, progress)
        next_section = record.section_id if entries else None
        try:
            rows = self._repos.conversations.store_seance(
                user_id,
                chapter.id,
                chapter.version,
                live_id=record.id,
                expected_count=record.entry_count,
                segments=[
                    _segment(record.section_id, [], "capped"),
                    _segment(next_section, entries, None),
                ],
            )
        except ConversationBusy:
            raise SeanceBusy() from None
        log.info(
            "seance_capped",
            extra={
                "conversation_id": record.id,
                "next_id": rows[-1].id,
                "chapter_id": chapter.id,
                "section_id": record.section_id,
                "entry_count": record.entry_count,
                "char_count": record.char_count,
            },
        )
        return self._repos.conversations.live(user_id, chapter.id, mode=MODE)

    def seed(self, user_id: str, chapter: LessonChapter, progress: Progress) -> list[Entry]:
        """What a voice session of the parcours is seeded with: the séance it continues."""
        record = self.current(user_id, chapter, progress)
        return conversations.stored_entries(record) if record is not None else []

    # -------------------------------------------------------------------- turns

    def open_turn(
        self, user_id: str, chapter: LessonChapter, progress: Progress, message: str | None
    ) -> tuple[SeanceTurn, list[Entry]]:
        """The turn, and what the model reads for it (D4): the live séance, then the
        message. `message is None` opens the lesson and is only valid while the séance
        is empty or there is none: a séance with something in it is restored instead (D6)."""
        record = self.current(user_id, chapter, progress)
        stored = conversations.stored_entries(record) if record is not None else []
        added = conversations.opening(stored, message, SeanceStarted)
        completed = record is not None and _completes(stored, record.section_id)
        return self._turn(user_id, chapter, record, lambda: completed, added), [*stored, *added]

    def _turn(
        self,
        user_id: str,
        chapter: LessonChapter,
        record: ConversationRecord | None,
        completed: Callable[[], bool],
        added: list[Entry],
    ) -> SeanceTurn:
        return SeanceTurn(
            user_id,
            chapter.id,
            chapter.version,
            live_id=record.id if record is not None else None,
            expected_count=record.entry_count if record is not None else 0,
            section_id=record.section_id if record is not None else None,
            completed=completed,
            added=added,
        )

    def store(self, turn: SeanceTurn, entries: list[Entry]) -> list[StoredSeance]:
        """One write, after the turn ended or was reported (D3, D7), cut by the split rule."""
        if not entries:
            return []
        segments = split(turn.section_id, entries, turn.completed)
        try:
            rows = self._repos.conversations.store_seance(
                turn.user_id,
                turn.chapter_id,
                turn.content_version,
                live_id=turn.live_id,
                expected_count=turn.expected_count,
                segments=segments,
            )
        except Exception as exc:
            # The turn reached the learner but is lost to the store: logged by name, never by content.
            log.warning(
                "seance_store_failed",
                extra={
                    "conversation_id": turn.live_id,
                    "chapter_id": turn.chapter_id,
                    "added": len(entries),
                    "reason": type(exc).__name__,
                },
            )
            if isinstance(exc, ConversationBusy):
                raise SeanceBusy() from None
            raise
        live = rows[-1]
        log.info(
            "seance_stored",
            extra={
                "user_id": turn.user_id,
                "chapter_id": turn.chapter_id,
                "conversation_id": live.id,
                "section_id": live.section_id,
                "added": len(entries),
                "rows": len(rows),
                "closed": [row.closed_reason for row in rows[:-1]],
                "entry_count": live.entry_count,
                "card_count": live.card_count,
            },
        )
        return rows

    def store_reported(
        self, user_id: str, chapter: LessonChapter, progress: Progress, entries: list[Entry]
    ) -> list[StoredSeance]:
        """A turn the browser reports (`POST /api/seance/report`): a spoken one, or one
        the learner stopped (D7). Stored like a text turn, on the séance as it stands now.
        Its transcript is parsed only if the turn starts another section, to tell `done`
        from `left`.

        The one write without a model call, so it is checked first (D10): a section id
        that is not the chapter's, or a tool the parcours does not offer, is
        `SeanceReportInvalid` (422); a chapter already holding `seance_max_rows` séances
        for the student is `SeanceFull` (409). A `start_section` reported without its
        `review` gets it here, from the progress (`recorded_review`'s rule), so the stored
        call says what it was and the reprise note never depends on a later progress."""
        entries = self._checked(chapter, progress, entries)
        rows = self._repos.conversations.count_seances(user_id, chapter.id)
        if rows >= self._settings.seance_max_rows:
            log.warning(
                "seance_full", extra={"user_id": user_id, "chapter_id": chapter.id, "rows": rows}
            )
            raise SeanceFull()
        record = self.current(user_id, chapter, progress)

        def completed() -> bool:
            return record is not None and _completes(conversations.stored_entries(record), record.section_id)

        return self.store(self._turn(user_id, chapter, record, completed, []), entries)

    def _checked(self, chapter: LessonChapter, progress: Progress, entries: list[Entry]) -> list[Entry]:
        offered = registry.offered(MODE)
        view = StoredView(chapter.curriculum, progress)
        checked: list[Entry] = []
        for index, entry in enumerate(entries):
            if isinstance(entry, ToolEntry):
                problem = None
                if entry.name not in offered:
                    problem = "tool"
                elif (kept := registry.checked(entry, view)) is None:
                    problem = "section"
                else:
                    entry = kept
                if problem is not None:
                    # Ids and the reason only: what the browser sent, a tool name included, is not logged.
                    log.warning(
                        "seance_report_refused",
                        extra={"chapter_id": chapter.id, "index": index, "reason": problem},
                    )
                    raise SeanceReportInvalid()
            checked.append(entry)
        return checked

    # ----------------------------------------------------------------- the chapter

    def card_counts(self, user_id: str, chapter: LessonChapter) -> dict[str, int]:
        """Section id -> stored cards, for each section with a séance at this version."""
        return self._repos.conversations.card_counts(user_id, chapter.id, chapter.version)

    def notebook(self, user_id: str, chapter: LessonChapter) -> list[NotebookSection]:
        """The cahier (D8): per section in path order, every card shown and every word
        said in its séances of the current content version, live one included, oldest
        first. Sections with nothing stored are left out. No model call."""
        rows = self._repos.conversations.seances(user_id, chapter.id, chapter.version)
        by_section: dict[str, list[NotebookItem]] = {}
        for row in rows:
            if row.section_id is None:
                continue  # a greeting before any section belongs to none
            items = by_section.setdefault(row.section_id, [])
            for entry in conversations.stored_entries(row):
                if isinstance(entry, (TutorEntry, LearnerEntry)):
                    if entry.text.strip():
                        items.append(NotebookItem(kind=entry.kind, text=entry.text))
                elif (card := conversations.card_of(entry)) is not None:
                    items.append(NotebookItem(kind="card", card=card))
        sections = [
            NotebookSection(section_id=section.id, items=by_section[section.id])
            for section in chapter.curriculum.sections
            if by_section.get(section.id)
        ]
        log.info(
            "seance_notebook",
            extra={
                "user_id": user_id,
                "chapter_id": chapter.id,
                "rows": len(rows),
                "sections": len(sections),
                "items": sum(len(s.items) for s in sections),
            },
        )
        return sections
