"""Courses, chapters and runs in the database (005 design 3.10)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import event

from app.db.base import utcnow
from app.db.models import AuthoringRunRow, ChapterRow
from app.db.repositories import Repositories
from app.domain.errors import ChapterLimit, CourseLimit, StaleVersion
from app.domain.progress import Progress
from app.domain.chapter import RunUsage
from app.domain.content import ValidContent
from app.domain.pack import PackIndex
from tests.fixtures.curricula import curriculum


def content(pack: str = "# P", title: str = "T") -> ValidContent:
    index = PackIndex(title=title, sections=frozenset(), exercises=frozenset())
    return ValidContent(pack=pack, index=index, curriculum=curriculum())


@pytest.fixture
def user(repos: Repositories):
    return repos.users.create("a@b.be", "Léa", "hash")


def test_course_create_list_rename_delete(repos: Repositories, user) -> None:
    course = repos.courses.create(user.id, "Physique 5e", "sciences", max_courses=30)
    assert course.subject == "sciences" and course.user_id == user.id
    listed = repos.courses.list_for_user(user.id)
    assert [c.course.id for c in listed] == [course.id] and listed[0].chapters == []
    renamed = repos.courses.rename(user.id, course.id, "Physique")
    assert renamed and renamed.name == "Physique"
    assert repos.courses.get_owned(user.id, course.id) == renamed
    assert repos.courses.delete(user.id, course.id) is True
    assert repos.courses.list_for_user(user.id) == []


def test_course_limit_is_checked_in_the_transaction(repos: Repositories, user) -> None:
    repos.courses.create(user.id, "A", "mathematics", max_courses=2)
    repos.courses.create(user.id, "B", "mathematics", max_courses=2)
    with pytest.raises(CourseLimit):
        repos.courses.create(user.id, "C", "mathematics", max_courses=2)


def test_ownership_is_in_every_query(repos: Repositories, user) -> None:
    other = repos.users.create("b@b.be", "B", "h")
    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    assert repos.courses.get_owned(other.id, course.id) is None
    assert repos.courses.rename(other.id, course.id, "x") is None
    assert repos.courses.delete(other.id, course.id) is False
    assert repos.courses.detail(other.id, course.id) is None
    assert repos.chapters.get_owned(other.id, course.id, chapter.id) is None
    assert repos.chapters.delete(other.id, course.id, chapter.id) is False
    second = repos.courses.create(user.id, "B", "sciences", max_courses=30)
    assert repos.chapters.get_owned(user.id, second.id, chapter.id) is None  # wrong course


def test_chapters_are_appended_and_limited(repos: Repositories, user) -> None:
    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    first = repos.chapters.create(course.id, "un", max_chapters=2)
    second = repos.chapters.create(course.id, "deux", max_chapters=2)
    assert (first.position, second.position) == (1, 2)
    assert not first.ready and first.authoring_state == "idle"
    with pytest.raises(ChapterLimit):
        repos.chapters.create(course.id, "trois", max_chapters=2)
    repos.chapters.delete(user.id, course.id, first.id)
    third = repos.chapters.create(course.id, "trois", max_chapters=2)
    assert third.position == 3
    detail = repos.courses.detail(user.id, course.id)
    assert detail and [c.id for c in detail.chapters] == [second.id, third.id]
    assert repos.chapters.get_owned(user.id, course.id, third.id).chapter.source_text is None  # not loaded by default
    owned = repos.chapters.get_owned(user.id, course.id, third.id, source=True)
    assert owned and owned.chapter.source_text == "trois" and owned.course.id == course.id


def test_list_for_user_is_one_query_without_content(repos: Repositories, user, db_engine) -> None:
    for name in ("A", "B"):
        course = repos.courses.create(user.id, name, "mathematics", max_courses=30)
        for i in range(3):
            repos.chapters.create(course.id, "x" * 1000, max_chapters=40)
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(db_engine, "before_cursor_execute", listener)
    try:
        listed = repos.courses.list_for_user(user.id)
    finally:
        event.remove(db_engine, "before_cursor_execute", listener)
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 1
    assert "source_text" not in statements[0] and "pack" not in statements[0].replace("section_count", "")
    assert [len(c.chapters) for c in listed] == [3, 3]
    assert listed[0].chapters[0].source_text is None


def test_adoption_bumps_version_and_deletes_progress(repos: Repositories, user) -> None:
    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    cur = curriculum()
    adopted = repos.chapters.adopt_content(chapter.id, content())
    assert adopted.ready and adopted.content_version == 1 and adopted.section_count == len(cur.sections)
    assert adopted.curriculum and adopted.curriculum["sections"][0]["id"] == cur.sections[0].id
    repos.progress.save(user.id, chapter.id, Progress(active=cur.sections[0].id))
    again = repos.chapters.adopt_content(chapter.id, content("# P2", "T2"), expected_version=1)
    assert again.content_version == 2 and again.pack == "# P2"
    assert repos.progress.load(user.id, chapter.id) is None


def test_stale_version_is_refused_and_changes_nothing(repos: Repositories, user) -> None:
    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    cur = curriculum()
    repos.chapters.adopt_content(chapter.id, content())
    repos.progress.save(user.id, chapter.id, Progress(active=cur.sections[0].id))
    with pytest.raises(StaleVersion):
        repos.chapters.adopt_content(chapter.id, content("# X", "X"), expected_version=0)
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned and owned.chapter.pack == "# P"
    assert repos.progress.load(user.id, chapter.id) is not None


def test_adoption_rolls_back_as_a_whole(repos: Repositories, user, monkeypatch) -> None:
    from app.db import repositories as module

    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    cur = curriculum()
    repos.chapters.adopt_content(chapter.id, content())
    repos.progress.save(user.id, chapter.id, Progress(active=cur.sections[0].id))

    real_delete = module.delete

    def failing_delete(table):  # noqa: ANN001
        if table is module.ProgressRow:
            raise RuntimeError("disk full")
        return real_delete(table)

    monkeypatch.setattr(module, "delete", failing_delete)
    with pytest.raises(RuntimeError):
        repos.chapters.adopt_content(chapter.id, content("# NEW"))
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned and owned.chapter.pack == "# P" and owned.chapter.content_version == 1


def test_run_counts_and_orphans(repos: Repositories, user, db_engine) -> None:
    from sqlalchemy.orm import Session

    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    now = utcnow()
    with Session(db_engine) as s:
        s.add(AuthoringRunRow(id="r1", user_id=user.id, chapter_id=chapter.id, trigger="create", state="running", model="m", started_at=now - timedelta(hours=30)))
        s.add(AuthoringRunRow(id="r2", user_id=user.id, chapter_id=chapter.id, trigger="retry", state="failed", model="m", started_at=now - timedelta(hours=2)))
        s.add(AuthoringRunRow(id="r3", user_id=user.id, chapter_id=None, trigger="create", state="succeeded", model="m", started_at=now - timedelta(hours=1)))
        s.get(ChapterRow, chapter.id).authoring_state = "generating"
        s.commit()
    assert repos.runs.running_for_user(user.id) == 1
    assert repos.runs.active() == 1
    count, oldest = repos.runs.started_since(user.id, now - timedelta(hours=24))
    assert count == 2 and oldest is not None and abs((oldest - (now - timedelta(hours=2))).total_seconds()) < 1
    assert repos.runs.fail_orphans() == 1
    assert repos.runs.active() == 0
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned and owned.chapter.authoring_state == "failed" and owned.chapter.authoring_error == "interrupted"


def test_editor_adoption_is_refused_while_a_run_is_in_progress(repos: Repositories, user) -> None:
    from app.domain.errors import AuthoringRunning

    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    repos.chapters.adopt_content(chapter.id, content())
    repos.chapters.begin_authoring(
        user_id=user.id, course_id=course.id, chapter_id=chapter.id, source_text=None,
        trigger="retry", model="m", max_chapters=40,
    )
    with pytest.raises(AuthoringRunning):
        repos.chapters.adopt_content(chapter.id, content("# EDIT"), expected_version=1)
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id)
    assert owned and owned.chapter.pack == "# P"


def test_progress_saved_against_an_older_version_is_refused(repos: Repositories, user) -> None:
    course = repos.courses.create(user.id, "A", "mathematics", max_courses=30)
    chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
    repos.chapters.adopt_content(chapter.id, content())
    cur = curriculum()
    repos.progress.save(user.id, chapter.id, Progress(active=cur.sections[0].id), version=1)
    repos.chapters.adopt_content(chapter.id, content("# P2"))  # version 2, progress deleted
    with pytest.raises(StaleVersion):
        repos.progress.save(user.id, chapter.id, Progress(active=cur.sections[0].id), version=1)
    assert repos.progress.load(user.id, chapter.id) is None


def _document_run(repos: Repositories, user, pages: int = 3):
    course = repos.courses.create(user.id, "Maths", "mathematics", max_courses=30)
    chapter, run_id = repos.chapters.begin_authoring(
        user_id=user.id, course_id=course.id, chapter_id=None, source_text="", trigger="create",
        model="m", max_chapters=40, source_kind="document", page_count=pages,
    )
    return course, chapter, run_id


def test_document_run_progress_transcription_and_failure_stage(repos: Repositories, user) -> None:
    course, chapter, run_id = _document_run(repos, user)
    assert (chapter.source_kind, chapter.authoring_stage, chapter.pages_done, chapter.page_count) == (
        "document", "transcription", 0, 3)
    repos.chapters.set_progress(chapter.id, "transcription", 2)
    assert repos.chapters.get_owned(user.id, course.id, chapter.id).chapter.pages_done == 2

    repos.chapters.store_transcription(chapter.id, run_id, "--- page 1 ---\n\nx\n", 3, (4, 1, 0))
    repos.chapters.store_transcription(chapter.id, run_id, "--- page 1 ---\n\ny\n", 3, (4, 1, 0))
    assert repos.chapters.uploads(chapter.id) == [(1, 3)]  # replaced, not appended
    owned = repos.chapters.get_owned(user.id, course.id, chapter.id, source=True)
    assert owned.chapter.source_text == "--- page 1 ---\n\ny\n" and owned.chapter.authoring_stage == "pack"

    assert repos.chapters.finish_failed(chapter.id, run_id, "provider", RunUsage()) == "pack"
    failed = repos.chapters.get_owned(user.id, course.id, chapter.id).chapter
    assert failed.authoring_state == "failed" and failed.authoring_stage == "pack"
    repos.chapters.set_progress(chapter.id, "curriculum")  # not generating any more: ignored
    assert repos.chapters.get_owned(user.id, course.id, chapter.id).chapter.authoring_stage == "pack"


def test_transcription_of_a_deleted_chapter_is_dropped(repos: Repositories, user) -> None:
    course, chapter, run_id = _document_run(repos, user)
    assert repos.chapters.delete(user.id, course.id, chapter.id)
    repos.chapters.store_transcription(chapter.id, run_id, "x", 3, (0, 0, 0))
    assert repos.chapters.uploads(chapter.id) == []


def test_a_course_has_the_language_it_was_created_with(repos: Repositories, user) -> None:
    assert repos.courses.create(user.id, "Physique", "sciences", max_courses=30).language == "fr"
    english = repos.courses.create(user.id, "Physics", "sciences", max_courses=30, language="en")
    assert english.language == "en"
    assert repos.courses.get_owned(user.id, english.id).language == "en"
    assert [e.course.language for e in repos.courses.list_for_user(user.id)].count("en") == 1
