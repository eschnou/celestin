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
    assert repos.conversations.live(user, chapter, mode="discussion") is None

    conv = repos.conversations.start(user, chapter, content_version=3, mode="discussion")
    assert conv.live and conv.entries == [] and conv.entry_count == 0
    assert conv.content_version == 3 and conv.closed_reason is None
    assert repos.conversations.live(user, chapter, mode="discussion") == conv


def test_starting_again_closes_the_previous_one_as_replaced(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    first = repos.conversations.start(user, chapter, 1, mode="discussion")
    second = repos.conversations.start(user, chapter, 1, mode="discussion")

    assert second.id != first.id
    assert repos.conversations.live(user, chapter, mode="discussion") == second
    stale = repos.conversations.get_owned(user, chapter, first.id, mode="discussion")
    assert stale and not stale.live and stale.closed_reason == "replaced"


def test_only_one_live_row_per_student_and_chapter(repos: Repositories, db_engine) -> None:
    """The partial unique index, not a read-then-write race (007 §4.1)."""
    user = _student(repos)
    chapter = _chapter(repos, user)
    repos.conversations.start(user, chapter, 1, mode="discussion")
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
        repos.conversations.start(user, chapter, 1, mode="discussion")
    assert repos.conversations.live(user, chapter, mode="discussion") is not None


def test_conversations_are_per_student_and_per_chapter(repos: Repositories) -> None:
    a, b = _student(repos, "a@b.be"), _student(repos, "b@b.be")
    chapter_a, chapter_b = _chapter(repos, a), _chapter(repos, b)
    conv = repos.conversations.start(a, chapter_a, 1, mode="discussion")

    assert repos.conversations.live(b, chapter_b, mode="discussion") is None
    assert repos.conversations.get_owned(b, chapter_a, conv.id, mode="discussion") is None
    assert repos.conversations.get_owned(a, chapter_b, conv.id, mode="discussion") is None
    assert repos.conversations.get_owned(a, chapter_a, conv.id, mode="discussion") == conv


def test_append_adds_entries_and_counts_them(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1, mode="discussion")

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
    conv = repos.conversations.start(user, _chapter(repos, user), 1, mode="discussion")
    tool = {"kind": "tool", "name": "display_board", "arguments": {"card": {"kind": "title"}}}
    after = repos.conversations.append(conv.id, [tool], expected_count=0, **BIG)
    assert after.char_count == len('{"card": {"kind": "title"}}')


def test_a_stale_expected_count_is_busy_and_writes_nothing(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1, mode="discussion")
    repos.conversations.append(conv.id, [_say("un")], expected_count=0, **BIG)

    with pytest.raises(ConversationBusy):
        repos.conversations.append(conv.id, [_say("deux")], expected_count=0, **BIG)

    current = repos.conversations.get_owned(user, conv.chapter_id, conv.id, mode="discussion")
    assert current and current.entry_count == 1


def test_an_unknown_conversation_is_busy_rather_than_a_crash(repos: Repositories) -> None:
    with pytest.raises(ConversationBusy):
        repos.conversations.append("0" * 32, [_say("x")], expected_count=0, **BIG)


def test_crossing_the_entry_cap_closes_the_conversation(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1, mode="discussion")
    after = repos.conversations.append(
        conv.id, [_say("a"), _say("b")], expected_count=0, max_entries=2, max_chars=200_000
    )
    assert not after.live and after.closed_reason == "capped"
    assert repos.conversations.live(user, conv.chapter_id, mode="discussion") is None


def test_crossing_the_character_cap_closes_the_conversation(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1, mode="discussion")
    after = repos.conversations.append(
        conv.id, [_say("x" * 50)], expected_count=0, max_entries=400, max_chars=40
    )
    assert not after.live and after.closed_reason == "capped"


def test_close_is_idempotent_and_keeps_the_first_reason(repos: Repositories) -> None:
    user = _student(repos)
    conv = repos.conversations.start(user, _chapter(repos, user), 1, mode="discussion")
    repos.conversations.close(conv.id, "content_changed")
    repos.conversations.close(conv.id, "replaced")
    stored = repos.conversations.get_owned(user, conv.chapter_id, conv.id, mode="discussion")
    assert stored and stored.closed_reason == "content_changed"


def test_started_since_counts_for_the_quota(repos: Repositories) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    for _ in range(3):
        repos.conversations.start(user, chapter, 1, mode="discussion")
    assert repos.conversations.started_since(user, NOW - timedelta(days=400), mode="discussion") == 3
    assert repos.conversations.started_since(user, datetime.now(UTC) + timedelta(days=1), mode="discussion") == 0
    other = _student(repos, "b@b.be")
    assert repos.conversations.started_since(other, NOW - timedelta(days=400), mode="discussion") == 0


def test_conversations_go_with_the_chapter(repos: Repositories) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1, mode="discussion")
    assert repos.chapters.delete(user, course, chapter)
    assert repos.conversations.get_owned(user, chapter, conv.id, mode="discussion") is None


def test_conversations_go_with_the_course(repos: Repositories) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1, mode="discussion")
    assert repos.courses.delete(user, course)
    assert repos.conversations.get_owned(user, chapter, conv.id, mode="discussion") is None


def test_conversations_go_with_the_account(repos: Repositories, db_engine) -> None:
    user = _student(repos)
    chapter = _chapter(repos, user)
    conv = repos.conversations.start(user, chapter, 1, mode="discussion")
    with db_engine.begin() as conn:
        conn.execute(sql_text("delete from users where id = :u"), {"u": user})
    assert repos.conversations.get_owned(user, chapter, conv.id, mode="discussion") is None


# --- révisions (spec 020) ------------------------------------------------------------------------------------


def _revision(repos: Repositories, user: str, course: str, chapter: str):
    return repos.conversations.start_revision(user, course, [{"chapter_id": chapter, "content_version": 1}])


def test_a_revision_names_its_course_and_no_chapter(repos: Repositories) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    revision = _revision(repos, user, course, chapter)
    assert (revision.chapter_id, revision.course_id, revision.content_version) == (None, course, 0)
    assert revision.scope == [{"chapter_id": chapter, "content_version": 1}]
    assert repos.conversations.live_revision(user, course) == revision
    assert repos.conversations.get_revision(user, course, revision.id) == revision


def test_starting_a_revision_replaces_the_live_one_of_the_course_only(repos: Repositories) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    other_course, other_chapter = _course_and_chapter(repos, user)
    first = _revision(repos, user, course, chapter)
    elsewhere = _revision(repos, user, other_course, other_chapter)
    second = _revision(repos, user, course, chapter)
    assert repos.conversations.get_revision(user, course, first.id).closed_reason == "replaced"  # type: ignore[union-attr]
    assert repos.conversations.live_revision(user, course).id == second.id  # type: ignore[union-attr]
    assert repos.conversations.live_revision(user, other_course).id == elsewhere.id  # type: ignore[union-attr]


def test_a_revision_does_not_resolve_under_another_course_or_student(repos: Repositories) -> None:
    user, other = _student(repos), _student(repos, "c@d.be")
    course, chapter = _course_and_chapter(repos, user)
    other_course, _ = _course_and_chapter(repos, user)
    revision = _revision(repos, user, course, chapter)
    assert repos.conversations.get_revision(user, other_course, revision.id) is None
    assert repos.conversations.get_revision(other, course, revision.id) is None


def test_the_chapter_reads_never_meet_a_revision(repos: Repositories) -> None:
    """Every read of a discussion or a séance names its chapter (or the parcours): a révision has neither."""
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    revision = _revision(repos, user, course, chapter)
    since = NOW - timedelta(days=3650)
    for mode in ("discussion", "parcours"):
        assert repos.conversations.live(user, chapter, mode=mode) is None  # type: ignore[arg-type]
        assert repos.conversations.get_owned(user, chapter, revision.id, mode=mode) is None  # type: ignore[arg-type]
        assert repos.conversations.started_since(user, since, mode=mode) == 0  # type: ignore[arg-type]
    assert repos.conversations.started_since(user, since, mode="revision") == 1
    assert repos.conversations.seances(user, chapter, 1) == []
    assert repos.conversations.seances_by_id(user, [revision.id]) == []
    assert repos.conversations.count_seances(user, chapter) == 0
    assert repos.conversations.card_counts(user, chapter, 1) == {}
    assert repos.progress.reset(user, chapter) == 0  # « Recommencer le chapitre » leaves a révision alone
    assert repos.conversations.live_revision(user, course) is not None
    # A discussion and a révision coexist.
    repos.conversations.start(user, chapter, 1, mode="discussion")
    assert repos.conversations.live_revision(user, course) is not None


def _note(repos: Repositories, revision, *results: tuple[str, str, str, int]) -> None:
    """A révision turn with one `record_result` entry per result, appended with its results (spec 020 D6)."""
    from app.domain.revision import NewResult

    current = repos.conversations.get_revision(revision.user_id, revision.course_id, revision.id)
    entries = [
        {"kind": "tool", "name": "record_result", "arguments": {"chapter": 1, "section_id": s, "outcome": o}}
        for _, s, o, _ in results
    ]
    repos.conversations.append(
        revision.id, entries, expected_count=current.entry_count, max_entries=400, max_chars=200_000,  # type: ignore[union-attr]
        results=[NewResult(c, s, o, v) for c, s, o, v in results],  # type: ignore[arg-type]
    )


def test_results_are_written_with_the_transcript_and_read_latest_per_section_at_the_given_versions(
    repos: Repositories,
) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    earlier = _revision(repos, user, course, chapter)
    _note(repos, earlier, (chapter, "a", "todo", 1), (chapter, "b", "shaky", 0))
    revision = _revision(repos, user, course, chapter)
    _note(repos, revision, (chapter, "a", "shaky", 1), (chapter, "a", "solid", 1))  # one turn, the last one counts
    assert repos.conversations.get_revision(user, course, revision.id).entry_count == 2  # type: ignore[union-attr]
    every, here = repos.revision_results.latest(user, course, {chapter: 1}, conversation_id=revision.id)
    assert {k: v.outcome for k, v in every.items()} == {(chapter, "a"): "solid"}
    assert {k: v.outcome for k, v in here.items()} == {(chapter, "a"): "solid"}
    every, here = repos.revision_results.latest(user, course, {chapter: 0}, conversation_id=revision.id)
    assert {k: v.outcome for k, v in every.items()} == {(chapter, "b"): "shaky"} and here == {}
    assert repos.revision_results.latest(user, course, {chapter: 1})[1] == {}  # no révision named: no tally
    assert repos.revision_results.latest(user, course, {}) == ({}, {})


def test_a_busy_append_writes_no_result(repos: Repositories) -> None:
    from app.domain.errors import ConversationBusy
    from app.domain.revision import NewResult

    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    revision = _revision(repos, user, course, chapter)
    with pytest.raises(ConversationBusy):
        repos.conversations.append(
            revision.id, [{"kind": "tutor", "text": "x"}], expected_count=3, max_entries=400, max_chars=200_000,
            results=[NewResult(chapter, "a", "solid", 1)],
        )
    assert repos.revision_results.latest(user, course, {chapter: 1}) == ({}, {})


def test_a_start_that_meets_another_live_row_is_busy(repos: Repositories, monkeypatch) -> None:
    """Another tab's live row the closing UPDATE did not see trips the unique index: `ConversationBusy`, for a
    chapter mode's start as for a révision's (one implementation)."""
    import app.db.repositories as module
    from app.domain.errors import ConversationBusy

    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    _revision(repos, user, course, chapter)
    repos.conversations.start(user, chapter, 1, mode="discussion")
    real = module.update
    monkeypatch.setattr(module, "update", lambda *args: real(*args).where(sql_text("1 = 0")))  # closes nothing
    with pytest.raises(ConversationBusy):
        _revision(repos, user, course, chapter)
    with pytest.raises(ConversationBusy):
        repos.conversations.start(user, chapter, 1, mode="discussion")


def test_revisions_and_results_go_with_the_chapter_course_and_account(repos: Repositories, db_engine) -> None:
    user = _student(repos)
    course, chapter = _course_and_chapter(repos, user)
    revision = _revision(repos, user, course, chapter)
    _note(repos, revision, (chapter, "a", "solid", 1), (chapter, "b", "solid", 1))

    def counts() -> tuple[int, int]:
        with db_engine.connect() as conn:
            return (
                conn.execute(sql_text("select count(*) from revision_results")).scalar_one(),
                conn.execute(sql_text("select count(*) from conversations where mode = 'revision'")).scalar_one(),
            )

    assert counts() == (2, 1)
    assert repos.chapters.delete(user, course, chapter)
    assert counts() == (0, 1)  # the chapter's results go; the révision is closed lazily when next read
    chapter = repos.chapters.create(course, "texte", max_chapters=40).id
    _note(repos, revision, (chapter, "a", "todo", 1))
    assert repos.courses.delete(user, course)
    assert counts() == (0, 0)
    course, chapter = _course_and_chapter(repos, user)
    revision = _revision(repos, user, course, chapter)
    _note(repos, revision, (chapter, "a", "todo", 1))
    with db_engine.begin() as conn:
        conn.execute(sql_text("delete from users where id = :u"), {"u": user})
    assert counts() == (0, 0)
