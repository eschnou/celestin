"""Subjects (005 design 3.2): a closed list defined in code.

A subject is offered only once its subject prompt and pack template exist; adding
one is those two files plus flipping `available`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast, get_args

from app.domain.errors import InvalidLanguage, InvalidSubject
from app.domain.language import COURSE_LANGUAGES, CourseLanguage
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.messages import render

# Four categories, grouped by how a subject is taught and answered, not by school discipline: the
# student's material carries the content, the subject only the way of teaching, writing and checking.
#   mathematics  calculation, proof, exact notation
#   sciences     physics, chemistry, biology, general science: quantities, laws, experiments, diagrams
#   languages    French and foreign languages: rules, vocabulary, conjugations, texts
#   general      history, geography, general studies, anything learnt from the course: facts, causes, documents
Subject = Literal["mathematics", "sciences", "languages", "general"]


@dataclass(frozen=True)
class SubjectInfo:
    id: Subject
    available: bool
    # The course languages this subject is written in: its subject prompt and pack
    # template exist for each (spec 011 R1.7).
    languages: tuple[CourseLanguage, ...] = ()

    def label(self, locale: Locale = DEFAULT_LOCALE) -> str:
        """The subject's name in the student's language (`subject.<id>` in the catalog)."""
        return render(f"subject.{self.id}", locale)


SUBJECTS: dict[Subject, SubjectInfo] = {
    info.id: info
    for info in (
        SubjectInfo("mathematics", True, ("fr", "en")),
        SubjectInfo("sciences", True, ("fr", "en")),
        SubjectInfo("languages", True, ("fr", "en")),
        SubjectInfo("general", True, ("fr", "en")),
    )
}

SUBJECT_IDS: tuple[Subject, ...] = get_args(Subject)


def available_subjects() -> list[SubjectInfo]:
    return [info for info in SUBJECTS.values() if info.available]


def require_available(value: str) -> Subject:
    info = SUBJECTS.get(cast(Subject, value))
    if info is None or not info.available:
        raise InvalidSubject()
    return info.id


def offers(subject: Subject, language: CourseLanguage) -> bool:
    return SUBJECTS[subject].available and language in SUBJECTS[subject].languages


def offered() -> list[tuple[Subject, CourseLanguage]]:
    """Every (subject, language) pair a student can create a course in."""
    return [(info.id, language) for info in available_subjects() for language in info.languages]


def offered_languages() -> tuple[CourseLanguage, ...]:
    """The languages some available subject is offered in, in `COURSE_LANGUAGES` order."""
    present = {language for _, language in offered()}
    return tuple(language for language in COURSE_LANGUAGES if language in present)


def require_offered(subject: Subject, language: CourseLanguage) -> None:
    if not offers(subject, language):
        raise InvalidLanguage()
