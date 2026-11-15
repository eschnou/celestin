"""Spec 020: `record_result`, the révision's one tool — its declaration, its rules, its store, its replay and what a
stored call shows."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.api.schemas.chat import ToolEntry, stored_form
from app.api.schemas.events import RevisionResultEvent, to_sse
from app.config import get_settings
from app.domain.errors import ToolValidationError
from app.services.conversations import entries_from_events
from app.services.prompts import PromptLibrary
from app.services.tool_events import event_of
from app.services.tools import registry
from app.services.tools.context import StoredView, TurnContext
from scripts.chapter_files import load_revision
from tests.fixtures.curricula import ctx_for

PROMPTS = PromptLibrary(get_settings().prompts_dir)


def _ctx(language: str = "fr", **kwargs) -> TurnContext:
    scope = load_revision("mathematics", PROMPTS, language)  # type: ignore[arg-type]
    return TurnContext(mode="revision", revision=scope, pack=scope.packs, language=language, **kwargs)  # type: ignore[arg-type]


def _args(chapter: int = 1, section_id: str = "suites", outcome: str = "shaky") -> str:
    return json.dumps({"chapter": chapter, "section_id": section_id, "outcome": outcome})


# --- the declarations --------------------------------------------------------------------------------------


def test_the_revision_offers_the_board_pair_and_record_result_last() -> None:
    declared = registry.declarations("revision", "fr")
    assert [d["name"] for d in declared] == ["display_board", "clear_board", "record_result"]
    # The board pair is the very same declaration in every mode: its bytes do not move.
    assert declared[:2] == registry.declarations("parcours", "fr")[:2] == registry.declarations("discussion", "fr")
    record = declared[2]
    assert record["strict"] is True
    assert record["parameters"]["required"] == ["chapter", "section_id", "outcome"]
    assert record["parameters"]["properties"]["outcome"]["enum"] == ["solid", "shaky", "todo"]
    assert record["parameters"]["additionalProperties"] is False


def test_no_other_mode_offers_record_result() -> None:
    assert "record_result" not in registry.offered("parcours")
    assert "record_result" not in registry.offered("discussion")
    for mode in ("parcours", "discussion"):
        assert "record_result" not in [d["name"] for d in registry.declarations(mode, "fr")]  # type: ignore[arg-type]
        with pytest.raises(ToolValidationError, match="n'est pas disponible ici"):
            registry.execute("record_result", _args(), ctx_for(mode=mode))


def test_a_revision_refuses_the_section_tools() -> None:
    for name in ("start_section", "complete_section", "skip_section", "propose_next_step"):
        with pytest.raises(ToolValidationError, match="n'est pas disponible ici"):
            registry.execute(name, json.dumps({"section_id": "suites"}), _ctx())


# --- the rules -----------------------------------------------------------------------------------------------


def test_a_result_is_adopted_in_memory_without_a_store_and_answers_the_tally() -> None:
    ctx = _ctx()
    outcome = registry.execute("record_result", _args(1, "suites", "shaky"), ctx)
    assert ctx.noted == {("suites", "suites"): "shaky"}
    assert outcome.output == "Bilan noté. Cette révision : 0 acquis, 1 fragile(s), 0 à revoir (1 section(s) notée(s))."
    assert str(outcome.marker) == "noté : fragile · 1. Suites numériques"
    registry.execute("record_result", _args(2, "graphiques", "solid"), ctx)
    third = registry.execute("record_result", _args(1, "suites", "solid"), ctx)  # the latest per section counts
    assert third.output.endswith("2 acquis, 0 fragile(s), 0 à revoir (2 section(s) notée(s)).")


def test_a_result_is_noted_in_the_turns_memory_only() -> None:
    """D6 (amended): the tool writes nothing; the controller writes a turn's results with its transcript when the
    turn ends. A context has no store to bind."""
    ctx = _ctx()
    assert not hasattr(ctx, "record")
    registry.execute("record_result", _args(2, "pratique", "todo"), ctx)
    assert ctx.noted == {("statistique", "pratique"): "todo"}


@pytest.mark.parametrize(
    ("language", "chapter", "section", "message"),
    [
        ("fr", 3, "suites", "Le chapitre 3 ne fait pas partie de cette révision. Chapitres de la révision : 1, 2."),
        ("en", 3, "sequences", "Chapter 3 is not part of this revision. Chapters in the revision: 1, 2."),
        ("nl", 3, "rijen", "Hoofdstuk 3 hoort niet bij deze herhaling. Hoofdstukken van de herhaling: 1, 2."),
        ("fr", 2, "suites", "La section « suites » n'est pas dans le chapitre 2. Sections de ce chapitre : vocabulaire, graphiques, parametres, pratique."),
        ("en", 1, "nope", "The section “nope” is not in chapter 1. Sections of this chapter: sequences, geometric, practice, summary."),
        ("nl", 1, "nope", "De sectie “nope” zit niet in hoofdstuk 1. Secties van dit hoofdstuk: rijen, meetkundig, oefeningen, samenvatting."),
    ],
)
def test_a_result_outside_the_revision_is_refused_in_the_course_language(language, chapter, section, message) -> None:
    ctx = _ctx(language)
    with pytest.raises(ToolValidationError) as raised:
        registry.execute("record_result", _args(chapter, section), ctx)
    assert raised.value.message == message
    assert ctx.noted == {}


@pytest.mark.parametrize(
    "arguments",
    [
        {"chapter": 1, "section_id": "suites", "outcome": "parfait"},
        {"chapter": 0, "section_id": "suites", "outcome": "solid"},
        {"chapter": 1, "section_id": "", "outcome": "solid"},
        {"chapter": 1, "section_id": "suites"},
        {"chapter": 1, "section_id": "suites", "outcome": "solid", "comment": "bof"},
    ],
)
def test_invalid_arguments_are_refused(arguments) -> None:
    with pytest.raises(ToolValidationError, match="Arguments invalides"):
        registry.execute("record_result", json.dumps(arguments), _ctx())


def test_a_context_is_checked_when_it_is_built() -> None:
    """A révision context without its scope, or a chapter context without its path, fails where it is built, never
    later inside a tool (where an AssertionError would end the stream instead of being a tool error)."""
    scope = _ctx().scope
    with pytest.raises(ValueError, match="révision"):
        TurnContext(mode="revision")
    with pytest.raises(ValueError, match="révision"):
        TurnContext(mode="revision", revision=scope, curriculum=scope.chapters[0].curriculum)
    for mode in ("parcours", "discussion"):
        with pytest.raises(ValueError, match="chapter's path"):
            TurnContext(mode=mode)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="chapter's path"):
            TurnContext(mode=mode, curriculum=scope.chapters[0].curriculum, revision=scope)  # type: ignore[arg-type]
    chapter, revision = ctx_for(), _ctx()
    assert chapter.chapter_path is chapter.curriculum and revision.scope is revision.revision


# --- the event, the stored entry, the replay ---------------------------------------------------------------


def _live(ctx: TurnContext, *args: object):
    outcome = registry.execute("record_result", _args(*args), ctx)  # type: ignore[arg-type]
    return outcome, event_of(outcome, "fr")


def test_the_event_carries_its_wire_fields_only() -> None:
    _, event = _live(_ctx(), 2, "graphiques", "shaky")
    assert isinstance(event, RevisionResultEvent)
    assert to_sse(event) == (
        'event: revision.result\ndata: {"chapter_id":"statistique","section_id":"graphiques","outcome":"shaky",'
        '"marker":"noté : fragile · 2. Représenter une série"}\n\n'
    )
    assert event_of(registry.execute("record_result", _args(2, "graphiques", "todo"), _ctx()), "nl").marker == (
        "genoteerd: te herhalen · 2. Représenter une série"
    )


def test_the_stored_entry_records_the_chapter_and_the_tally() -> None:
    _, event = _live(_ctx(), 2, "graphiques", "shaky")
    (entry,) = entries_from_events([event])
    assert stored_form(entry) == {
        "kind": "tool",
        "name": "record_result",
        "arguments": {"chapter": 2, "section_id": "graphiques", "outcome": "shaky"},
        "ok": True,
        "error": None,
        "chapter_id": "statistique",
        "tally": {"solid": 0, "shaky": 1, "todo": 0},
    }


def test_other_entries_keep_their_bytes() -> None:
    board = ToolEntry(kind="tool", name="display_board", arguments={"card": {"kind": "recap"}})
    assert stored_form(board) == {"kind": "tool", "name": "display_board", "arguments": {"card": {"kind": "recap"}}, "ok": True, "error": None}


def test_only_a_record_result_entry_records_a_chapter_or_a_tally() -> None:
    with pytest.raises(ValidationError):
        ToolEntry(kind="tool", name="display_board", arguments={}, tally={"solid": 1})
    with pytest.raises(ValidationError):
        ToolEntry(kind="tool", name="start_section", arguments={}, chapter_id="a" * 32)


def test_a_replay_answers_what_the_call_answered_whatever_was_noted_since() -> None:
    ctx = _ctx()
    first, event = _live(ctx, 1, "suites", "shaky")
    (entry,) = entries_from_events([event])
    registry.execute("record_result", _args(1, "suites", "solid"), ctx)
    registry.execute("record_result", _args(2, "pratique", "todo"), ctx)
    later = _ctx()  # a later turn's context: other results noted since
    later.noted = {("suites", "suites"): "solid", ("statistique", "pratique"): "todo"}
    assert registry.replay_output(entry, later) == {"ok": True, "result": first.output}


def test_a_section_tool_entry_replays_as_a_bare_success_in_a_revision() -> None:
    """A révision has no chapter path to replay a brief from; it never stores such a call either."""
    entry = ToolEntry(kind="tool", name="start_section", arguments={"section_id": "suites"})
    assert registry.replay_output(entry, _ctx()) == {"ok": True}


def test_a_stored_call_shows_its_marker_and_what_it_noted() -> None:
    _, event = _live(_ctx(), 2, "graphiques", "solid")
    (entry,) = entries_from_events([event])
    scope = load_revision("mathematics", PROMPTS, "fr")
    view = StoredView(chapters={c.id: c.curriculum for c in scope.chapters})
    shown = registry.shown(entry, "revision", view)
    assert shown.marker is not None and shown.marker.render("en") == "noted: solid · 2. Représenter une série"
    assert dict(shown.fields) == {"chapter_id": "statistique", "section_id": "graphiques", "outcome": "solid"}
    # A chapter no longer known shows the section's id; another mode shows nothing.
    assert registry.shown(entry, "revision", StoredView()).marker == "noté : acquis · graphiques"
    assert registry.shown(entry, "discussion", view).marker is None


# --- the board in a révision reads the chosen packs ------------------------------------------------------------


def _definition(term: str, text: str) -> str:
    card = {"kind": "explanation", "title": "Rappel", "blocks": [{"type": "definition", "entries": [{"term": term, "text": text}]}]}
    return json.dumps({"card": card})


def test_a_definition_on_the_board_may_quote_any_chosen_pack_and_no_other_text() -> None:
    from dataclasses import replace

    from app.services.tools.board import BoardSet

    ctx = _ctx()
    # Chapter 2's pack (statistics), in a révision that also holds chapter 1.
    quoted = _definition("échantillon", "Un échantillon est un sous-ensemble de la population.")
    assert isinstance(registry.execute("display_board", quoted, ctx), BoardSet)
    reworded = _definition("échantillon", "Un échantillon est une petite partie de la population.")
    with pytest.raises(ToolValidationError, match="« échantillon »"):
        registry.execute("display_board", reworded, ctx)
    # A révision of chapter 1 alone does not know chapter 2's definition.
    alone = replace(ctx.revision, chapters=ctx.revision.chapters[:1])  # type: ignore[union-attr, arg-type]
    with pytest.raises(ToolValidationError, match="« échantillon »"):
        registry.execute("display_board", quoted, TurnContext(mode="revision", revision=alone, pack=alone.packs))
