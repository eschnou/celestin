"""Spec 011 R3.2/R3.5: the English prompt set keeps what the French one holds.

The French assertions of `test_prompt_files.py` are untouched; this runs the shared
invariants for each language, and compares each English file with its French twin: same
sections, same markers, same tool and block names.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domain.language import COURSE_LANGUAGES
from app.domain.mode import MODES
from app.domain.subject import available_subjects
from app.services.prompt_service import VOICE_END, VOICE_START
from app.services.prompts import PromptLibrary

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
LIBRARY = PromptLibrary(PROMPTS)

# What differs between the languages in the checks below.
WORDS = {
    "fr": {
        "subject_words": ("mathématique", "physique", "suite arithmétique", "u₁", "5e secondaire"),
        "gender": r"\belle\b",
        "to_check": "Points à vérifier",
        "lesson": "**Leçon.**",
        "off_topic": "Hors sujet",
        "voice_titles": ("Quand on se parle à voix haute", "à voix haute"),
    },
    "en": {
        "subject_words": ("mathematics", "physics", "arithmetic sequence", "u_1", "5th year", "belgi", "fédération"),
        "gender": r"\b(?:she|he|her|hers|his|him)\b",
        "to_check": "Points to check",
        "lesson": "**Lesson.**",
        "off_topic": "Off-topic",
        "voice_titles": ("When we talk out loud", "out loud"),
    },
}
MARKERS = (
    "<!-- SUBJECT -->",
    "<!-- COURSE_PACK -->",
    "<!-- CURRICULUM -->",
    "<!-- MODE -->",
    "<!-- MODE_OPENING -->",
)
LANGUAGES = list(COURSE_LANGUAGES)


def read(name: str, language: str) -> str:
    base, _, ext = name.rpartition(".")
    return (PROMPTS / f"{base}.{language}.{ext}").read_text(encoding="utf-8")


def neutral(text: str, where: str, language: str) -> None:
    lowered = text.lower()
    for word in WORDS[language]["subject_words"]:
        assert word not in lowered, f"{where}: {word}"
    assert not re.search(WORDS[language]["gender"], lowered), where


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_tutor_prompt_is_subject_neutral_and_gender_neutral(language: str) -> None:
    text = read("tutor.md", language)
    for marker in MARKERS:
        assert text.count(marker) == 1, marker
    positions = [text.index(marker) for marker in MARKERS]
    assert positions == sorted(positions)
    neutral(text, f"tutor.{language}.md", language)
    assert WORDS[language]["to_check"] in text


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_tutor_prompt_cites_the_templates_last_heading(language: str) -> None:
    """The section the tutor never teaches is the last one of every pack template."""
    cited = WORDS[language]["to_check"]
    assert cited in read("tutor.md", language)
    for info in available_subjects():
        template = LIBRARY.template(info.id, language)  # type: ignore[arg-type]
        assert template.headings[-1][1] == cited, (info.id, template.headings[-1])
        assert template.language == language


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_mode_has_both_layers_neutral_and_marker_free(language: str) -> None:
    for mode in MODES:
        for name in (f"modes/{mode}.md", f"modes/{mode}.opening.md"):
            text = read(name, language)
            assert text.strip(), name
            neutral(text, f"{name} ({language})", language)
            for marker in MARKERS[:4]:
                assert marker not in text, f"{name}: {marker}"
    assert WORDS[language]["lesson"] in read("modes/parcours.md", language)
    discussion = read("modes/discussion.md", language)
    assert "start_section" not in discussion and "complete_section" not in discussion


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_available_subject_prompt_has_one_voice_block_at_the_end(language: str) -> None:
    for info in available_subjects():
        text = read(f"subjects/{info.id}.md", language)
        assert text.count(VOICE_START) == 1 and text.count(VOICE_END) == 1
        assert text.index(VOICE_START) < text.index(VOICE_END)
        assert WORDS[language]["off_topic"] in text


def test_the_tutor_prompts_voice_block_is_the_only_one_and_text_mode_drops_it() -> None:
    for language in LANGUAGES:
        text = read("tutor.md", language)
        assert text.count(VOICE_START) == 1 and text.count(VOICE_END) == 1


TRANSCRIPTION = {
    "fr": ("--- page N ---", "[manuscrit]", "[incertain:", "[illisible]", "[figure :", "[barré:", "[page vide]"),
    "en": ("--- page N ---", "[handwritten]", "[uncertain:", "[illegible]", "[figure:", "[crossed out:", "[empty page]"),
}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_transcription_prompt_demands_doubt_and_page_markers(language: str) -> None:
    text = read("transcription/transcribe.md", language)
    for convention in TRANSCRIPTION[language]:
        assert convention in text, convention
    # The marks of the other language are not taught.
    other = TRANSCRIPTION["en" if language == "fr" else "fr"]
    for convention in other[1:]:
        assert convention not in text, convention
    assert "[uncertain:" in read("transcription/verify.md", language) or language == "fr"


def test_the_english_transcription_prompt_never_translates() -> None:
    assert "never translate" in read("transcription/transcribe.md", "en").lower()
    assert "never translate" in read("transcription/verify.md", "en").lower()


def test_the_english_authoring_prompt_reads_a_transcription_of_pages() -> None:
    pack = read("authoring/pack.md", "en")
    assert "If the material is a transcription of pages" in pack and "p. 5" in pack
    for mark in ("[handwritten]", "[uncertain: a | b]", "[illegible]", "[figure: …]", "[crossed out: …]"):
        assert mark in pack, mark
    assert "restructure, never add" in pack.lower()


# --- structure: each English file against its French twin -----------------------------

TWINS = sorted(str(p.relative_to(PROMPTS)).replace(".fr.md", "") for p in PROMPTS.glob("**/*.fr.md"))


def outline(text: str) -> list[int]:
    """The levels of the headings, in order: the skeleton of a file."""
    return [len(m.group(1)) for m in re.finditer(r"^(#{1,4}) ", text, re.MULTILINE)]


def names(text: str) -> set[str]:
    """What the model is told to call: tools, fields and blocks written `like_this`."""
    found = (m.group(1) for m in re.finditer(r"`([^`\s]+)`", text))
    return {t for t in found if re.fullmatch(r"[a-z_]+(?:\(.*\))?", t)}


def test_every_french_file_has_an_english_twin_and_the_converse() -> None:
    english = sorted(str(p.relative_to(PROMPTS)).replace(".en.md", "") for p in PROMPTS.glob("**/*.en.md"))
    assert TWINS == english


@pytest.mark.parametrize("twin", TWINS)
def test_an_english_file_has_the_skeleton_of_its_french_twin(twin: str) -> None:
    fr, en = read(f"{twin}.md", "fr"), read(f"{twin}.md", "en")
    assert outline(en) == outline(fr), twin
    for marker in (*MARKERS, VOICE_START.strip(), VOICE_END.strip()):
        assert en.count(marker) == fr.count(marker), (twin, marker)
    assert names(en) == names(fr), (twin, names(en) ^ names(fr))
    assert en.count("`display_board`") == fr.count("`display_board`") or twin == "tutor"


@pytest.mark.parametrize("twin", [t for t in TWINS if t.startswith("templates/")])
def test_an_english_template_keeps_the_positions_of_the_french_one(twin: str) -> None:
    subject = twin.split("/")[1].split(".")[0]
    french, english = LIBRARY.template(subject, "fr"), LIBRARY.template(subject, "en")  # type: ignore[arg-type]
    assert [n for n, _ in english.headings] == [n for n, _ in french.headings]
    assert english.exercises_section == french.exercises_section
    assert english.text.count("###") == french.text.count("###")


@pytest.mark.parametrize("twin", TWINS)
def test_an_english_file_carries_no_french(twin: str) -> None:
    text = read(f"{twin}.md", "en")
    # The tutor's name is a proper noun, not French: « Célestin » is the one accent an English file keeps.
    prose = text.replace("<materiel>", "").replace("</materiel>", "").replace("Célestin", "Celestin")
    accented = re.findall(r"[àâçéèêëîïôûùüÿœ]", prose, re.IGNORECASE)
    assert not accented, (twin, set(accented))
    assert "«" not in text and "»" not in text, twin


# What the interface sends to the model for the learner (frontend `lib/tutor/prompts.ts`, pinned
# there per language) is quoted by the path-mode prompt, so Célestin recognises it.
CITED = {
    "fr": ("« Étape suivante »", "« Section suivante »", "On commence la section …", "Ma réponse à la question : …"),
    "en": ("“Next step”", "“Next section”", "Shall we start the section", "My answer to the question: …"),
}


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_path_prompt_quotes_the_sentences_the_interface_sends(language: str) -> None:
    parcours = " ".join(read("modes/parcours.md", language).split())
    for sentence in CITED[language]:
        assert sentence in parcours, sentence


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_work_reading_prompt_keeps_the_transcription_conventions(language: str) -> None:
    """The student's photo is read with the marks of the course transcription: a doubt is marked, an
    illegible word is not guessed, nothing is corrected, and a photo with no writing says so in one fixed
    phrase the route recognises (`api/routes/work.py`)."""
    text = read("transcription/work.md", language)
    doubt, illegible, nothing = {
        "fr": ("[incertain:", "[illisible]", "[rien de lisible]"),
        "en": ("[uncertain:", "[illegible]", "[nothing legible]"),
    }[language]
    for mark in (doubt, illegible, nothing, "$…$"):
        assert mark in text
    assert "```" not in text.split("## La réponse" if language == "fr" else "## The answer")[0]
    if language == "en":
        assert "never translate" in text.lower()
