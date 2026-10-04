from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from tests.fixtures.fake_clients import FixedAiConfig
from app.services.ai_settings import load_ai_config
from app.api.schemas.chat import LearnerEntry, ProgressDTO, ToolEntry, TutorEntry
from app.config import Settings
from app.domain.progress import Progress
from app.services.tool_events import event_of
from app.services.tools import registry
from app.services.voice_service import VoiceService
from tests.fixtures.curricula import HERE, StubPrompts, ctx_for, lesson_chapter
from tests.fixtures.fake_realtime import FakeRealtime

CARD = {"kind": "explanation", "title": "T", "blocks": [{"type": "text", "text": "x"}]}
NOW = datetime(2026, 9, 11, 10, 5)


def _ctx(progress: ProgressDTO | None = None, save=None):
    progress = progress or ProgressDTO()
    from app.services.tools.context import TurnContext

    return TurnContext.from_progress(ctx_for().curriculum, progress.done, progress.active, save=save)


PROMPT = (
    "Célestin.\n<!-- VOICE -->\nÀ voix haute.\n<!-- /VOICE -->\n\n"
    "<!-- SUBJECT -->\n<!-- COURSE_PACK -->\n<!-- CURRICULUM -->\n<!-- MODE -->\n<!-- MODE_OPENING -->\n"
)
CH = lesson_chapter()


def _service(**overrides: Any) -> tuple[VoiceService, FakeRealtime]:
    settings = Settings(openai_api_key="k", _env_file=None, **overrides)
    realtime = FakeRealtime()
    return VoiceService(realtime, StubPrompts(PROMPT), settings, FixedAiConfig(load_ai_config(settings))), realtime  # type: ignore[arg-type]


def test_session_config_shape() -> None:
    service, _ = _service()
    config = service.session_config(CH)
    assert config["type"] == "realtime" and config["model"] == "gpt-realtime-2.1"
    assert "# Pack" in config["instructions"] and "À voix haute." in config["instructions"]
    assert config["tools"] == registry.realtime_declarations()
    assert config["parallel_tool_calls"] is False
    assert config["output_modalities"] == ["audio"]
    assert config["audio"]["input"]["transcription"] == {"model": "gpt-4o-mini-transcribe", "language": "fr"}
    assert config["audio"]["input"]["turn_detection"]["type"] == "semantic_vad"
    assert "format" not in config["audio"]["input"] and "format" not in config["audio"]["output"]
    assert config["audio"]["output"] == {"voice": "marin", "speed": 1.0}
    assert config["reasoning"] == {"effort": "low"}
    assert config["tracing"] is None and config["truncation"] == "auto"


def test_session_config_is_byte_stable() -> None:
    service, _ = _service()
    a = json.dumps(service.session_config(CH), sort_keys=True)
    b = json.dumps(service.session_config(CH), sort_keys=True)
    assert a == b


def test_reasoning_omitted_when_blank() -> None:
    service, _ = _service(voice_reasoning_effort="")
    assert "reasoning" not in service.session_config(CH)


def test_seed_maps_every_entry_kind() -> None:
    service, _ = _service()
    entries = [
        LearnerEntry(kind="learner", text="Bonjour"),
        TutorEntry(kind="tutor", text="Salut"),
        ToolEntry(kind="tool", name="display_board", arguments={"card": CARD}, ok=True),
        ToolEntry(kind="tool", name="start_section", arguments={"section_id": "nope"}, ok=False, error="refusé"),
    ]
    items = service.seed(entries, _ctx(), now=NOW)
    assert items[0] == {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Bonjour"}]}
    assert items[1] == {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Salut"}]}
    assert items[2]["type"] == "function_call" and items[2]["name"] == "display_board"
    assert items[3]["type"] == "function_call_output" and json.loads(items[3]["output"]) == {"ok": True}
    assert json.loads(items[5]["output"]) == {"ok": False, "error": "refusé"}
    last = items[-1]
    assert last["role"] == "system" and "État du parcours" in last["content"][0]["text"]
    assert "vendredi 11 septembre" in last["content"][0]["text"]


def test_seed_trims_oldest_turns_to_budget() -> None:
    service, _ = _service(voice_seed_token_budget=50)
    entries = []
    for i in range(6):
        entries.append(LearnerEntry(kind="learner", text=f"question {i} " + "x" * 100))
        entries.append(TutorEntry(kind="tutor", text=f"réponse {i}"))
    items = service.seed(entries, _ctx(), now=NOW)
    texts = [i["content"][0]["text"] for i in items if i.get("role") == "user"]
    assert texts and texts[-1].startswith("question 5")
    assert len(texts) < 6


def test_seed_state_reflects_progress() -> None:
    service, _ = _service()
    items = service.seed([], _ctx(ProgressDTO(done=["intro"])), now=NOW)
    assert "1 section(s) faite(s)" in items[-1]["content"][0]["text"]


async def test_create_session_hands_config_and_ttl_to_the_provider() -> None:
    service, realtime = _service(voice_secret_ttl_s=45)
    res = await service.create_session(CH, [], _ctx())
    assert res.secret == "ek_test_secret" and res.expires_at == 1_800_000_000
    assert res.opening is True and res.model == "gpt-realtime-2.1" and res.voice == "marin"
    assert res.limits.max_session_s == 1500 and res.limits.idle_s == 180
    assert len(res.seed) == 1 and res.seed[0]["role"] == "system"
    assert realtime.ttls == [45]
    assert realtime.sessions[0]["instructions"] == service.session_config(CH)["instructions"]
    assert len(res.session_id) == 12


async def test_create_session_opening_false_with_history() -> None:
    service, _ = _service()
    res = await service.create_session(CH, [LearnerEntry(kind="learner", text="hi")], _ctx())
    assert res.opening is False and len(res.seed) == 2


@pytest.mark.parametrize(
    ("name", "arguments", "progress"),
    [
        ("display_board", json.dumps({"card": CARD}), ProgressDTO()),
        ("clear_board", "{}", ProgressDTO()),
        ("start_section", '{"section_id":"intro"}', ProgressDTO()),
        ("complete_section", '{"section_id":"intro","summary":"fait"}', ProgressDTO(active="intro")),
        ("propose_next_step", "{}", ProgressDTO()),
    ],
)
def test_execute_tool_matches_the_text_loop(name: str, arguments: str, progress: ProgressDTO) -> None:
    service, _ = _service()
    ctx = ctx_for(Progress(done=frozenset(progress.done), active=progress.active))
    expected = registry.execute(name, arguments, ctx)
    res = service.execute_tool(name, arguments, _ctx(progress))
    assert json.loads(res.output) == registry.output_of(expected)
    assert res.event == event_of(expected).model_dump(mode="json")
    assert res.progress == ProgressDTO(done=list(ctx.progress.done), active=ctx.progress.active)


def test_execute_section_tools_carry_state_text() -> None:
    service, _ = _service()
    started = service.execute_tool("start_section", '{"section_id":"intro"}', _ctx())
    assert started.state_text and "Section en cours" in started.state_text
    assert started.progress.active == "intro"
    done = service.execute_tool("complete_section", '{"section_id":"intro","summary":"ok"}', _ctx(ProgressDTO(active="intro")))
    assert done.progress.done == ["intro"] and done.progress.active is None
    assert done.state_text and "Aucune section en cours" in done.state_text
    assert service.execute_tool("clear_board", "{}", _ctx()).state_text is None


def test_execute_tool_refusal_and_unknown() -> None:
    service, _ = _service()
    refused = service.execute_tool("complete_section", '{"section_id":"intro","summary":"x"}', _ctx())
    assert refused.event is None and json.loads(refused.output)["ok"] is False
    assert refused.progress == ProgressDTO()
    unknown = service.execute_tool("teleport", "{}", _ctx())
    assert unknown.event is None and "teleport" in json.loads(unknown.output)["error"]
    malformed = service.execute_tool("display_board", "{nope", _ctx())
    assert malformed.event is None and "JSON" in json.loads(malformed.output)["error"]


def test_usage_cost_estimate(caplog: pytest.LogCaptureFixture) -> None:
    from app.api.schemas.voice import VoiceUsageReport, VoiceUsageTotals

    service, _ = _service()
    report = VoiceUsageReport(
        session_id="s", reason="learner", duration_s=60, responses=2,
        usage=VoiceUsageTotals(input_audio=1_000_000, cached_audio=0, output_audio=0),
    )
    with caplog.at_level("INFO"):
        service.log_usage(report, user_id="u1")
    record = next(r for r in caplog.records if r.getMessage() == "voice_usage")
    assert record.cost_estimate_usd == 32.0  # type: ignore[attr-defined]
    assert record.input_audio == 1_000_000  # type: ignore[attr-defined]


# --- spec 014: the voice role's model and connection ------------------------------------------


def test_the_session_follows_the_voice_roles_model_and_effort() -> None:
    service, _ = _service(voice_model="rt-custom", voice_transcription_model="stt-custom", voice_reasoning_effort="")
    config = service.session_config(CH)
    assert config["model"] == "rt-custom" and config["audio"]["input"]["transcription"]["model"] == "stt-custom"
    assert "reasoning" not in config  # an empty effort is not sent


async def test_the_session_response_carries_the_voice_servers_calls_url() -> None:
    from tests.fixtures.curricula import ctx_for

    service, realtime = _service()
    response = await service.create_session(CH, [], ctx_for())
    assert response.calls_url == "https://api.openai.com/v1/realtime/calls" and response.model == "gpt-realtime-2.1"
    own, _ = _service(voice_base_url="https://rt.example/v1", voice_api_key="k2")
    assert (await own.create_session(CH, [], ctx_for())).calls_url == "https://rt.example/v1/realtime/calls"


async def test_without_a_voice_connection_there_is_no_session() -> None:
    from app.domain.errors import VoiceDisabled
    from tests.fixtures.curricula import ctx_for

    service, realtime = _service(openai_base_url="https://api.groq.com/openai/v1", openai_model="m")  # not a Realtime server
    with pytest.raises(VoiceDisabled):
        await service.create_session(CH, [], ctx_for())
    assert realtime.sessions == []


def test_a_voice_session_on_another_provider_is_not_priced_with_openais_prices() -> None:
    from app.api.schemas.voice import VoiceUsageReport, VoiceUsageTotals

    report = VoiceUsageReport(
        session_id="s", reason="learner", duration_s=60, responses=2, usage=VoiceUsageTotals(input_audio=1_000_000)
    )
    service, _ = _service(voice_base_url="https://rt.example/v1", voice_api_key="k2")
    assert service.log_usage(report, user_id="u") == 0.0
    priced, _ = _service(voice_base_url="https://rt.example/v1", voice_api_key="k2", voice_price_audio_in=1.0)
    assert priced.log_usage(report, user_id="u") == 1.0
