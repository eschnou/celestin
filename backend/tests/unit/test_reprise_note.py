"""The reprise note (spec 018 D5): what `start_section` ends with when a section left
unfinished in an earlier séance is taken up again. Model-facing text, per course language."""

from __future__ import annotations

import json

import pytest

from app.api.schemas.chat import ToolEntry
from app.domain.progress import Progress
from app.services import curriculum_render
from app.services.tools import registry
from app.services.tools.section import StartSectionArgs, replay_start, start_section
from tests.fixtures.curricula import ctx_for, curriculum

CARDS = [
    {"kind": "title", "title": "Les  suites\nnumériques"},
    {"kind": "explanation", "title": "Définition", "blocks": []},
    {"kind": "check_question", "question": "Quel est u₂ ?", "options": [], "correct_option_id": "a", "feedback": "f"},
    {"kind": "recap", "acquired": ["x"], "next": "y"},
]


def test_the_note_lists_the_cards_in_order_and_says_what_to_do() -> None:
    note = curriculum_render.reprise(CARDS, "fr")
    assert note == (
        "Reprise : cette section a déjà été travaillée lors d'une séance précédente. "
        "Cartes déjà montrées, dans l'ordre :\n"
        "- titre : Les suites numériques\n"
        "- explication : Définition\n"
        "- question de compréhension : Quel est u₂ ?\n"
        "- bilan\n"
        "Dis en une phrase à ton élève où vous en étiez, puis continue après la dernière carte, "
        "sans reprendre la section depuis le début."
    )


@pytest.mark.parametrize(
    ("language", "head", "line"),
    [
        ("en", "Resuming: this section was already worked on", "- check question: Quel est u₂ ?"),
        ("nl", "Hervatting: aan deze sectie werd al gewerkt", "- begripsvraag: Quel est u₂ ?"),
    ],
)
def test_the_note_is_written_in_the_courses_language(language: str, head: str, line: str) -> None:
    note = curriculum_render.reprise(CARDS, language)  # type: ignore[arg-type]
    assert note is not None and note.startswith(head) and line in note.splitlines()
    assert "Reprise" not in note and "Dis en une phrase" not in note


def test_no_cards_no_note() -> None:
    assert curriculum_render.reprise([], "fr") is None


def test_the_note_keeps_the_last_cards_only() -> None:
    cards = [{"kind": "explanation", "title": f"Carte {i}"} for i in range(1, 26)]
    lines = curriculum_render.reprise(cards, "fr").splitlines()  # type: ignore[union-attr]
    assert lines[1] == "(et 5 carte(s) plus ancienne(s))"
    shown = [line for line in lines if line.startswith("- ")]
    assert len(shown) == curriculum_render.REPRISE_MAX_CARDS == 20
    assert shown[0] == "- explication : Carte 6" and shown[-1] == "- explication : Carte 25"


def _ctx(progress: Progress, cards: list[dict] | None):
    ctx = ctx_for(progress)
    if cards is not None:
        ctx.earlier_cards = lambda section_id: cards if section_id == "intro" else []
    return ctx


def test_start_section_ends_with_the_note() -> None:
    brief = curriculum_render.brief(curriculum(), curriculum().get("intro"), False, "fr")
    outcome = start_section(StartSectionArgs(section_id="intro"), _ctx(Progress(), CARDS))
    assert outcome.output == f"{brief}\n\n{curriculum_render.reprise(CARDS, 'fr')}"


def test_without_earlier_seances_the_output_is_byte_identical() -> None:
    brief = curriculum_render.brief(curriculum(), curriculum().get("intro"), False, "fr")
    for cards in (None, []):
        outcome = start_section(StartSectionArgs(section_id="intro"), _ctx(Progress(), cards))
        assert outcome.output == brief


def test_a_review_has_no_note() -> None:
    ctx = _ctx(Progress(done=frozenset({"intro"})), CARDS)
    outcome = start_section(StartSectionArgs(section_id="intro"), ctx)
    assert outcome.review is True and "Reprise" not in outcome.output
    assert "Reprise" not in replay_start(ToolEntry(kind="tool", name="start_section", arguments={"section_id": "intro"}), ctx)


def test_the_replay_says_the_note_again_byte_for_byte() -> None:
    live = start_section(StartSectionArgs(section_id="intro"), _ctx(Progress(), CARDS)).output
    # On a later turn the section is active: the replay sees the same closed séances.
    later = _ctx(Progress(active="intro"), CARDS)
    assert replay_start(ToolEntry(kind="tool", name="start_section", arguments={"section_id": "intro"}), later) == live
    replayed = registry.replay_output(ToolEntry(kind="tool", name="start_section", arguments={"section_id": "intro"}), later)
    assert replayed == {"ok": True, "result": live}
    assert json.loads(registry.encode_output(replayed))["result"].endswith("sans reprendre la section depuis le début.")
