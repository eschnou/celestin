"""Stored chapters as lessons (005 design 3.3, 3.11).

A turn needs the parsed curriculum; parsing the stored JSON once per content
version keeps a turn to one extra query and no repeated validation.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from threading import Lock

from pydantic import ValidationError

from app.domain.chapter import LessonChapter, OwnedChapter
from app.domain.curriculum import Curriculum, curriculum_from_json
from app.domain.errors import ChapterNotReady, ChapterUnavailable
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage

log = logging.getLogger(__name__)


class CurriculumCache:
    def __init__(self, size: int = 256) -> None:
        self._size = size
        self._items: OrderedDict[tuple[str, int], Curriculum] = OrderedDict()
        self._lock = Lock()  # routes read it from the threadpool

    def get(
        self, chapter_id: str, version: int, data: object, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
    ) -> Curriculum:
        key = (chapter_id, version)
        with self._lock:
            found = self._items.get(key)
            if found is not None:
                self._items.move_to_end(key)
                return found
        parsed = curriculum_from_json(data, language)
        with self._lock:
            self._items[key] = parsed
            while len(self._items) > self._size:
                self._items.popitem(last=False)
        return parsed


def to_lesson_chapter(owned: OwnedChapter, cache: CurriculumCache) -> LessonChapter:
    """`ChapterNotReady` before the first adoption; `ChapterUnavailable` when the
    stored content no longer validates (rules tightened since it was saved)."""
    chapter = owned.chapter
    if not chapter.ready or chapter.pack is None or chapter.curriculum is None:
        raise ChapterNotReady()
    try:
        curriculum = cache.get(chapter.id, chapter.content_version, chapter.curriculum, owned.course.language)
    except ValidationError as exc:
        log.error("chapter_invalid", extra={"chapter_id": chapter.id, "issues": exc.error_count()})
        raise ChapterUnavailable() from exc
    return LessonChapter(
        id=chapter.id,
        subject=owned.course.subject,
        language=owned.course.language,
        title=chapter.title or curriculum.title,
        pack=chapter.pack,
        curriculum=curriculum,
        version=chapter.content_version,
    )
