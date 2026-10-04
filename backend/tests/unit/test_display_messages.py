"""Spec 010 R5.4, R5.5: the labels, titles, statuses and markers the server builds for the
student. The French is what the code said before the catalog existed
(`status_messages_fr.json`, `markers_fr.json`, recorded from the old code)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.routes.courses import authoring_message, display_title
from app.api.schemas.discussion import StoredEntry
from app.domain import board
from app.domain.board import CLEAR_MARKER, marker_for
from app.api.schemas.chat import ToolEntry
from app.domain.marker import Marker
from app.domain.messages import CATALOGS, render
from app.domain.subject import SUBJECTS
from app.services.tool_events import event_of
from app.services.tools.board import BoardCleared, BoardSet
from app.services.tools.pace import NextStepProposed
from app.services.tools.section import SectionCompleted, SectionStarted

FIXTURES = Path(__file__).parent.parent / "fixtures"
STATUS = json.loads((FIXTURES / "status_messages_fr.json").read_text("utf-8"))
MARKERS = json.loads((FIXTURES / "markers_fr.json").read_text("utf-8"))


# --- subjects, titles, failures --------------------------------------------------


@pytest.mark.parametrize("subject", sorted(SUBJECTS))
def test_subject_labels(subject: str) -> None:
    assert SUBJECTS[subject].label("fr") == STATUS["subjects"][subject]  # type: ignore[index]
    assert SUBJECTS[subject].label() == STATUS["subjects"][subject]  # type: ignore[index]
    assert SUBJECTS[subject].label("en") != SUBJECTS[subject].label("fr")  # type: ignore[index]


@pytest.mark.parametrize("case", STATUS["display_title"], ids=lambda c: repr(c["title"]))
def test_chapter_titles_keep_their_french(case: dict) -> None:
    assert display_title(case["position"], case["title"], "fr") == case["fr"]
    assert display_title(case["position"], case["title"]) == case["fr"]


def test_the_number_is_the_interfaces_and_the_title_the_courses() -> None:
    assert display_title(1, "Les suites numériques", "en") == "Chapter 1 — Les suites numériques"
    assert display_title(2, None, "en") == "New chapter 2"


def _chapter(error: str | None, needs_document: bool = False, state: str = "failed") -> SimpleNamespace:
    return SimpleNamespace(authoring_state=state, authoring_error=error, needs_document=needs_document)


@pytest.mark.parametrize("code", sorted(STATUS["authoring"]))
def test_authoring_failures_keep_their_french(code: str) -> None:
    assert authoring_message(_chapter(code), "fr") == STATUS["authoring"][code]  # type: ignore[arg-type]
    assert authoring_message(_chapter(code), "en") != STATUS["authoring"][code]  # type: ignore[arg-type]


@pytest.mark.parametrize("code", sorted(STATUS["transcription"]))
def test_transcription_failures_ask_for_the_document_again(code: str) -> None:
    chapter = _chapter(code, needs_document=True)
    assert authoring_message(chapter, "fr") == STATUS["transcription"][code]  # type: ignore[arg-type]
    assert "document" in authoring_message(chapter, "en").lower()  # type: ignore[arg-type]


def test_an_unknown_code_and_a_healthy_chapter() -> None:
    assert authoring_message(_chapter("never-heard-of-it"), "fr") == STATUS["authoring"]["internal"]  # type: ignore[arg-type]
    assert authoring_message(_chapter(None, state="ready")) is None  # type: ignore[arg-type]
    assert authoring_message(_chapter(None)) == STATUS["authoring"]["internal"]  # type: ignore[arg-type]


def test_every_code_has_both_languages() -> None:
    for catalog in CATALOGS.values():
        for code in STATUS["authoring"]:
            assert f"authoring.{code}" in catalog
        for code in STATUS["transcription"]:
            assert f"transcription.{code}" in catalog


# --- markers ----------------------------------------------------------------------


@pytest.mark.parametrize("row", MARKERS, ids=lambda r: r["key"])
def test_each_marker_renders_the_french_it_always_said(row: dict) -> None:
    assert render(row["key"], "fr", **row["params"]) == row["fr"]
    assert render(row["key"], "en", **row["params"]) != row["fr"]


def test_a_marker_is_its_french_string_and_remembers_how_to_say_it_otherwise() -> None:
    marker = Marker("marker.section_done", label="1. Introduction")
    assert marker == "section terminée · 1. Introduction"
    assert isinstance(marker, str) and marker.key == "marker.section_done"
    assert marker.render("en") == "section completed · 1. Introduction"
    assert marker.render() == marker


CARDS = [
    (board.TitleCard, "marker.title"),
    (board.ExplanationCard, "marker.explanation"),
    (board.WorkedExampleCard, "marker.worked_example"),
    (board.ExerciseCard, "marker.exercise"),
    (board.CheckQuestionCard, "marker.check_question"),
    (board.RecapCard, "marker.recap"),
]


@pytest.mark.parametrize(("card", "key"), CARDS)
def test_every_card_kind_has_its_marker_in_both_languages(card: type, key: str) -> None:
    assert card.marker.key == key
    assert card.marker.render("fr") == next(r["fr"] for r in MARKERS if r["key"] == key)
    assert card.marker.render("en") != card.marker.render("fr")


def test_every_card_kind_of_the_union_is_covered() -> None:
    from typing import get_args

    union = get_args(get_args(board.BoardCard)[0])
    assert {c for c, _ in CARDS} == set(union)


def test_the_event_of_an_outcome_carries_the_marker_in_the_requests_language() -> None:
    card = board.ExplanationCard(title="t", blocks=[board.TextBlock(text="x")])
    assert event_of(BoardSet(card=card, marker=card.marker)).marker == "explication affichée"
    assert event_of(BoardSet(card=card, marker=card.marker), "en").marker == "explanation shown"
    assert event_of(BoardCleared(marker=CLEAR_MARKER), "en").marker == "board cleared"
    assert event_of(NextStepProposed(marker=Marker("marker.step_ready")), "en").marker == "next step offered"
    section = SimpleNamespace(id="intro", label="1. Introduction")
    started = SectionStarted(section=section, review=False, output="o", marker=Marker("marker.section_started", label="1. Introduction"))  # type: ignore[arg-type]
    assert event_of(started, "fr").marker == "section commencée · 1. Introduction"
    assert event_of(started, "en").marker == "section started · 1. Introduction"
    done = SectionCompleted(section=section, next=None, summary="s", output="o", marker=Marker("marker.section_done", label="1. Introduction"))  # type: ignore[arg-type]
    assert event_of(done, "en").marker == "section completed · 1. Introduction"


def test_a_stored_call_is_marked_in_the_readers_language() -> None:
    card = {"kind": "exercise", "title": "t", "statement": "s"}
    assert marker_for("display_board", {"card": card}) == "exercice posé"
    assert marker_for("display_board", {"card": card}, "en") == "exercise set"
    assert marker_for("clear_board", {}, "en") == "board cleared"
    assert marker_for("display_board", {"card": {"kind": "nonsense"}}, "en") is None
    entry = ToolEntry(kind="tool", name="clear_board", arguments={})
    assert StoredEntry.of(entry).marker == "tableau effacé"
    assert StoredEntry.of(entry, "en").marker == "board cleared"


def test_a_marker_survives_copy_and_pickle() -> None:
    """A str subclass is rebuilt from its text by default, which would lose the key."""
    import copy
    import pickle

    marker = Marker("marker.section_done", label="1. Introduction")
    for clone in (copy.copy(marker), copy.deepcopy(marker), pickle.loads(pickle.dumps(marker))):
        assert clone == marker and clone.key == marker.key and dict(clone.params) == dict(marker.params)
        assert clone.render("en") == "section completed · 1. Introduction"
