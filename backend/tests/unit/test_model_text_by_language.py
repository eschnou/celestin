"""Spec 011 R5.3/R5.5: what the tools and the history tell the model, per course language.

French is pinned by the existing tests (`test_section_tools`, `test_registry`, `test_path`,
`test_history`); these cover the English rows and that the language is the ctx's.
"""

from __future__ import annotations

import json

import pytest

from app.api.schemas.chat import LearnerEntry, ToolEntry
from app.domain.errors import ToolValidationError
from app.domain.progress import Progress
from app.services import history, path
from app.services.tools import registry
from app.services.tools.context import SAVE_FAILED, TurnContext
from tests.fixtures.curricula import ctx_for, curriculum

CUR_EN = curriculum("valid_en.yaml")


def run(name: str, args: dict, ctx: TurnContext):
    return registry.execute(name, json.dumps(args), ctx)


def refusal(name: str, args: dict, ctx: TurnContext) -> str:
    with pytest.raises(ToolValidationError) as raised:
        run(name, args, ctx)
    return raised.value.message


# --- the locked path ------------------------------------------------------------


def test_path_refusals_in_english() -> None:
    assert path.can_start(CUR_EN, Progress(), "nope", "en") == (
        "Section “nope” does not exist. Sections of the chapter: intro, exos, bilan."
    )
    assert path.can_start(CUR_EN, Progress(), "exos", "en") == (
        "Section “2. Exercises” is not open yet. You can start “1. Introduction” (id: intro)."
    )
    assert path.can_complete(CUR_EN, Progress(), "intro", "en") == (
        "No section is in progress. Start one with start_section."
    )
    assert path.can_complete(CUR_EN, Progress(active="intro"), "exos", "en") == (
        "Only the current section can be finished: “1. Introduction” (id: intro)."
    )
    assert path.can_complete(CUR_EN, Progress(active="intro"), "intro", "en") is None


def test_path_refusals_are_french_by_default() -> None:
    assert path.can_start(CUR_EN, Progress(), "nope").startswith("La section « nope » n'existe pas.")


def test_the_refusal_a_tool_gives_follows_the_turns_language() -> None:
    # The French fixture curriculum has French titles; only the wording follows the language.
    assert "is not open yet" in refusal("start_section", {"section_id": "exos"}, ctx_for(language="en"))
    english = refusal("start_section", {"section_id": "exos"}, ctx_for(name="valid_en.yaml", language="en"))
    assert english.startswith("Section “2. Exercises” is not open yet.")
    french = refusal("start_section", {"section_id": "exos"}, ctx_for())
    assert french.startswith("La section « 2. Exercices » n'est pas encore ouverte.")


# --- section tools ----------------------------------------------------------------


def test_section_tool_outputs_follow_the_turns_language() -> None:
    ctx = ctx_for(name="valid_en.yaml", language="en")
    started = run("start_section", {"section_id": "intro"}, ctx)
    assert started.output.startswith("Section “1. Introduction” (lesson), 1/3.")
    done = run("complete_section", {"section_id": "intro", "summary": "Done."}, ctx)
    assert done.output == "Section finished. Next section: “2. Exercises” (practice), id: exos."


def test_the_markers_the_student_sees_do_not_follow_the_course_language() -> None:
    """Interface text: the catalog and the account's locale decide (spec 010)."""
    started = run("start_section", {"section_id": "intro"}, ctx_for(name="valid_en.yaml", language="en"))
    assert started.marker == "section commencée · 1. Introduction"


def test_a_replayed_start_is_the_brief_in_the_turns_language() -> None:
    ctx = ctx_for(name="valid_en.yaml", language="en")
    assert registry.replay_output("start_section", {"section_id": "intro"}, ctx)["result"].startswith(
        "Section “1. Introduction” (lesson)"
    )
    assert registry.replay_output("start_section", {"section_id": "zzz"}, ctx) == {
        "ok": True,
        "result": "Unknown section in the current path.",
    }
    assert registry.replay_output("complete_section", {"section_id": "zzz"}, ctx_for())["result"] == (
        "Section inconnue dans le parcours actuel."
    )


# --- pace, save, registry ---------------------------------------------------------


def test_propose_next_step_output() -> None:
    assert run("propose_next_step", {}, ctx_for(language="en")).output == (
        "“Next step” button enabled. End your turn and wait for the student to click or answer."
    )
    assert run("propose_next_step", {}, ctx_for()).output.startswith("Bouton « Étape suivante » activé.")


def test_a_failed_save_is_told_in_the_courses_language() -> None:
    def boom(_: Progress) -> None:
        raise RuntimeError("db down")

    for language in ("fr", "en"):
        ctx = TurnContext.from_progress(CUR_EN, [], None, save=boom, language=language)  # type: ignore[arg-type]
        assert refusal("start_section", {"section_id": "intro"}, ctx) == SAVE_FAILED[language]  # type: ignore[index]
    assert SAVE_FAILED["en"] == "I could not save your progress. Try again."


def test_registry_refusals_in_english() -> None:
    ctx = ctx_for(language="en")
    with pytest.raises(ToolValidationError, match=r"Invalid JSON arguments: "):
        registry.execute("start_section", "{nope", ctx)
    with pytest.raises(ToolValidationError, match="The arguments must be a JSON object."):
        registry.execute("start_section", "[1]", ctx)
    with pytest.raises(ToolValidationError, match=r"Invalid arguments\. \(root\)|Invalid arguments\. section_id"):
        registry.execute("start_section", "{}", ctx)
    with pytest.raises(ToolValidationError, match="The tool 'nope' is not available here. Available tools: "):
        registry.execute("nope", "{}", ctx)


def test_registry_refusals_in_french_are_unchanged() -> None:
    ctx = ctx_for()
    with pytest.raises(ToolValidationError, match="Arguments JSON invalides : "):
        registry.execute("start_section", "{nope", ctx)
    with pytest.raises(ToolValidationError, match="Les arguments doivent être un objet JSON."):
        registry.execute("start_section", "[1]", ctx)
    with pytest.raises(ToolValidationError, match=r"L'outil 'nope' n'est pas disponible ici\."):
        registry.execute("nope", "{}", ctx)


# --- history ----------------------------------------------------------------------


def _learner(text: str) -> LearnerEntry:
    return LearnerEntry(kind="learner", text=text)


def test_english_is_estimated_with_more_characters_per_token() -> None:
    entries = [_learner("a" * 3200)]
    assert history.estimate_tokens(entries) == 1000
    assert history.estimate_tokens(entries, "fr") == 1000
    assert history.estimate_tokens(entries, "en") == 800


def test_an_english_history_keeps_what_a_french_ratio_would_trim() -> None:
    entries = [_learner("a" * 3200), _learner("b" * 3200)]
    assert [e.text[0] for e in history.trim(entries, 1500)] == ["b"]  # 2000 tokens at 3.2
    assert [e.text[0] for e in history.trim(entries, 1700, "en")] == ["a", "b"]  # 1600 at 4.0


def test_the_history_is_trimmed_by_the_ctxs_language_and_replays_in_it() -> None:
    entries = [
        _learner("a" * 3200),
        ToolEntry(kind="tool", name="start_section", arguments={"section_id": "intro"}, ok=True),
        _learner("b" * 3200),
    ]
    kept = history.to_provider_input(entries, 1700, ctx_for(name="valid_en.yaml", language="en"))
    assert [i.get("content", "")[:1] for i in kept if i.get("role") == "user"] == ["a", "b"]
    output = next(i["output"] for i in kept if i.get("type") == "function_call_output")
    assert "Section “1. Introduction” (lesson)" in output
