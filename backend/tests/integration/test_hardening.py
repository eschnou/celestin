"""Phase 7: the failure paths and the caps."""

from __future__ import annotations

import json
import logging

from app.providers.base import Completed, TextDelta
from tests.conftest import CARD, LESSON, sse_frames as frames, tool_call as call
from tests.fixtures.fake_llm import FakeLLM


async def test_oversized_body_is_rejected_before_the_provider(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    client, _ = make_client(llm)
    async with client:
        r = await client.post(
            "/api/chat",
            json={**LESSON, "history": [{"kind": "learner", "text": "x" * 1_100_000}]},
        )
    assert r.status_code == 413
    assert r.json()["code"] == "payload_too_large"
    assert llm.rounds_used == 0


async def test_too_many_entries_is_rejected_before_the_provider(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    client, _ = make_client(llm)
    async with client:
        r = await client.post(
            "/api/chat",
            json={**LESSON, "history": [{"kind": "learner", "text": "ok"}] * 500},
        )
    assert r.status_code in (413, 422)
    assert llm.rounds_used == 0


async def test_round_limit_ends_the_turn_cleanly(make_client, settings) -> None:
    settings.max_tool_rounds = 1
    llm = FakeLLM([[call("clear_board", {}), Completed()]])
    client, _ = make_client(llm)
    async with client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    got = frames(r.text)
    assert got[-1][0] == "turn.end"
    assert got[-1][1]["reason"] == "max_rounds"
    assert llm.rounds_used == 1


async def test_tool_self_correction_renders_the_corrected_board(make_client) -> None:
    bad = {"card": {"kind": "check_question", "question": "Q", "options": [], "correct_option_id": "a", "feedback": "f"}}
    llm = FakeLLM(
        [
            [call("display_board", bad), Completed()],
            [call("display_board", {"card": CARD}), Completed()],
            [TextDelta("voilà"), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    names = [n for n, _ in frames(r.text)]
    assert names.count("board.set") == 1
    assert "error" not in names
    outputs = [i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert json.loads(outputs[0]["output"])["ok"] is False


async def test_turn_log_carries_the_required_fields(make_client, caplog) -> None:
    llm = FakeLLM(
        [
            [TextDelta("a"), call("clear_board", {}), Completed()],
            [Completed(usage={"input_tokens": 5, "input_tokens_details": {"cached_tokens": 4}})],
        ]
    )
    client, _ = make_client(llm)
    with caplog.at_level(logging.INFO, logger="app.services.tutor_service"):
        async with client:
            await client.post("/api/chat", json={**LESSON, "history": []})

    matching = [r for r in caplog.records if r.message == "turn_complete"]
    assert matching, "no turn_complete log record was emitted"
    record = matching[0]
    for field in ("turn_id", "model", "rounds", "tools", "reason", "ttft_ms", "total_ms", "usage"):
        assert hasattr(record, field), field
    assert record.tools == ["clear_board:ok"]
    assert record.cached_tokens == 4
    assert "test-key" not in json.dumps(record.__dict__, default=str)


async def test_cors_denied_by_default(make_client) -> None:
    client, _ = make_client(FakeLLM([[Completed()]]))
    async with client:
        r = await client.get("/api/health", headers={"origin": "http://evil.test"})
    assert "access-control-allow-origin" not in r.headers


async def test_cors_allows_configured_origin(settings, db_engine) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    settings.cors_origins = ["http://localhost:8080"]
    app = create_app(settings, engine=db_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/health", headers={"origin": "http://localhost:8080"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:8080"
