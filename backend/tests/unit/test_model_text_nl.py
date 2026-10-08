"""Spec 017 R4.5, R5: what the code builds for the model in a Dutch course, beside the French and English pins.

`test_model_text_by_language.py` pins the English rows; French is pinned by the original tests. These cover the
Dutch rows of the same tables: the locked path, the tools' words, the history estimate, the authoring words, the
declarations, and that a Dutch course is read as Dutch whichever interface language the account has.
"""

from __future__ import annotations

import json

import pytest

from app.api.schemas.chat import LearnerEntry, ToolEntry
from app.domain.errors import ToolValidationError
from app.domain.messages.issues import issue_text
from app.domain.pack import ContentIssue, chapter_title
from app.domain.progress import Progress
from app.services import history, path
from app.services.authoring.agent import _repair_message
from app.services.authoring.words import AGENT_WORDS
from app.services.tools import registry
from app.services.tools.context import SAVE_FAILED, TurnContext
from tests.fixtures.curricula import ctx_for, curriculum

CUR = curriculum("valid_nl.yaml")


def run(name: str, args: dict, ctx: TurnContext):
    return registry.execute(name, json.dumps(args), ctx)


def refusal(name: str, args: dict, ctx: TurnContext) -> str:
    with pytest.raises(ToolValidationError) as raised:
        run(name, args, ctx)
    return raised.value.message


def test_path_refusals_in_dutch() -> None:
    assert path.can_start(CUR, Progress(), "nope", "nl") == (
        "Sectie “nope” bestaat niet. Secties van het hoofdstuk: intro, exos, bilan."
    )
    assert path.can_start(CUR, Progress(), "exos", "nl") == (
        "Sectie “2. Oefeningen” is nog niet open. Je kunt “1. Inleiding” beginnen (id: intro)."
    )
    assert path.can_complete(CUR, Progress(), "intro", "nl") == "Geen sectie is bezig. Begin er een met start_section."
    assert path.can_complete(CUR, Progress(active="intro"), "exos", "nl") == (
        "Alleen de huidige sectie kan worden afgerond: “1. Inleiding” (id: intro)."
    )
    assert path.can_complete(CUR, Progress(active="intro"), "intro", "nl") is None


def test_the_sections_tools_refuse_in_the_courses_language() -> None:
    ctx = ctx_for(name="valid_nl.yaml", language="nl")
    assert "bestaat niet" in refusal("start_section", {"section_id": "nope"}, ctx)
    assert "nog niet open" in refusal("start_section", {"section_id": "exos"}, ctx)
    brief = run("start_section", {"section_id": "intro"}, ctx).output
    assert brief.startswith("Sectie “1. Inleiding” (les)")


def test_propose_next_step_output() -> None:
    assert run("propose_next_step", {}, ctx_for(language="nl")).output == (
        "Knop “Volgende stap” geactiveerd. Beëindig je beurt en wacht tot de leerling klikt of antwoordt."
    )


def test_a_failed_save_is_told_in_dutch() -> None:
    def boom(_: Progress) -> None:
        raise RuntimeError("db down")

    ctx = TurnContext.from_progress(CUR, [], None, save=boom, language="nl")  # type: ignore[arg-type]
    assert refusal("start_section", {"section_id": "intro"}, ctx) == SAVE_FAILED["nl"]
    assert SAVE_FAILED["nl"] == "Ik kon je voortgang niet opslaan. Probeer opnieuw."


def test_registry_refusals_in_dutch() -> None:
    ctx = ctx_for(language="nl")
    with pytest.raises(ToolValidationError, match=r"Ongeldige JSON-argumenten: "):
        registry.execute("start_section", "{nope", ctx)
    with pytest.raises(ToolValidationError, match="De argumenten moeten een JSON-object zijn."):
        registry.execute("start_section", "[1]", ctx)
    with pytest.raises(ToolValidationError, match=r"Ongeldige argumenten\. \(basis\)|Ongeldige argumenten\. section_id"):
        registry.execute("start_section", "{}", ctx)
    with pytest.raises(ToolValidationError, match="De tool 'nope' is hier niet beschikbaar. Beschikbare tools: "):
        registry.execute("nope", "{}", ctx)


def test_the_declarations_of_a_dutch_course_are_the_french_ones() -> None:
    """Spec 017 R5.4: no overlay until the Dutch probes say a description leaks."""
    for mode in ("parcours", "discussion"):
        assert registry.declarations(mode, "nl") == registry.declarations(mode, "fr")  # type: ignore[arg-type]
        assert registry.realtime_declarations(mode, "nl") == registry.realtime_declarations(mode, "fr")  # type: ignore[arg-type]
    assert registry.TOOL_TEXT["nl"] == {}


def test_history_estimates_dutch_between_french_and_english() -> None:
    entries = [LearnerEntry(kind="learner", text="x" * 340), ToolEntry(kind="tool", name="t", arguments={})]
    fr, nl, en = (history.estimate_tokens(entries, language) for language in ("fr", "nl", "en"))  # type: ignore[arg-type]
    assert fr > nl > en
    assert history.CHARS_PER_TOKEN["nl"] == 3.4


def test_the_repair_request_is_in_dutch() -> None:
    issues = [ContentIssue("§ 5", "section « ## 5. Vocabulaire » manquante", "pack.section_missing", {"number": 5, "text": "Woordenschat"})]
    request = _repair_message(AGENT_WORDS["nl"].the_document, issues, "nl")
    assert request.startswith("Het document volgt de regels niet:\n- § 5: sectie “## 5. Woordenschat” ontbreekt")
    assert request.endswith("Geef het volledige, verbeterde document terug.")
    path_request = _repair_message(AGENT_WORDS["nl"].the_path, issues[:0], "nl")
    assert path_request.endswith("Geef het volledige, verbeterde traject terug.")


def test_the_reason_a_dutch_course_reads_is_the_catalogs_dutch_sentence() -> None:
    coded = ContentIssue("§ 4.2", "titre manquant", "pack.title_missing", {})
    assert issue_text(coded, "nl") == "het document moet beginnen met een titel “# Titel van het hoofdstuk”"
    assert issue_text(coded, "fr") == "titre manquant"  # French is the message byte for byte
    assert issue_text(ContentIssue("x", "raw message"), "nl") == "raw message"  # an uncoded one stays as written


def test_a_curriculum_title_loses_the_dutch_numbering_words() -> None:
    from app.domain.curriculum import curriculum_from_json

    data = curriculum("valid_nl.yaml").model_dump(mode="json")
    data["title"] = "Les 3 – Minihoofdstuk"
    assert curriculum_from_json(data, "nl").title == "Minihoofdstuk"
    assert curriculum_from_json(data).title == "Les 3 – Minihoofdstuk"  # the French reading leaves it
    assert chapter_title("Hoofdstuk 3: Rijen", "nl") == "Rijen"
