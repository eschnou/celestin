"""Spec 011 task 8.2/8.3: the opt-in scripts take `--language` (the paid runs are not made here)."""

from __future__ import annotations

import pytest

from app.config import Settings
from scripts.chapter_files import DEFAULT_CHAPTER_DIR, DEFAULT_ENGLISH_CHAPTER_DIR, default_chapter_dir
from scripts.smoke import SECOND_TURN, context_for, language_of, load_lesson
from scripts.voice_probe import PROBES, unspeakable


def test_the_default_chapter_follows_the_language() -> None:
    assert default_chapter_dir("fr") == DEFAULT_CHAPTER_DIR and default_chapter_dir() == DEFAULT_CHAPTER_DIR
    assert default_chapter_dir("en") == DEFAULT_ENGLISH_CHAPTER_DIR and DEFAULT_ENGLISH_CHAPTER_DIR.is_dir()


def test_language_of_reads_the_flag() -> None:
    assert language_of(["x"]) == "fr" and language_of(["x", "--language", "en"]) == "en"
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


def test_every_language_has_a_second_turn_and_voice_probes() -> None:
    assert set(SECOND_TURN) == {"fr", "en"} and set(PROBES) == {"fr", "en"}
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
    ],
)
def test_what_a_voice_cannot_say(text: str, language: str, bad: bool) -> None:
    assert unspeakable(text, language) is bad
