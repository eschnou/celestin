"""Spec 011 task 8.2/8.3: the opt-in scripts take `--language` (the paid runs are not made here)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.domain.language import COURSE_LANGUAGES
from scripts.chapter_files import DEFAULT_CHAPTER_DIR, DEFAULT_ENGLISH_CHAPTER_DIR, default_chapter_dir
from scripts.smoke import SECOND_TURN, context_for, language_of, load_lesson
from scripts.voice_probe import PROBES, unspeakable


def test_the_default_chapter_follows_the_language() -> None:
    assert default_chapter_dir("fr") == DEFAULT_CHAPTER_DIR and default_chapter_dir() == DEFAULT_CHAPTER_DIR
    assert default_chapter_dir("en") == DEFAULT_ENGLISH_CHAPTER_DIR and DEFAULT_ENGLISH_CHAPTER_DIR.is_dir()


def test_the_dutch_chapter_is_the_default_of_a_dutch_run() -> None:
    from scripts.chapter_files import DEFAULT_DUTCH_CHAPTER_DIR

    assert default_chapter_dir("nl") == DEFAULT_DUTCH_CHAPTER_DIR and DEFAULT_DUTCH_CHAPTER_DIR.is_dir()


def test_language_of_reads_the_flag() -> None:
    assert language_of(["x"]) == "fr" and language_of(["x", "--language", "en"]) == "en"
    assert language_of(["x", "--language", "nl"]) == "nl"
    with pytest.raises(SystemExit):
        language_of(["--language", "de"])


def test_load_lesson_loads_the_english_chapter_in_english() -> None:
    settings = Settings(openai_api_key="k", _env_file=None)
    prompts, chapter = load_lesson(settings, ["--language", "en"])
    assert chapter.language == "en" and chapter.title == "Arithmetic and geometric sequences"
    assert context_for(chapter).language == "en"
    assert prompts.tutor("en") != prompts.tutor("fr")
    _, other = load_lesson(settings, ["--language", "en", "--chapter-dir", str(DEFAULT_ENGLISH_CHAPTER_DIR.parent / "statistics_en")])
    assert other.language == "en" and other.title.startswith("Descriptive statistics")


def test_load_lesson_loads_the_dutch_chapter_in_dutch() -> None:
    settings = Settings(openai_api_key="k", _env_file=None)
    prompts, chapter = load_lesson(settings, ["--language", "nl"])
    assert chapter.language == "nl" and chapter.title == "Rekenkundige en meetkundige rijen"
    assert context_for(chapter).language == "nl"
    assert len({prompts.tutor(language) for language in COURSE_LANGUAGES}) == 3


def test_every_language_has_a_second_turn_and_voice_probes() -> None:
    assert set(SECOND_TURN) == set(COURSE_LANGUAGES) and set(PROBES) == set(COURSE_LANGUAGES)
    assert all(len(messages) == 3 for messages in PROBES.values())


@pytest.mark.parametrize(
    ("text", "language", "bad"),
    [
        ("Write it as x squared, then add two point five.", "en", False),
        ("The common ratio is q, so u sub n is u one times q to the n minus one.", "en", False),
        ("It costs 1,500 pounds.", "en", False),
        ("Take x^2 and add 2,5.", "en", True),
        ("Look at $u_n$.", "en", True),
        ("Use \\frac of the two.", "en", True),
        ("Then u_n grows.", "en", True),
        ("Ajoute deux virgule cinq à x au carré.", "fr", False),
        ("Ajoute 2,5 à x au carré.", "fr", False),
        ("Prends x^2.", "fr", True),
        ("Schrijf x kwadraat en tel twee komma vijf op.", "nl", False),
        ("Tel 2,5 op bij x kwadraat.", "nl", False),
        ("Neem x^2.", "nl", True),
        ("Kijk naar $u_n$.", "nl", True),
    ],
)
def test_what_a_voice_cannot_say(text: str, language: str, bad: bool) -> None:
    assert unspeakable(text, language) is bad


def test_a_language_without_a_probe_set_exits_with_a_message() -> None:
    """Spec 017 §4.3: probe vocabulary may lag a language; it says so instead of a KeyError."""
    import pytest

    from scripts.probe import GUARDRAIL_SETS, LANGUAGE_NAME, guardrails

    assert [mode for mode, _ in guardrails("fr")] == ["parcours", "discussion"] == [m for m, _ in GUARDRAIL_SETS["en"]]
    assert LANGUAGE_NAME["en"] == "anglais"
    # A language without a probe set (none today: Dutch has one since spec 017 phase 8) is named in the message.
    missing = [language for language in COURSE_LANGUAGES if language not in LANGUAGE_NAME]
    for language in missing:
        with pytest.raises(SystemExit, match=f"no probe set for '{language}'"):
            LANGUAGE_NAME[language]
        with pytest.raises(SystemExit, match=f"no probe set for '{language}'"):
            guardrails(language)


def test_every_language_has_authoring_fixtures_that_exist() -> None:
    from scripts.authoring_eval import FIXTURES, MATERIAL

    assert set(FIXTURES) == set(COURSE_LANGUAGES)
    for language, rows in FIXTURES.items():
        assert [subject for _, subject in rows] == ["mathematics", "sciences", "mathematics", "mathematics"], language
        assert all((MATERIAL / name).is_file() for name, _ in rows), language


def test_the_dutch_authoring_fixtures_are_dutch_and_the_injection_is_a_dutch_injection() -> None:
    from scripts.authoring_eval import FIXTURES, MATERIAL

    names = [name for name, _ in FIXTURES["nl"]]
    assert names == [
        "maths_kwadratische_nl.txt",
        "fysica_eenparige_beweging_nl.txt",
        "injection_nl.txt",
        "maths_statistiek_nl.txt",
    ]
    injection = (MATERIAL / "injection_nl.txt").read_text(encoding="utf-8")
    assert "instructies" in injection.lower() and "ignore" not in injection.lower()
