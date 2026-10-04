"""Stored discussions (007 design 4.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text as sql_text

from app.db.repositories import Repositories
from app.domain.errors import ConversationBusy

NOW = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)

BIG = {"max_entries": 400, "max_chars": 200_000}


def _course_and_chapter(repos: Repositories, user_id: str) -> tuple[str, str]:
    course = repos.courses.create(user_id, "Maths", "mathematics", max_courses=30)
    return course.id, repos.chapters.create(course.id, "texte", max_chapters=40).id


def _chapter(repos: Repositories, user_id: str) -> str:
    return _course_and_chapter(repos, user_id)[1]


def _student(repos: Repositories, email: str = "a@b.be") -> str:
    return repos.users.create(email, "Léa", "hash").id


def _say(text: str) -> dict:
    return {"kind": "learner", "text": text}


def test_start_creates_a_live_empty_conversation(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    assert repos.conversations.live(user, chapter) is None

    conv = repos.conversations.start(user, chapter, content_version=3)
    assert conv.live and conv.entries == [] and conv.entry_count == 0
    assert conv.content_version == 3 and conv.closed_reason is None
    assert repos.conversations.live(user, chapter) == conv


def test_starting_again_closes_the_previous_one_as_replaced(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    first = repos.conversations.start(user, chapter, 1)
    second = repos.conversations.start(user, chapter, 1)

    assert second.id != first.id
    assert repos.conversations.live(user, chapter) == second
    stale = repos.conversations.get_owned(user, chapter, first.id)
    assert stale and not stale.live and stale.closed_reason == "replaced"


def test_only_one_live_row_per_student_and_chapter(repos: Repositories, db_engine) -> None:
    """The partial unique index, not a read-then-write race (007 §4.1)."""
    user = _student(repos)
    chapter = _chapter(repos, user)
    repos.conversations.start(user, chapter, 1)
    with pytest.raises(Exception):  # IntegrityError under any driver
        with db_engine.begin() as conn:
            conn.execute(
                sql_text(
                    "insert into conversations (id, user_id, chapter_id, mode, content_version,"
                    " entries, entry_count, char_count, state, created_at, updated_at)"
                    " values ('x', :u, :c, 'discussion', 1, '[]', 0, 0, 'live', :n, :n)"
                ),
                {"u": user, "c": chapter, "n": NOW.isoformat(sep=" ")},
            )


def test_a_closed_conversation_does_not_block_a_new_live_one(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    for _ in range(3):
        repos.conversations.start(user, chapter, 1)
    assert repos.conversations.live(user, chapter) is not None


def test_conversations_are_per_student_and_per_chapter(repos: Repositories) -> None:
    a, b = _student(repos, "a@b.be"), _student(repos, "b@b.be")
    chapter_a, chapter_b = _chapter(repos, a), _chapter(repos, b)
    conv = repos.conversations.start(a, chapter_a, 1)

    assert repos.conversations.live(b, chapter_b) is None
    assert repos.conversations.get_owned(b, chapter_a, conv.id) is None
    assert repos.conversations.get_owned(a, chapter_b, conv.id) is None
    assert repos.conversations.get_owned(a, chapter_a, conv.id) == conv


def test_append_adds_entries_and_counts_them(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1)

    after = repos.conversations.append(
        conv.id,
        [_say("salut"), {"kind": "tutor", "text": "bonjour"}],
        expected_count=0,
        **BIG,
    )
    assert after.entry_count == 2
    assert after.char_count == len("salut") + len("bonjour")
    assert [e["kind"] for e in after.entries] == ["learner", "tutor"]

    again = repos.conversations.append(conv.id, [_say("et donc ?")], expected_count=2, **BIG)
    assert again.entry_count == 3 and again.live


def test_a_tool_entry_costs_its_arguments(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1)
    tool = {"kind": "tool", "name": "display_board", "arguments": {"card": {"kind": "title"}}}
    after = repos.conversations.append(conv.id, [tool], expected_count=0, **BIG)
    assert after.char_count == len('{"card": {"kind": "title"}}')


def test_a_stale_expected_count_is_busy_and_writes_nothing(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1)
    repos.conversations.append(conv.id, [_say("un")], expected_count=0, **BIG)

    with pytest.raises(ConversationBusy):
        repos.conversations.append(conv.id, [_say("deux")], expected_count=0, **BIG)

    current = repos.conversations.get_owned(user, conv.chapter_id, conv.id)
    assert current and current.entry_count == 1


def test_an_unknown_conversation_is_busy_rather_than_a_crash(repos: Repositories) -> None:
    with pytest.raises(ConversationBusy):
        repos.conversations.append("0" * 32, [_say("x")], expected_count=0, **BIG)


def test_crossing_the_entry_cap_closes_the_conversation(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1)
    after = repos.conversations.append(
        conv.id, [_say("a"), _say("b")], expected_count=0, max_entries=2, max_chars=200_000
    )
    assert not after.live and after.closed_reason == "capped"
    assert repos.conversations.live(user, conv.chapter_id) is None


def test_crossing_the_character_cap_closes_the_conversation(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1)
    after = repos.conversations.append(
        conv.id, [_say("x" * 50)], expected_count=0, max_entries=400, max_chars=40
    )
    assert not after.live and after.closed_reason == "capped"


def test_close_is_idempotent_and_keeps_the_first_reason(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1)
    repos.conversations.close(conv.id, "content_changed")
    repos.conversations.close(conv.id, "replaced")
    stored = repos.conversations.get_owned(user, conv.chapter_id, conv.id)
    assert stored and stored.closed_reason == "content_changed"


def test_started_since_counts_for_the_quota(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    for _ in range(3):
        repos.conversations.start(user, chapter, 1)
    assert repos.conversations.started_since(user, NOW - timedelta(days=400)) == 3
    assert repos.conversations.started_since(user, datetime.now(UTC) + timedelta(days=1)) == 0
    other = _student(repos, "b@b.be")
    assert repos.conversations.started_since(other, NOW - timedelta(days=400)) == 0


def test_conversations_go_with_the_chapter(repos: Repositories) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1)
    assert repos.chapters.delete(user, course, chapter)
    assert repos.conversations.get_owned(user, chapter, conv.id) is None


def test_conversations_go_with_the_course(repos: Repositories) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1)
    assert repos.courses.delete(user, course)
    assert repos.conversations.get_owned(user, chapter, conv.id) is None


def test_conversations_go_with_the_account(repos: Repositories, db_engine) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1)
    with db_engine.begin() as conn:
        conn.execute(sql_text("delete from users where id = :u"), {"u": user})
    assert repos.conversations.get_owned(user, chapter, conv.id) is None
