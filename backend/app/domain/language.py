"""The course languages (spec 011 §3.2). Imports nothing, so errors can use it.

A course's language is a different thing from the interface language (`Locale`): it is
the language of the material, the pack, the curriculum, Célestin's speech and the board's
notation, and it is the only language the model path ever takes. Every table that
depends on it is declared with `by_language`, so a language missing from a table fails
at import and not in front of a student.
"""

from __future__ import annotations

from typing import Literal, TypeGuard, TypeVar, get_args

CourseLanguage = Literal["fr", "en", "nl"]
COURSE_LANGUAGES: tuple[CourseLanguage, ...] = get_args(CourseLanguage)
DEFAULT_COURSE_LANGUAGE: CourseLanguage = "fr"

T = TypeVar("T")


def is_course_language(value: object) -> TypeGuard[CourseLanguage]:
    return isinstance(value, str) and value in COURSE_LANGUAGES


def require_language(value: str) -> CourseLanguage:
    """The language a request names, or `InvalidLanguage` (422)."""
    if not is_course_language(value):
        from app.domain.errors import InvalidLanguage  # errors import the catalog: keep this module a leaf

        raise InvalidLanguage()
    return value


def by_language(**table: T) -> dict[CourseLanguage, T]:
    """A per-language table, complete or not at all: `by_language(fr=..., en=...)`."""
    if set(table) != set(COURSE_LANGUAGES):
        missing = sorted(set(COURSE_LANGUAGES) - set(table))
        extra = sorted(set(table) - set(COURSE_LANGUAGES))
        raise ValueError(f"by_language: missing {missing}, unknown {extra}")
    return {language: table[language] for language in COURSE_LANGUAGES}
