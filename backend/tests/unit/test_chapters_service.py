from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from app.domain.chapter import ChapterRecord, CourseRecord, OwnedChapter
from app.domain.errors import ChapterNotReady, ChapterUnavailable
from app.services import chapters as module
from app.services.chapters import CurriculumCache, to_lesson_chapter
from tests.fixtures.curricula import curriculum

NOW = datetime(2026, 9, 16, tzinfo=UTC)
COURSE = CourseRecord(id="c" * 32, user_id="u", name="Physique", subject="sciences", created_at=NOW, updated_at=NOW)


def owned(version: int = 1, data: object = None, pack: str | None = "# P") -> OwnedChapter:
    data = curriculum().model_dump(mode="json") if data is None else data
    chapter = ChapterRecord(
        id="h" * 32, course_id=COURSE.id, position=1, title="Titre", section_count=2, content_version=version,
        authoring_state="idle", authoring_error=None, created_at=NOW, updated_at=NOW, content_updated_at=NOW,
        source_text="s", pack=pack if version else None, curriculum=data if version else None,
    )
    return OwnedChapter(course=COURSE, chapter=chapter)


def test_lesson_chapter_carries_subject_and_version():
    lesson = to_lesson_chapter(owned(version=3), CurriculumCache())
    assert lesson.subject == "sciences"
    assert lesson.title == "Titre" and lesson.pack == "# P"


def test_parsed_once_per_version(monkeypatch):
    calls = []
    real = module.curriculum_from_json
    monkeypatch.setattr(module, "curriculum_from_json", lambda data, language="fr": calls.append(1) or real(data, language))
    cache = CurriculumCache()
    to_lesson_chapter(owned(version=1), cache)
    to_lesson_chapter(owned(version=1), cache)
    assert len(calls) == 1
    to_lesson_chapter(owned(version=2), cache)
    assert len(calls) == 2


def test_cache_is_bounded():
    cache = CurriculumCache(size=2)
    data = curriculum().model_dump(mode="json")
    for version in range(1, 4):
        cache.get("h", version, data)
    assert len(cache._items) == 2 and ("h", 1) not in cache._items


def test_not_ready_chapter():
    with pytest.raises(ChapterNotReady):
        to_lesson_chapter(owned(version=0), CurriculumCache())


def test_invalid_stored_curriculum_is_unavailable_and_logged(caplog):
    with caplog.at_level(logging.ERROR), pytest.raises(ChapterUnavailable):
        to_lesson_chapter(owned(data={"id": "x", "title": "T", "sections": []}), CurriculumCache())
    assert any(r.message == "chapter_invalid" for r in caplog.records)
