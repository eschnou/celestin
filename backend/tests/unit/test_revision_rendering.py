"""Spec 020: what a révision turn reads, rendered from its chapters.

The révision's prefix (the chosen packs under their headers, one overview per chapter, the révision's mode files)
is its own cached prefix per selection, pinned per language like the parcours and discussion ones:
`system_text_sha_revision.txt`, `system_text_sha_en_revision.txt` and `system_text_sha_nl_revision.txt` were
generated once from the fixture révision of each language (sequences, then statistics), read by a person, and
pinned. Delete a file and rerun to regenerate it after an intended change to a révision prompt, a pack or a
curriculum of those fixtures.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import get_settings
from app.domain.progress import Progress
from app.domain.revision import Noted
from app.services import curriculum_render, prompt_service
from app.services.prompts import PromptLibrary
from scripts.chapter_files import load_revision

RENDER = Path(__file__).parents[1] / "fixtures" / "render"
PROMPTS = PromptLibrary(get_settings().prompts_dir)
PINS = {"fr": "system_text_sha_revision.txt", "en": "system_text_sha_en_revision.txt", "nl": "system_text_sha_nl_revision.txt"}


def _scope(language: str):
    return load_revision("mathematics", PROMPTS, language)  # type: ignore[arg-type]


def _rendering(language: str, voice: bool = False) -> str:
    scope = _scope(language)
    text = prompt_service.revision_system_text(
        PROMPTS.tutor(language),  # type: ignore[arg-type]
        PROMPTS.subject("mathematics", language),  # type: ignore[arg-type]
        scope,
        PROMPTS.mode("revision", language),  # type: ignore[arg-type]
        PROMPTS.mode_opening("revision", language),  # type: ignore[arg-type]
        language,  # type: ignore[arg-type]
    )
    return text


@pytest.mark.parametrize("language", ["fr", "en", "nl"])
def test_the_revision_rendering_is_byte_stable(language: str) -> None:
    text = _rendering(language)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = RENDER / PINS[language]
    if not path.exists():
        path.write_text(digest + "\n")
    assert digest == path.read_text().strip()


@pytest.mark.parametrize(
    ("language", "heads", "mode_title"),
    [
        ("fr", ("# Chapitre 1 — Les suites numériques", "# Chapitre 2 — Statistique descriptive"), "## La révision"),
        ("en", ("# Chapter 1 — Arithmetic and geometric sequences", "# Chapter 2 — Descriptive statistics"), "## The revision"),
        ("nl", ("# Hoofdstuk 1 — Rekenkundige en meetkundige rijen", "# Hoofdstuk 2 — Beschrijvende statistiek"), "## De herhaling"),
    ],
)
def test_the_packs_come_in_course_order_under_their_headers(language: str, heads: tuple[str, str], mode_title: str) -> None:
    scope = _scope(language)
    text = _rendering(language)
    first, second = (text.index(head) for head in heads)
    assert first < second
    # Each pack follows its header, whole.
    for chapter, head in zip(scope.chapters, heads, strict=True):
        assert f"\n\n{chapter.pack.strip()}" in text[text.index(head):]
    assert mode_title in text
    # One overview per chapter, read-only: every section id is listed, no tool is named in the overviews.
    overview = curriculum_render.revision_overview(scope.chapters, language)  # type: ignore[arg-type]
    assert overview in text
    for chapter in scope.chapters:
        for section in chapter.curriculum.sections:
            assert f"`{section.id}`" in overview
    for tool in ("start_section", "complete_section", "skip_section", "record_result", "display_board"):
        assert tool not in overview
    # The révision layer names no section tool; it names its own.
    assert "start_section" not in text and "complete_section" not in text and "skip_section" not in text
    assert "`record_result`" in text


def test_the_three_languages_render_different_prefixes() -> None:
    assert len({_rendering(language) for language in ("fr", "en", "nl")}) == 3


def test_a_selection_is_its_own_prefix() -> None:
    scope = _scope("fr")
    one = replace(scope, chapters=scope.chapters[:1])
    assert curriculum_render.revision_packs(one.chapters, "fr") != curriculum_render.revision_packs(scope.chapters, "fr")
    assert curriculum_render.revision_packs(one.chapters, "fr").count("# Chapitre ") == 1


def _state(language: str) -> str:
    scope = _scope(language)
    first, second = scope.chapters
    ids = [s.id for s in first.curriculum.sections]
    first = replace(first, progress=Progress(done=frozenset({ids[0]}), skipped=frozenset({ids[2]}), active=ids[3]))
    earlier = {
        (first.id, ids[1]): Noted("shaky", datetime(2026, 11, 12, 15, 0, tzinfo=UTC)),
        (second.id, second.curriculum.sections[0].id): Noted("solid", datetime(2026, 11, 13, 9, 0, tzinfo=UTC)),
    }
    return curriculum_render.revision_state(
        (first, second), earlier, {"solid": 2, "shaky": 1, "todo": 0}, datetime(2026, 11, 15, 18, 5), language  # type: ignore[arg-type]
    )


def test_the_state_message_says_what_was_done_skipped_never_done_and_noted() -> None:
    text = _state("fr")
    assert text.splitlines()[0] == "Nous sommes dimanche 15 novembre, 18 h 05 (le soir)."
    assert "Chapitre 1 — « Les suites numériques » : 1 section(s) faite(s), 1 passée(s) et 5 jamais faite(s) sur 7." in text
    assert "- Faites : « 1. Suites numériques »." in text
    assert "- Passées, jamais travaillées avec toi : « 3. Somme des termes d'une suite arithmétique »." in text
    # An active section that is not done is never done, for a révision.
    assert "« 4. Exercices sur les suites arithmétiques »" in text.split("- Jamais faites : ")[1].splitlines()[0]
    assert "- Derniers bilans : « 2. Les suites arithmétiques » : fragile (12 novembre)." in text
    assert "« 1. Population, individu, variable » : acquis (13 novembre)" in text
    assert text.splitlines()[-1] == "Cette révision : 3 section(s) notée(s) — 2 acquis, 1 fragile(s), 0 à revoir."


def test_the_state_message_says_when_nothing_was_noted_yet() -> None:
    scope = _scope("fr")
    text = curriculum_render.revision_state(scope.chapters, {}, {}, None, "fr")
    assert text.splitlines()[-1] == "Cette révision : rien de noté pour l'instant."
    assert "Derniers bilans" not in text and "Nous sommes" not in text


@pytest.mark.parametrize(
    ("language", "words"),
    [
        ("en", ("It is Sunday 15 November", "Skipped, never worked on with you", "shaky (12 November)", "This revision: 3 section(s) noted — 2 solid, 1 shaky, 0 to review.")),
        ("nl", ("Het is zondag 15 november", "Overgeslagen, nooit met jou behandeld", "wankel (12 november)", "Deze herhaling: 3 sectie(s) genoteerd — 2 gekend, 1 wankel, 0 te herhalen.")),
    ],
)
def test_the_state_message_follows_the_course_language(language: str, words: tuple[str, ...]) -> None:
    text = _state(language)
    for word in words:
        assert word in text, word
    for french in ("Nous sommes", "Faites", "fragile", "acquis"):
        assert french not in text


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("fr", "Bilan noté. Cette révision : 1 acquis, 2 fragile(s), 0 à revoir (3 section(s) notée(s))."),
        ("en", "Self-assessment noted. This revision: 1 solid, 2 shaky, 0 to review (3 section(s) noted)."),
        ("nl", "Zelfbeoordeling genoteerd. Deze herhaling: 1 gekend, 2 wankel, 0 te herhalen (3 sectie(s) genoteerd)."),
    ],
)
def test_the_tally_is_one_line_from_the_counts(language: str, expected: str) -> None:
    assert curriculum_render.revision_tally({"solid": 1, "shaky": 2, "todo": 0}, language) == expected  # type: ignore[arg-type]
