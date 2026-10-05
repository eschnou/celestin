"""003 design 3.1: the three voice routes, offline."""

from __future__ import annotations

from tests.conftest import CHAPTER_ID, LESSON

import json

import pytest
from httpx import AsyncClient

from app.domain.errors import ProviderUnavailable
from tests.conftest import CARD
from tests.fixtures.fake_realtime import ExplodingRealtime, FakeRealtime

IDS = LESSON
EMPTY = {**IDS, "history": []}


async def test_session_shape_and_headers(make_voice_client, caplog: pytest.LogCaptureFixture) -> None:
    realtime = FakeRealtime()
    async with make_voice_client(realtime) as client:
        with caplog.at_level("INFO"):
            r = await client.post("/api/voice/session", json=EMPTY)
    assert r.status_code == 201
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["secret"] == "ek_test_secret"
    assert body["model"] == "gpt-realtime-2.1" and body["voice"] == "marin"
    assert body["calls_url"] == "https://api.openai.com/v1/realtime/calls"  # the browser holds no URL of its own
    assert body["limits"] == {"max_session_s": 1500, "idle_s": 180}
    assert body["opening"] is True
    assert body["seed"][-1]["role"] == "system"
    assert "instructions" not in body
    assert "ek_test_secret" not in caplog.text
    assert realtime.sessions[0]["tools"][0]["name"] == "display_board"


async def test_session_with_history_is_not_opening(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        r = await client.post(
            "/api/voice/session",
            json={**IDS, "history": [{"kind": "learner", "text": "Bonjour"}]},
        )
    assert r.status_code == 201
    assert r.json()["opening"] is False
    assert r.json()["seed"][0]["role"] == "user"


async def test_session_rate_limited(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime(), voice_sessions_per_hour=2) as client:
        assert (await client.post("/api/voice/session", json=EMPTY)).status_code == 201
        assert (await client.post("/api/voice/session", json=EMPTY)).status_code == 201
        r = await client.post("/api/voice/session", json=EMPTY)
    assert r.status_code == 429
    assert r.json()["code"] == "voice_rate_limited"
    assert "séances vocales" in r.json()["message"]


async def test_session_disabled(make_voice_client) -> None:
    realtime = FakeRealtime()
    async with make_voice_client(realtime, voice_enabled=False) as client:
        r = await client.post("/api/voice/session", json=EMPTY)
    assert r.status_code == 503 and r.json()["code"] == "voice_disabled"
    assert realtime.sessions == []


async def test_session_provider_failure_is_502(make_voice_client) -> None:
    async with make_voice_client(ExplodingRealtime(ProviderUnavailable())) as client:
        r = await client.post("/api/voice/session", json=EMPTY)
    assert r.status_code == 502


async def test_session_logs_the_user(make_voice_client, caplog: pytest.LogCaptureFixture) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        with caplog.at_level("INFO"):
            r = await client.post("/api/voice/session", json=EMPTY)
    assert r.status_code == 201
    record = next(r for r in caplog.records if r.getMessage() == "voice_session_issued")
    assert record.user_id  # type: ignore[attr-defined]
    assert "ek_test_secret" not in caplog.text


async def test_voice_routes_need_a_student(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime(), anonymous=True) as client:
        assert (await client.post("/api/voice/session", json=EMPTY)).status_code == 401
        assert (await client.post("/api/voice/tool", json={**IDS, "call_id": "c", "name": "x"})).status_code == 401


async def test_tool_start_section_golden(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        r = await client.post(
            "/api/voice/tool",
            json={**IDS, "session_id": "s", "call_id": "c1", "name": "start_section",
                  "arguments": json.dumps({"section_id": "suites"})},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["event"]["event"] == "section.start"
    assert body["event"]["section_id"] == "suites" and body["event"]["review"] is False
    assert body["progress"] == {"done": [], "active": "suites"}
    assert json.loads(body["output"])["ok"] is True
    assert "Section en cours" in body["state_text"]
    stored = client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID)
    assert stored and stored.progress.active == "suites"


async def test_tool_display_board_golden(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        r = await client.post(
            "/api/voice/tool",
            json={**IDS, "call_id": "c1", "name": "display_board", "arguments": json.dumps({"card": CARD})},
        )
    body = r.json()
    assert body["event"]["event"] == "board.set" and body["event"]["card"]["kind"] == "explanation"
    assert body["state_text"] is None
    assert json.loads(body["output"]) == {"ok": True}


async def test_tool_refusal_and_unknown_are_200(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        refused = await client.post(
            "/api/voice/tool",
            json={**IDS, "call_id": "c1", "name": "complete_section", "arguments": '{"section_id":"suites","summary":"x"}'},
        )
        unknown = await client.post("/api/voice/tool", json={**IDS, "call_id": "c2", "name": "teleport"})
    assert refused.status_code == 200 and refused.json()["event"] is None
    assert json.loads(refused.json()["output"])["ok"] is False
    assert unknown.status_code == 200 and "teleport" in json.loads(unknown.json()["output"])["error"]


async def test_tool_malformed_body_422(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        r = await client.post("/api/voice/tool", json={**IDS, "name": "clear_board"})
    assert r.status_code == 422


async def test_usage_accepts_json_plain_and_garbage(make_voice_client, caplog: pytest.LogCaptureFixture) -> None:
    report = {"session_id": "s", "reason": "learner", "duration_s": 10, "responses": 1,
              "usage": {"input_audio": 100, "output_audio": 200}}
    async with make_voice_client(FakeRealtime()) as client:
        with caplog.at_level("INFO"):
            a = await client.post("/api/voice/usage", json=report)
            b = await client.post("/api/voice/usage", content=json.dumps(report), headers={"content-type": "text/plain"})
            c = await client.post("/api/voice/usage", content=b"not json", headers={"content-type": "text/plain"})
    assert (a.status_code, b.status_code, c.status_code) == (204, 204, 204)
    assert sum(1 for r in caplog.records if r.getMessage() == "voice_usage") == 2
    assert any(r.getMessage() == "voice_usage_malformed" for r in caplog.records)


async def test_usage_is_stored_with_the_user(make_voice_client) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.models import AiUsageRow

    report = {"session_id": "s", "reason": "cap", "duration_s": 10, "responses": 1, "usage": {"output_audio": 7}}
    async with make_voice_client(FakeRealtime()) as client:
        await client.post("/api/voice/usage", json=report)
        with Session(client.app.state.engine) as s:
            row = s.scalar(select(AiUsageRow))
    assert row and row.user_id == client.user["id"] and row.output_audio_tokens == 7 and row.output_tokens == 7
    assert (row.role, row.feature, row.status, row.correlation_id) == ("voice", "voice_session", "ok", "s")
    assert row.audio_seconds == 10.0 and row.cost_usd is None


async def test_a_minted_session_reports_its_usage_for_its_course_and_chapter(make_voice_client) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.models import AiUsageRow

    async with make_voice_client(FakeRealtime()) as client:
        minted = (await client.post("/api/voice/session", json=EMPTY)).json()
        report = {"session_id": minted["session_id"], "reason": "learner", "duration_s": 30, "responses": 2,
                  "usage": {"input_audio": 10, "input_text": 90, "output_audio": 5}}
        # The browser names the session only: a course or chapter id in the body is not accepted.
        assert (await client.post("/api/voice/usage", json={**report, "course_id": "x"})).status_code == 204
        assert (await client.post("/api/voice/usage", json=report)).status_code == 204
        with Session(client.app.state.engine) as s:
            rows = s.scalars(select(AiUsageRow).order_by(AiUsageRow.id)).all()
    (row,) = rows  # the malformed one (an unknown field) was dropped
    assert (row.user_id, row.course_id, row.chapter_id) == (client.user["id"], client.course_id, client.chapter_id)
    assert (row.correlation_id, row.model, row.input_tokens, row.output_audio_tokens) == (
        minted["session_id"], minted["model"], 100, 5)


def _ledger_rows(client) -> list:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.models import AiUsageRow

    with Session(client.app.state.engine) as s:
        return list(s.scalars(select(AiUsageRow).order_by(AiUsageRow.id)))


async def test_a_session_reported_twice_is_one_row(make_voice_client) -> None:
    """The stop and the unload beacon can both report the same session (spec 015)."""
    report = {"session_id": "s-twice", "reason": "learner", "duration_s": 5, "responses": 1, "usage": {"input_text": 9}}
    async with make_voice_client(FakeRealtime()) as client:
        assert [(await client.post("/api/voice/usage", json=report)).status_code for _ in range(3)] == [204] * 3
        rows = _ledger_rows(client)
    assert [(r.correlation_id, r.input_tokens) for r in rows] == [("s-twice", 9)]


async def test_reports_beyond_what_the_minting_allows_are_dropped_with_a_204(make_voice_client, caplog) -> None:
    async with make_voice_client(FakeRealtime(), voice_sessions_per_hour=1) as client:  # two reports an hour
        with caplog.at_level("WARNING"):
            statuses = [
                (await client.post("/api/voice/usage", json={"session_id": f"s{n}", "reason": "cap", "duration_s": 1, "responses": 1})).status_code
                for n in range(4)
            ]
        rows = _ledger_rows(client)
    assert statuses == [204] * 4  # a beacon is never refused
    assert [r.correlation_id for r in rows] == ["s0", "s1"]
    assert any(r.getMessage() == "voice_usage_rate_limited" for r in caplog.records)


@pytest.mark.parametrize("totals", [{"input_text": -1}, {"output_audio": 10**12}, {"cached_text": "many"}])
async def test_a_forged_total_is_dropped_not_stored(make_voice_client, totals: dict, caplog) -> None:
    report = {"session_id": "s", "reason": "cap", "duration_s": 1, "responses": 1, "usage": totals}
    async with make_voice_client(FakeRealtime()) as client:
        with caplog.at_level("WARNING"):
            r = await client.post("/api/voice/usage", json=report)
        assert r.status_code == 204 and _ledger_rows(client) == []
    assert any(rec.getMessage() == "voice_usage_malformed" for rec in caplog.records)


async def test_a_failed_store_is_logged_by_its_class_only(make_voice_client, monkeypatch, caplog) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        def boom(*_: object, **__: object) -> None:
            raise RuntimeError("secret bound value 4242")

        monkeypatch.setattr(client.app.state.repos.ai_usage, "add_once", boom)
        with caplog.at_level("ERROR"):
            await client.post("/api/voice/usage", json={"session_id": "s", "reason": "cap", "duration_s": 1, "responses": 1})
    (record,) = [r for r in caplog.records if r.getMessage() == "voice_usage_not_stored"]
    assert record.error == "RuntimeError" and not record.exc_info  # type: ignore[attr-defined]
    assert "4242" not in caplog.text


async def test_voice_limiter_is_per_user(make_voice_client) -> None:
    from tests.conftest import seed_lesson, sign_in

    async with make_voice_client(FakeRealtime(), voice_sessions_per_hour=1) as client:
        assert (await client.post("/api/voice/session", json=EMPTY)).status_code == 201
        assert (await client.post("/api/voice/session", json=EMPTY)).status_code == 429
        bob, other = sign_in(client.app, email="bob@example.be", name="Bob", lesson=False)
        course_id, chapter_id = seed_lesson(client.app, bob["id"])
        body = {"course_id": course_id, "chapter_id": chapter_id, "history": []}
        assert (await client.post("/api/voice/session", json=body, headers=other)).status_code == 201


async def test_usage_survives_a_failing_store(make_voice_client, monkeypatch, caplog) -> None:
    """003 §3.1: a beacon cannot retry, so the route answers 204 whatever the DB does."""
    report = {"session_id": "s", "reason": "cap", "duration_s": 1, "responses": 1, "usage": {}}
    async with make_voice_client(FakeRealtime()) as client:
        def boom(*_: object, **__: object) -> None:
            raise RuntimeError("disk full")

        monkeypatch.setattr(client.app.state.repos.ai_usage, "add_once", boom)
        with caplog.at_level("INFO"):
            r = await client.post("/api/voice/usage", json=report)
    assert r.status_code == 204
    assert any(rec.getMessage() == "voice_usage" for rec in caplog.records)
    assert any(rec.getMessage() == "voice_usage_not_stored" for rec in caplog.records)


# --- discussion mode (007 §3.10) ----------------------------------------------


async def _conversation(client) -> str:
    r = await client.post(f"/api/courses/{client.course_id}/chapters/{client.chapter_id}/discussion")
    assert r.status_code == 201, r.text
    return r.json()["conversation"]["id"]


async def test_a_discussion_session_declares_only_the_board_tools(make_voice_client) -> None:
    realtime = FakeRealtime()
    async with make_voice_client(realtime) as client:
        conversation = await _conversation(client)
        r = await client.post(
            "/api/voice/session",
            json={**IDS, "history": [], "mode": "discussion", "conversation_id": conversation},
        )
    assert r.status_code == 201
    tools = [t["name"] for t in realtime.sessions[-1]["tools"]]
    assert tools == ["display_board", "clear_board"]
    assert "## La discussion" in realtime.sessions[-1]["instructions"]
    assert "start_section" not in realtime.sessions[-1]["instructions"]


async def test_a_discussion_session_is_seeded_from_the_stored_conversation(make_voice_client) -> None:
    """R4.4: the browser posts no transcript here; the server has it."""
    realtime = FakeRealtime()
    async with make_voice_client(realtime) as client:
        conversation = await _conversation(client)
        repos = client.app.state.repos
        repos.conversations.append(
            conversation,
            [{"kind": "learner", "text": "parle-moi des suites"}],
            expected_count=0,
            max_entries=400,
            max_chars=200_000,
        )
        r = await client.post(
            "/api/voice/session",
            json={**IDS, "history": [], "mode": "discussion", "conversation_id": conversation},
        )
    body = r.json()
    assert body["opening"] is False
    assert "parle-moi des suites" in json.dumps(body["seed"], ensure_ascii=False)


async def test_a_discussion_session_needs_a_conversation(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        missing = await client.post(
            "/api/voice/session", json={**IDS, "history": [], "mode": "discussion"}
        )
        unknown = await client.post(
            "/api/voice/session",
            json={**IDS, "history": [], "mode": "discussion", "conversation_id": "0" * 32},
        )
    assert missing.status_code == 404 and unknown.status_code == 404


async def test_a_section_tool_is_refused_from_a_discussion_and_writes_no_progress(
    make_voice_client,
) -> None:
    """The browser sends the tool name, so the gate has to be here (007 §3.5)."""
    async with make_voice_client(FakeRealtime()) as client:
        r = await client.post(
            "/api/voice/tool",
            json={
                **IDS,
                "mode": "discussion",
                "call_id": "c1",
                "name": "start_section",
                "arguments": json.dumps({"section_id": "suites"}),
            },
        )
        stored = client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID)

    assert r.status_code == 200
    body = r.json()
    assert body["event"] is None
    output = json.loads(body["output"])
    assert output["ok"] is False and "n'est pas disponible ici" in output["error"]
    assert stored is None


async def test_the_board_still_works_by_voice_in_a_discussion(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        r = await client.post(
            "/api/voice/tool",
            json={**IDS, "mode": "discussion", "call_id": "c1", "name": "display_board",
                  "arguments": json.dumps({"card": CARD})},
        )
    assert r.json()["event"]["event"] == "board.set"


# --- reporting a spoken turn (007 deviation D1) -------------------------------


async def test_a_spoken_turn_is_appended_to_the_conversation(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        conversation = await _conversation(client)
        r = await client.post(
            "/api/discussion/voice/turn",
            json={
                **IDS,
                "conversation_id": conversation,
                "entries": [
                    {"kind": "learner", "text": "et les suites géométriques ?"},
                    {"kind": "tutor", "text": "On y vient."},
                ],
            },
        )
        stored = client.app.state.repos.conversations.get_owned(
            client.user["id"], client.chapter_id, conversation
        )
    assert r.status_code == 204
    assert stored is not None and stored.entry_count == 2


async def test_a_spoken_turn_is_bounded_and_owner_scoped(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime()) as client:
        conversation = await _conversation(client)
        too_many = await client.post(
            "/api/discussion/voice/turn",
            json={**IDS, "conversation_id": conversation,
                  "entries": [{"kind": "learner", "text": "x"}] * 33},
        )
        empty = await client.post(
            "/api/discussion/voice/turn",
            json={**IDS, "conversation_id": conversation, "entries": []},
        )
        unknown = await client.post(
            "/api/discussion/voice/turn",
            json={**IDS, "conversation_id": "0" * 32,
                  "entries": [{"kind": "learner", "text": "x"}]},
        )
    assert too_many.status_code == 422
    assert empty.status_code == 422
    assert unknown.status_code == 404


# --- spec 014 R10: voice follows the voice connection ---------------------------------------------


async def test_the_calls_url_is_the_voice_servers(make_voice_client) -> None:
    async with make_voice_client(FakeRealtime(), voice_base_url="https://rt.example/v1", voice_api_key="k2") as client:
        r = await client.post("/api/voice/session", json=EMPTY)
    assert r.status_code == 201 and r.json()["calls_url"] == "https://rt.example/v1/realtime/calls"


async def test_voice_is_off_when_the_default_provider_is_not_openai(make_voice_client) -> None:
    """Realtime is not guessed to work elsewhere: no voice connection of its own, no session, and no mint."""
    realtime = FakeRealtime()
    async with make_voice_client(
        realtime, openai_base_url="https://api.groq.com/openai/v1", openai_api_key="gsk-k", openai_model="m"
    ) as client:
        r = await client.post("/api/voice/session", json=EMPTY)
        health = (await client.get("/api/health")).json()
    assert r.status_code == 503 and r.json()["code"] == "voice_disabled" and realtime.sessions == []
    assert health["voice"] is False and health["ai_configured"] is True and health["voice_model"] is None


async def test_voice_comes_back_with_a_connection_of_its_own(make_voice_client) -> None:
    realtime = FakeRealtime()
    async with make_voice_client(
        realtime, openai_base_url="https://api.groq.com/openai/v1", openai_api_key="gsk-k", openai_model="m",
        voice_base_url="https://api.openai.com/v1", voice_api_key="sk-voice",
    ) as client:
        r = await client.post("/api/voice/session", json=EMPTY)
        health = (await client.get("/api/health")).json()
    assert r.status_code == 201 and r.json()["calls_url"] == "https://api.openai.com/v1/realtime/calls"
    assert health["voice"] is True and health["voice_model"] == "gpt-realtime-2.1"
