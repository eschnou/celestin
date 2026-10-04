"""The discussion service (007 design 3.8)."""

from __future__ import annotations

import pytest

from app.api.schemas.chat import LearnerEntry, ToolEntry, TutorEntry
from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    SectionStartEvent,
    TextDeltaEvent,
    TurnEnd,
    TurnStart,
)
from app.config import Settings
from app.db.repositories import Repositories
from app.domain.board import ExplanationCard
from app.domain.chapter import LessonChapter
from app.domain.errors import (
    ConversationClosed,
    ConversationFull,
    DiscussionQuota,
    ConversationBusy,
    EmptyTurnExpected,
    NotFound,
)
from app.services.discussion import DiscussionService, entries_from_events
from tests.fixtures.curricula import curriculum

CARD = ExplanationCard.model_validate(
    {"kind": "explanation", "title": "Les suites", "blocks": [{"type": "text", "text": "Bonjour"}]}
)


def _chapter(repos: Repositories, user_id: str, version: int = 1) -> LessonChapter:
    """A real chapter row (the conversations foreign key points at it) seen as a
    lesson. `version` stands in for a content edit having bumped it."""
    course = repos.courses.create(user_id, "Maths", "mathematics", max_courses=30)
    row = repos.chapters.create(course.id, "texte", max_chapters=40)
    cur = curriculum()
    return LessonChapter(
        id=row.id, subject="mathematics", title=cur.title, pack="# Pack", curriculum=cur,
        version=version,
    )


def _same_chapter(chapter: LessonChapter, version: int) -> LessonChapter:
    return LessonChapter(
        id=chapter.id, subject=chapter.subject, title=chapter.title, pack=chapter.pack,
        curriculum=chapter.curriculum, version=version,
    )


def _service(repos: Repositories, settings: Settings, **overrides) -> DiscussionService:
    return DiscussionService(repos, settings.model_copy(update=overrides) if overrides else settings)


def _student(repos: Repositories, email: str = "a@b.be") -> str:
    return repos.users.create(email, "Léa", "hash").id


# --- entries_from_events ------------------------------------------------------


def test_a_text_only_turn_becomes_one_tutor_entry() -> None:
    entries = entries_from_events(
        [
            TurnStart(turn_id="t"),
            TextDeltaEvent(block_id=0, text="Salut "),
            TextDeltaEvent(block_id=0, text="!"),
            TurnEnd(reason="end", usage={}),
        ]
    )
    assert entries == [TutorEntry(kind="tutor", text="Salut !")]


def test_text_board_text_keeps_its_order_and_blocks() -> None:
    entries = entries_from_events(
        [
            TextDeltaEvent(block_id=0, text="Regarde"),
            BoardSetEvent(card=CARD, marker="explication affichée"),
            TextDeltaEvent(block_id=1, text="Compris ?"),
        ]
    )
    assert [e.kind for e in entries] == ["tutor", "tool", "tutor"]
    assert entries[0].text == "Regarde" and entries[2].text == "Compris ?"
    assert entries[1].name == "display_board"
    assert entries[1].arguments["card"]["title"] == "Les suites"


def test_clear_board_is_recorded_with_no_arguments() -> None:
    entries = entries_from_events([BoardClearEvent(marker="tableau effacé")])
    assert entries == [ToolEntry(kind="tool", name="clear_board", arguments={})]


def test_an_empty_text_block_is_not_recorded() -> None:
    assert entries_from_events([TextDeltaEvent(block_id=0, text="")]) == []


def test_section_events_are_ignored_they_cannot_happen_here() -> None:
    assert entries_from_events([SectionStartEvent(section_id="intro", review=False, marker="m")]) == []


# --- conversations ------------------------------------------------------------


def test_live_returns_none_until_one_is_started(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    other = _chapter(repos, user)
    repos.conversations.start(user, other.id, 1)
    assert _service(repos, settings).live(user, chapter) is None


def test_start_then_live_round_trips(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    started = service.start(user, chapter)
    assert service.live(user, chapter) == started
    assert started.content_version == 1


def test_a_conversation_of_an_older_content_version_is_closed(
    repos: Repositories, settings: Settings
) -> None:
    """Its pack is gone, so it cannot be continued (R8.3)."""
    user = _student(repos)
    service = _service(repos, settings)
    chapter = _chapter(repos, user, version=1)
    service.start(user, chapter)

    assert service.live(user, _same_chapter(chapter, 2)) is None
    # and it stays closed, rather than reappearing on the next read
    assert service.live(user, chapter) is None


def test_open_conversation_refuses_a_closed_one(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings)
    first = service.start(user, chapter)
    service.start(user, chapter)

    with pytest.raises(ConversationClosed) as exc:
        service.open_conversation(user, chapter, first.id)
    assert exc.value.reason == "replaced"
    assert "nouvelle discussion" in exc.value.message()


def test_open_conversation_refuses_an_unknown_id(repos: Repositories, settings: Settings) -> None:
    """A 404 like every other ownership lookup, not a sentinel the route translates."""
    user = _student(repos)
    with pytest.raises(NotFound):
        _service(repos, settings).open_conversation(user, _chapter(repos, user), "0" * 32)


def test_the_turn_that_fills_a_conversation_lands_and_the_next_is_refused(
    repos: Repositories, settings: Settings
) -> None:
    """The cap is applied when a turn is appended, so the answer the student is
    reading is never lost; the *next* turn is the one refused (R4.6)."""
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings, discussion_max_entries=2)
    conv = service.start(user, chapter)
    service.append(
        conv, [LearnerEntry(kind="learner", text="un"), TutorEntry(kind="tutor", text="deux")]
    )

    with pytest.raises(ConversationClosed) as exc:
        service.open_conversation(user, chapter, conv.id)
    assert exc.value.reason == "capped"
    assert "arrivée au bout" in exc.value.message()
    assert service.live(user, chapter) is None


def test_a_lowered_limit_refuses_a_conversation_that_is_still_live(
    repos: Repositories, settings: Settings
) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    conv = _service(repos, settings).start(user, chapter)
    _service(repos, settings).append(conv, [LearnerEntry(kind="learner", text="un")])

    with pytest.raises(ConversationFull):
        _service(repos, settings, discussion_max_entries=1).open_conversation(
            user, chapter, conv.id
        )


def test_the_daily_quota_bounds_new_conversations(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    service = _service(repos, settings, discussion_conversations_per_day=2)
    service.start(user, chapter)
    service.start(user, chapter)
    with pytest.raises(DiscussionQuota) as exc:
        service.start(user, chapter)
    assert "2 discussions" in exc.value.message()


# --- turns --------------------------------------------------------------------


def test_the_opening_turn_reads_nothing_and_adds_nothing(
    repos: Repositories, settings: Settings
) -> None:
    service = _service(repos, settings)
    user = _student(repos)
    conv = service.start(user, _chapter(repos, user))
    read, added = service.turn_entries(conv, None)
    assert read == [] and added == []


def test_a_message_is_read_after_the_stored_entries(
    repos: Repositories, settings: Settings
) -> None:
    user = _student(repos)
    service = _service(repos, settings)
    conv = service.start(user, _chapter(repos, user))
    service.append(
        conv,
        [LearnerEntry(kind="learner", text="salut"), TutorEntry(kind="tutor", text="bonjour")],
    )
    conv = repos.conversations.live(user, conv.chapter_id)
    assert conv is not None

    read, added = service.turn_entries(conv, "et les suites ?")
    assert [e.kind for e in read] == ["learner", "tutor", "learner"]
    assert read[-1].text == "et les suites ?"
    assert added == [LearnerEntry(kind="learner", text="et les suites ?")]


def test_an_opening_turn_on_a_started_conversation_is_refused(
    repos: Repositories, settings: Settings
) -> None:
    user = _student(repos)
    service = _service(repos, settings)
    conv = service.start(user, _chapter(repos, user))
    service.append(conv, [LearnerEntry(kind="learner", text="salut")])
    conv = repos.conversations.live(user, conv.chapter_id)
    assert conv is not None

    with pytest.raises(EmptyTurnExpected):
        service.turn_entries(conv, None)


def test_a_stored_tool_entry_round_trips(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    service = _service(repos, settings)
    conv = service.start(user, _chapter(repos, user))
    produced = entries_from_events([BoardSetEvent(card=CARD, marker="explication affichée")])
    service.append(conv, produced)

    conv = repos.conversations.live(user, conv.chapter_id)
    assert conv is not None
    read, _ = service.turn_entries(conv, "oui")
    assert isinstance(read[0], ToolEntry) and read[0].name == "display_board"


def test_append_of_nothing_writes_nothing(repos: Repositories, settings: Settings) -> None:
    user = _student(repos)
    service = _service(repos, settings)
    conv = service.start(user, _chapter(repos, user))
    service.append(conv, [])
    reloaded = repos.conversations.live(user, conv.chapter_id)
    assert reloaded is not None and reloaded.entry_count == 0


def test_a_lost_append_is_logged_by_name(
    repos: Repositories, settings: Settings, caplog
) -> None:
    """The one case where the screen and the record disagree (007 design 9)."""
    user = _student(repos)
    service = _service(repos, settings)
    conv = service.start(user, _chapter(repos, user))
    service.append(conv, [LearnerEntry(kind="learner", text="un")])

    with caplog.at_level("WARNING"), pytest.raises(ConversationBusy):
        # `conv` still carries the pre-append count, so this is the stale-guard path.
        service.append(conv, [LearnerEntry(kind="learner", text="deux")])

    record = next(r for r in caplog.records if r.message == "conversation_append_failed")
    assert record.reason == "ConversationBusy"  # type: ignore[attr-defined]
    assert record.conversation_id == conv.id  # type: ignore[attr-defined]


# --- the second lock (007 §3.6, task 2.3) -------------------------------------


def test_a_discussion_context_has_no_store_bound(repos: Repositories) -> None:
    """Not declaring the section tools is the first lock; this is the second. Even
    a section tool that somehow ran would adopt in memory and write nothing."""
    from app.api.deps import load_context

    user = repos.users.create("a@b.be", "Léa", "hash")
    chapter = _chapter(repos, user.id)

    parcours = load_context(user, chapter, repos)
    discussion = load_context(user, chapter, repos, "discussion")

    assert parcours.mode == "parcours" and parcours.save is not None
    assert discussion.mode == "discussion" and discussion.save is None
    # Both modes check a definition on the board against the chapter's pack.
    assert parcours.pack == discussion.pack == chapter.pack


def test_committing_in_a_discussion_context_writes_nothing(repos: Repositories) -> None:
    from app.api.deps import load_context
    from app.domain.progress import Progress

    user = repos.users.create("a@b.be", "Léa", "hash")
    chapter = _chapter(repos, user.id)
    ctx = load_context(user, chapter, repos, "discussion")

    ctx.commit(Progress(active="intro"))

    assert ctx.progress.active == "intro"  # adopted in memory
    assert repos.progress.load(user.id, chapter.id) is None  # and nowhere else
