from __future__ import annotations

from app.api.schemas.chat import LearnerEntry, ToolEntry, TutorEntry
from app.services import history
from tests.fixtures.curricula import ctx_for

BIG = 10_000
CTX = ctx_for()


def learner(text: str = "question") -> LearnerEntry:
    return LearnerEntry(kind="learner", text=text)


def tutor(text: str = "réponse") -> TutorEntry:
    return TutorEntry(kind="tutor", text=text)


def tool(ok: bool = True) -> ToolEntry:
    return ToolEntry(kind="tool", name="clear_board", arguments={}, ok=ok, error=None if ok else "boom")


def test_role_mapping() -> None:
    items = history.to_provider_input([learner("salut"), tutor("bonjour")], BIG, CTX)
    assert items[0] == {"role": "user", "content": "salut"}
    assert items[1] == {"role": "assistant", "content": "bonjour"}


def test_tool_entry_produces_call_and_output() -> None:
    items = history.to_provider_input([learner(), tool()], BIG, CTX)
    call, output = items[1], items[2]
    assert call["type"] == "function_call"
    assert output["type"] == "function_call_output"
    assert call["call_id"] == output["call_id"]


def test_function_call_never_emitted_without_output() -> None:
    entries = [learner(), tool(), tutor(), learner(), tool()]
    items = history.to_provider_input(entries, BIG, CTX)
    calls = [i for i in items if i.get("type") == "function_call"]
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert len(calls) == len(outputs) == 2
    assert {c["call_id"] for c in calls} == {o["call_id"] for o in outputs}


def test_failed_tool_reports_the_error_back_to_the_model() -> None:
    items = history.to_provider_input([tool(ok=False)], BIG, CTX)
    assert '"ok": false' in items[1]["output"]
    assert "boom" in items[1]["output"]


def test_empty_tutor_text_is_skipped() -> None:
    assert history.to_provider_input([tutor("")], BIG, CTX) == []


def test_trimming_drops_oldest_first() -> None:
    entries = [learner("a" * 3200), learner("b" * 3200), learner("c" * 3200)]
    kept = history.trim(entries, token_budget=1500)
    assert [e.text[0] for e in kept] == ["c"]


def test_trimming_never_separates_a_tool_from_its_turn() -> None:
    entries = [learner("a" * 3200), tool(), learner("b" * 3200), tool(), tutor("x")]
    kept = history.trim(entries, token_budget=1500)
    assert kept[0].kind == "learner" and kept[0].text.startswith("b")
    assert [e.kind for e in kept] == ["learner", "tool", "tutor"]


def test_most_recent_turn_always_survives() -> None:
    entries = [learner("a" * 4000), learner("b" * 4000)]
    kept = history.trim(entries, token_budget=1)
    assert len(kept) == 1 and kept[0].text.startswith("b")


def test_opening_turn_entries_group_together() -> None:
    entries = [tutor("bonjour"), tool(), learner("ok")]
    turns = history._split_turns(entries)
    assert [len(t) for t in turns] == [2, 1]


def test_nothing_trimmed_under_budget() -> None:
    entries = [learner("court"), tutor("aussi")]
    assert history.trim(entries, BIG) == entries


def test_replayed_section_start_carries_its_brief() -> None:
    entry = ToolEntry(kind="tool", name="start_section", arguments={"section_id": "intro"}, ok=True)
    items = history.to_provider_input([entry], BIG, CTX)
    assert "Déroulé" in items[1]["output"]
    assert "Citer la définition" in items[1]["output"]


def test_replayed_failed_section_start_keeps_its_refusal() -> None:
    entry = ToolEntry(
        kind="tool", name="start_section", arguments={"section_id": "bilan"}, ok=False, error="fermée"
    )
    items = history.to_provider_input([entry], BIG, CTX)
    assert '"ok": false' in items[1]["output"]
    assert "fermée" in items[1]["output"]
