from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.schemas.chat import ProgressDTO
from app.services.tools.context import TurnContext
from app.api.schemas.events import (
    BoardClearEvent,
    BoardSetEvent,
    ErrorEvent,
    SectionDoneEvent,
    SectionStartEvent,
    StepReadyEvent,
    TextDeltaEvent,
    TurnEnd,
    TurnStart,
)

from app.config import Settings
from app.domain.errors import ProviderRateLimited, ProviderUnavailable, TutorError
from app.providers.base import Completed, Failed, TextDelta, ToolCallRequested
from app.services.tutor_service import TutorService
from tests.fixtures.curricula import StubPrompts, lesson_chapter
from tests.fixtures.fake_llm import FakeLLM

CARD = {"kind": "explanation", "title": "T", "blocks": [{"type": "text", "text": "x"}]}


CHAPTER = lesson_chapter("# Course pack — Chapitre 1 : suites\n")
PROMPTS = StubPrompts(
    "prompt <!-- SUBJECT --> <!-- COURSE_PACK --> <!-- CURRICULUM -->"
    " <!-- MODE --> <!-- MODE_OPENING -->"
)


@pytest.fixture
def courses() -> None:
    """Kept as a fixture name so the tests read as before: the chapter is fixed."""
    return None


def build(llm: FakeLLM, courses: None = None, **overrides) -> TutorService:
    settings = Settings(openai_api_key="k", _env_file=None, **overrides)
    return TutorService(llm=llm, prompts=PROMPTS, settings=settings)  # type: ignore[arg-type]


def context(service: TutorService, progress: ProgressDTO | None = None, save=None) -> TurnContext:
    progress = progress or ProgressDTO()
    return TurnContext.from_progress(CHAPTER.curriculum, progress.done, progress.active, save=save)


async def drain(
    service: TutorService, entries: list | None = None, progress: ProgressDTO | None = None
) -> list:
    ctx = context(service, progress)
    items = service.build_input(CHAPTER, entries or [], ctx)
    return [event async for event in service.run_turn(items, ctx)]


def call(name: str, args: dict, call_id: str = "c1") -> ToolCallRequested:
    return ToolCallRequested(call_id=call_id, name=name, arguments_json=json.dumps(args))


async def test_text_only_turn(courses: None) -> None:
    llm = FakeLLM([[TextDelta("Salut "), TextDelta("!"), Completed(usage={"input_tokens": 5})]])
    events = await drain(build(llm, courses))
    assert isinstance(events[0], TurnStart)
    assert [e.text for e in events if isinstance(e, TextDeltaEvent)] == ["Salut ", "!"]
    assert events[-1] == TurnEnd(reason="end", usage={"input_tokens": 5})
    assert llm.rounds_used == 1


async def test_text_tool_text_ordering_and_block_ids(courses: None) -> None:
    llm = FakeLLM(
        [
            [TextDelta("avant"), call("display_board", {"card": CARD}), Completed()],
            [TextDelta("après"), Completed()],
        ]
    )
    events = await drain(build(llm, courses))
    kinds = [type(e).__name__ for e in events]
    assert kinds == ["TurnStart", "TextDeltaEvent", "BoardSetEvent", "TextDeltaEvent", "TurnEnd"]
    deltas = [e for e in events if isinstance(e, TextDeltaEvent)]
    assert (deltas[0].block_id, deltas[0].text) == (0, "avant")
    assert (deltas[1].block_id, deltas[1].text) == (1, "après")


async def test_board_set_carries_card_and_marker(courses: None) -> None:
    llm = FakeLLM([[call("display_board", {"card": CARD}), Completed()], [Completed()]])
    events = await drain(build(llm, courses))
    board = next(e for e in events if isinstance(e, BoardSetEvent))
    assert board.card.kind == "explanation"
    assert board.marker == "explication affichée"


async def test_clear_board(courses: None) -> None:
    llm = FakeLLM([[call("clear_board", {}), Completed()], [Completed()]])
    events = await drain(build(llm, courses))
    assert next(e for e in events if isinstance(e, BoardClearEvent)).marker == "tableau effacé"


async def test_two_tool_calls_in_one_round(courses: None) -> None:
    llm = FakeLLM(
        [
            [
                call("display_board", {"card": CARD}, "a"),
                call("clear_board", {}, "b"),
                Completed(),
            ],
            [Completed()],
        ]
    )
    events = await drain(build(llm, courses))
    assert [type(e).__name__ for e in events if "Board" in type(e).__name__] == [
        "BoardSetEvent",
        "BoardClearEvent",
    ]


async def test_invalid_arguments_then_corrected_retry(courses: None) -> None:
    llm = FakeLLM(
        [
            [call("display_board", {"card": {"kind": "explanation", "title": "T", "blocks": []}}), Completed()],
            [call("display_board", {"card": CARD}), Completed()],
            [TextDelta("voilà"), Completed()],
        ]
    )
    events = await drain(build(llm, courses))
    boards = [e for e in events if isinstance(e, BoardSetEvent)]
    assert len(boards) == 1, "the invalid call must not render a board"
    # The failure went back to the model as a tool result, not as an error event.
    assert not [e for e in events if isinstance(e, ErrorEvent)]
    outputs = [i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    reported = json.loads(outputs[0]["output"])
    assert reported["ok"] is False
    assert "blocks" in reported["error"]


async def test_unknown_tool_is_returned_to_the_model(courses: None) -> None:
    llm = FakeLLM([[call("teleport", {}), Completed()], [TextDelta("pardon"), Completed()]])
    events = await drain(build(llm, courses))
    assert not [e for e in events if isinstance(e, ErrorEvent)]
    assert "teleport" in json.dumps(llm.calls[1]["input"], ensure_ascii=False)


async def test_round_limit_exhausted(courses: None) -> None:
    rounds = [[call("clear_board", {}), Completed()] for _ in range(3)]
    llm = FakeLLM(rounds)
    events = await drain(build(llm, courses, max_tool_rounds=3))
    assert events[-1].reason == "max_rounds"
    assert llm.rounds_used == 3


async def test_provider_failure_mid_stream_raises_for_the_controller(courses: None) -> None:
    """The turn loop does not frame errors; design 5 puts that in the controller."""
    llm = FakeLLM([[TextDelta("début"), Failed(code="provider_unavailable", message="boom")]])
    with pytest.raises(ProviderUnavailable):
        await drain(build(llm, courses))


async def test_provider_failure_keeps_its_code(courses: None) -> None:
    llm = FakeLLM([[Failed(code="provider_rate_limited", message="slow down")]])
    with pytest.raises(ProviderRateLimited):
        await drain(build(llm, courses))


async def test_unrecognised_failure_code_falls_back(courses: None) -> None:
    llm = FakeLLM([[Failed(code="who_knows", message="?")]])
    with pytest.raises(TutorError):
        await drain(build(llm, courses))


async def test_assistant_text_is_replayed_into_the_next_round(courses: None) -> None:
    llm = FakeLLM([[TextDelta("je note"), call("clear_board", {}), Completed()], [Completed()]])
    await drain(build(llm, courses))
    assert {"role": "assistant", "content": "je note"} in llm.calls[1]["input"]


async def test_every_function_call_gets_an_output(courses: None) -> None:
    llm = FakeLLM([[call("clear_board", {}), Completed()], [Completed()]])
    await drain(build(llm, courses))
    items = llm.calls[1]["input"]
    calls = [i for i in items if i.get("type") == "function_call"]
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert len(calls) == len(outputs) == 1


async def test_prompt_prefix_is_sent_on_every_round(courses: None) -> None:
    llm = FakeLLM([[call("clear_board", {}), Completed()], [Completed()]])
    await drain(build(llm, courses))
    for record in llm.calls:
        first = record["input"][0]
        assert first["role"] == "developer"
        assert first["content"][0]["prompt_cache_breakpoint"] == {"mode": "explicit"}


async def test_tools_are_declared_on_every_round(courses: None) -> None:
    llm = FakeLLM([[Completed()]])
    await drain(build(llm, courses))
    assert [t["name"] for t in llm.tools] == [
        "display_board",
        "clear_board",
        "start_section",
        "complete_section",
        "propose_next_step",
    ]


async def test_propose_next_step_emits_step_ready(courses: None) -> None:
    llm = FakeLLM([[call("propose_next_step", {}), Completed()], [Completed()]])
    events = await drain(build(llm, courses))
    ready = next(e for e in events if isinstance(e, StepReadyEvent))
    assert ready.marker == "étape suivante proposée"
    outputs = [i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert "Étape suivante" in json.loads(outputs[0]["output"])["result"]


# --- section tools in the loop (002) ---------------------------------------


async def test_start_section_emits_event_and_brief(courses: None) -> None:
    llm = FakeLLM([[call("start_section", {"section_id": "intro"}), Completed()], [Completed()]])
    events = await drain(build(llm, courses))
    started = next(e for e in events if isinstance(e, SectionStartEvent))
    assert started.section_id == "intro"
    assert started.review is False
    assert started.marker == "section commencée · 1. Introduction"
    outputs = [i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    result = json.loads(outputs[0]["output"])
    assert result["ok"] is True
    assert "Déroulé" in result["result"]


async def test_locked_section_is_refused_without_event(courses: None) -> None:
    llm = FakeLLM([[call("start_section", {"section_id": "bilan"}), Completed()], [Completed()]])
    events = await drain(build(llm, courses))
    assert not [e for e in events if isinstance(e, SectionStartEvent)]
    outputs = [i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    result = json.loads(outputs[0]["output"])
    assert result["ok"] is False
    assert "intro" in result["error"]


async def test_complete_then_start_in_one_turn_sees_the_new_state(courses: None) -> None:
    llm = FakeLLM(
        [
            [
                call("complete_section", {"section_id": "intro", "summary": "fait"}, "a"),
                call("start_section", {"section_id": "exos"}, "b"),
                Completed(),
            ],
            [Completed()],
        ]
    )
    events = await drain(build(llm, courses), progress=ProgressDTO(done=[], active="intro"))
    kinds = [type(e).__name__ for e in events]
    assert kinds == ["TurnStart", "SectionDoneEvent", "SectionStartEvent", "TurnEnd"]
    done = next(e for e in events if isinstance(e, SectionDoneEvent))
    assert done.next_section_id == "exos"
    assert done.marker == "section terminée · 1. Introduction"


async def test_completing_a_non_active_section_is_refused(courses: None) -> None:
    llm = FakeLLM(
        [[call("complete_section", {"section_id": "exos", "summary": "x"}), Completed()], [Completed()]]
    )
    events = await drain(build(llm, courses), progress=ProgressDTO(done=[], active="intro"))
    assert not [e for e in events if isinstance(e, SectionDoneEvent)]


async def test_review_does_not_change_progress(courses: None) -> None:
    llm = FakeLLM([[call("start_section", {"section_id": "intro"}), Completed()], [Completed()]])
    service = build(llm, courses)
    ctx = context(service, ProgressDTO(done=["intro"], active="exos"))
    items = service.build_input(CHAPTER, [], ctx)
    events = [e async for e in service.run_turn(items, ctx)]
    started = next(e for e in events if isinstance(e, SectionStartEvent))
    assert started.review is True
    assert ctx.progress.active == "exos"


async def test_max_rounds_leaves_progress_untouched(courses: None) -> None:
    llm = FakeLLM([[call("clear_board", {}), Completed()]])
    service = build(llm, courses, max_tool_rounds=1)
    ctx = context(service)
    items = service.build_input(CHAPTER, [], ctx)
    events = [e async for e in service.run_turn(items, ctx)]
    assert events[-1].reason == "max_rounds"
    assert ctx.progress.active is None and not ctx.progress.done


def test_inconsistent_progress_is_repaired_before_the_stream(courses: None) -> None:
    service = build(FakeLLM([]), courses)
    ctx = context(service, ProgressDTO(done=["intro"], active="intro"))
    assert ctx.progress.active is None and ctx.progress.done == frozenset({"intro"})
    ctx = context(service, ProgressDTO(done=[], active="nope"))
    assert ctx.progress.active is None


def test_unknown_done_ids_are_dropped(courses: None) -> None:
    ctx = context(build(FakeLLM([]), courses), ProgressDTO(done=["intro", "ghost"]))
    assert ctx.progress.done == frozenset({"intro"})


# --- the usage ledger (spec 015 R1.7, R2) ----------------------------------------


class _Sink:
    def __init__(self) -> None:
        self.entries: list = []

    def record(self, entry) -> None:  # noqa: ANN001
        self.entries.append(entry)


def recorded(rounds: list, sink: _Sink) -> TutorService:
    from app.providers.recording import RecordingLLM

    return build(RecordingLLM(FakeLLM(rounds), model="tutor-m", host="api.test", sink=sink))  # type: ignore[arg-type]


async def drain_for(service: TutorService, user_id: str | None, mode: str = "parcours") -> list:
    ctx = TurnContext.from_progress(
        CHAPTER.curriculum, [], None, user_id=user_id, chapter_id="ch1", course_id="c1", mode=mode  # type: ignore[arg-type]
    )
    items = service.build_input(CHAPTER, [], ctx)
    return [event async for event in service.run_turn(items, ctx)]


async def test_a_turn_with_tool_rounds_is_summed_and_every_round_is_a_row() -> None:
    usage = lambda n, cost=None: {"input_tokens": n, "output_tokens": 1, **({"cost": cost} if cost else {})}  # noqa: E731
    sink = _Sink()
    service = recorded(
        [
            [call("display_board", {"card": CARD}), Completed(usage=usage(100, 0.25))],
            [call("display_board", {"card": CARD}, "c2"), Completed(usage=usage(110, 0.25))],
            [TextDelta("fin"), Completed(usage=usage(120))],
        ],
        sink,
    )
    events = await drain_for(service, "u1")
    end = events[-1]
    # The tokens of every round; the provider's cost is the administrator's (the ledger), not the student's.
    assert isinstance(end, TurnEnd) and end.usage == {"input_tokens": 330, "output_tokens": 3}
    assert [(e.user_id, e.course_id, e.chapter_id, e.feature, e.role, e.model) for e in sink.entries] == [
        ("u1", "c1", "ch1", "tutor_turn", "tutor", "tutor-m")
    ] * 3
    assert [e.input_tokens for e in sink.entries] == [100, 110, 120]
    turn_id = events[0].turn_id  # type: ignore[union-attr]
    assert {e.correlation_id for e in sink.entries} == {turn_id}


async def test_a_discussion_turn_has_its_own_feature() -> None:
    sink = _Sink()
    await drain_for(recorded([[TextDelta("x"), Completed()]], sink), "u1", mode="discussion")
    assert [e.feature for e in sink.entries] == ["discussion_turn"]


async def test_a_context_without_a_user_records_nothing() -> None:
    sink = _Sink()
    await drain_for(recorded([[TextDelta("x"), Completed()]], sink), None)
    assert sink.entries == []


async def test_a_turn_abandoned_midway_leaves_a_cancelled_row_and_closes_the_scope() -> None:
    from app.domain.usage import current_scope

    sink = _Sink()
    service = recorded([[TextDelta("a"), TextDelta("b"), Completed(usage={"input_tokens": 9})]], sink)
    ctx = TurnContext.from_progress(CHAPTER.curriculum, [], None, user_id="u1", chapter_id="ch1", course_id="c1")
    turn = service.run_turn(service.build_input(CHAPTER, [], ctx), ctx)
    async for event in turn:
        if isinstance(event, TextDeltaEvent):
            break
    await turn.aclose()
    assert [(e.status, e.input_tokens) for e in sink.entries] == [("cancelled", None)]
    assert current_scope() is None


async def test_a_failing_provider_round_is_a_failed_row_and_the_usual_error() -> None:
    sink = _Sink()
    service = recorded([[Failed(code="provider_rate_limited", message="PROVIDER TEXT")]], sink)
    with pytest.raises(ProviderRateLimited):
        await drain_for(service, "u1")
    assert [(e.status, e.error_code) for e in sink.entries] == [("failed", "provider_rate_limited")]
