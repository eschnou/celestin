"""Spec 011 §3.2: the course languages, `by_language`, and which subject is offered in which."""

from __future__ import annotations

import pytest

from app.domain.errors import InvalidLanguage, InvalidSubject
from app.domain.language import (
    COURSE_LANGUAGES,
    DEFAULT_COURSE_LANGUAGE,
    by_language,
    is_course_language,
    require_language,
)
from app.domain.locale import LOCALES
from app.domain.subject import offered, offered_languages, offers, require_offered


def test_the_course_languages_are_french_english_and_dutch() -> None:
    assert COURSE_LANGUAGES == ("fr", "en", "nl") and DEFAULT_COURSE_LANGUAGE == "fr"
    assert set(COURSE_LANGUAGES) <= set(LOCALES)  # a course language is also an interface language, two types on purpose


def test_by_language_is_complete_or_nothing() -> None:
    assert by_language(fr=1, en=2, nl=3) == {"fr": 1, "en": 2, "nl": 3}
    with pytest.raises(ValueError, match="missing"):
        by_language(fr=1, en=2)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="unknown"):
        by_language(fr=1, en=2, nl=3, de=4)


@pytest.mark.parametrize("value", ["fr", "en"])
def test_require_language_accepts_the_supported_ones(value: str) -> None:
    assert require_language(value) == value and is_course_language(value)


@pytest.mark.parametrize("value", ["de", "", "FR", "fr-BE"])
def test_require_language_refuses_the_rest(value: str) -> None:
    with pytest.raises(InvalidLanguage):
        require_language(value)


def test_the_error_reads_in_both_interface_languages() -> None:
    assert InvalidLanguage().message("fr") == "Choisis une langue dans la liste."
    assert InvalidLanguage().message("en") == "Pick a language from the list."
    assert InvalidLanguage.code == "invalid_language" and InvalidLanguage.status == 422


def test_the_launch_subjects_are_offered_in_french_english_and_dutch() -> None:
    subjects = ("mathematics", "sciences", "languages", "general")
    for subject in subjects:
        assert offers(subject, "fr") and offers(subject, "en") and offers(subject, "nl")
    assert offered() == [(subject, language) for subject in subjects for language in ("fr", "en", "nl")]
    assert offered_languages() == ("fr", "en", "nl")
    require_offered("sciences", "en")


def test_a_subject_written_in_french_only_refuses_english(french_only: None) -> None:
    assert offers("mathematics", "fr") and not offers("mathematics", "en")
    assert offered() == [(s, "fr") for s in ("mathematics", "sciences", "languages", "general")]
    assert offered_languages() == ("fr",)
    require_offered("sciences", "fr")
    with pytest.raises(InvalidLanguage):
        require_offered("sciences", "en")


def test_a_subject_that_is_not_in_the_list_cannot_be_chosen() -> None:
    # The categories are broad on purpose: « history » is a general course, not a subject of its own.
    with pytest.raises(InvalidSubject):
        from app.domain.subject import require_available

        require_available("history")
