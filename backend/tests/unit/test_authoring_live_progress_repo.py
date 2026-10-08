"""Spec 016 §4: the live progress of a preparation, stored on the chapter row."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect

from app.db.base import make_engine
from app.db.repositories import Repositories
from app.db.schema import alembic_config
from app.domain.chapter import RunUsage


@pytest.fixture
def world(repos: Repositories):
    user = repos.users.create("a@b.be", "Léa", "h")
    course = repos.courses.create(user.id, "Maths", "mathematics", max_courses=30)
    return repos, user, course


def begin(repos: Repositories, user, course, *, kind: str = "text", pages: int = 0):
    chapter, run_id = repos.chapters.begin_authoring(
        user_id=user.id, course_id=course.id, chapter_id=None, source_text="x" * 400, trigger="create",
        model="m", max_chapters=40, source_kind=kind, page_count=pages,
    )
    return chapter, run_id


def light(repos: Repositories, user, course, chapter_id: str):
    owned = repos.chapters.get_owned(user.id, course.id, chapter_id)
    assert owned is not None
    return owned.chapter


def test_a_new_run_starts_with_no_characters_and_a_clock(world) -> None:
    repos, user, course = world
    chapter, _ = begin(repos, user, course)
    assert chapter.authoring_received_chars == 0 and chapter.authoring_progress_at is not None


def test_set_received_moves_the_count_and_the_clock_while_generating(world) -> None:
    repos, user, course = world
    chapter, _ = begin(repos, user, course)
    first = light(repos, user, course, chapter.id).authoring_progress_at
    repos.chapters.set_received(chapter.id, 1200)
    after = light(repos, user, course, chapter.id)
    assert after.authoring_received_chars == 1200 and after.authoring_progress_at >= first


def test_set_received_without_a_count_only_touches_the_clock(world) -> None:
    repos, user, course = world
    chapter, _ = begin(repos, user, course)
    repos.chapters.set_received(chapter.id, 500)
    repos.chapters.set_received(chapter.id, None)
    assert light(repos, user, course, chapter.id).authoring_received_chars == 500


def test_a_stage_starting_restarts_the_count(world) -> None:
    repos, user, course = world
    chapter, _ = begin(repos, user, course)
    repos.chapters.set_received(chapter.id, 900)
    repos.chapters.set_progress(chapter.id, "curriculum")
    after = light(repos, user, course, chapter.id)
    assert after.authoring_stage == "curriculum" and after.authoring_received_chars == 0


def test_a_late_write_changes_nothing_on_a_chapter_that_is_not_generating(world) -> None:
    repos, user, course = world
    chapter, run_id = begin(repos, user, course)
    repos.chapters.set_received(chapter.id, 700)
    repos.chapters.finish_failed(chapter.id, run_id, "timeout", RunUsage())
    failed = light(repos, user, course, chapter.id)
    assert failed.authoring_received_chars == 0 and failed.authoring_progress_at is None
    repos.chapters.set_received(chapter.id, 999)
    still = light(repos, user, course, chapter.id)
    assert still.authoring_received_chars == 0 and still.authoring_progress_at is None


def test_the_stored_transcription_restarts_the_count_for_the_pack(world) -> None:
    repos, user, course = world
    chapter, run_id = begin(repos, user, course, kind="document", pages=2)
    repos.chapters.set_received(chapter.id, 10)
    repos.chapters.store_transcription(chapter.id, run_id, "--- page 1 ---\n…", 2, (0, 0, 0))
    after = light(repos, user, course, chapter.id)
    assert after.authoring_stage == "pack" and after.authoring_received_chars == 0 and after.authoring_progress_at


def test_the_orphan_sweep_clears_both(world) -> None:
    repos, user, course = world
    chapter, _ = begin(repos, user, course)
    repos.chapters.set_received(chapter.id, 800)
    assert repos.runs.fail_orphans() == 1
    after = light(repos, user, course, chapter.id)
    assert after.authoring_state == "failed" and after.authoring_received_chars == 0 and after.authoring_progress_at is None


def test_a_retry_after_a_failure_starts_from_zero(world) -> None:
    repos, user, course = world
    chapter, run_id = begin(repos, user, course)
    repos.chapters.set_received(chapter.id, 800)
    repos.chapters.finish_failed(chapter.id, run_id, "provider", RunUsage())
    again, _ = repos.chapters.begin_authoring(
        user_id=user.id, course_id=course.id, chapter_id=chapter.id, source_text=None, trigger="retry",
        model="m", max_chapters=40,
    )
    assert again.authoring_received_chars == 0 and again.authoring_progress_at is not None


def test_the_migration_adds_both_columns_to_existing_rows(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(alembic_config(url), "0010")
    columns = {c["name"] for c in inspect(make_engine(url)).get_columns("chapters")}
    assert "authoring_received_chars" not in columns
    command.upgrade(alembic_config(url), "head")
    columns = {c["name"]: c for c in inspect(make_engine(url)).get_columns("chapters")}
    assert columns["authoring_received_chars"]["nullable"] is False and columns["authoring_progress_at"]["nullable"] is True
    command.downgrade(alembic_config(url), "0010")
    assert "authoring_progress_at" not in {c["name"] for c in inspect(make_engine(url)).get_columns("chapters")}
    command.upgrade(alembic_config(url), "head")
