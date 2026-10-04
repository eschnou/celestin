from __future__ import annotations

from tests.conftest import CHAPTER_ID, LESSON

import json

import pytest

from app.providers.base import Completed, Failed, TextDelta
from app.domain.errors import ProviderRateLimited
from tests.conftest import CARD, seed_progress, sse_frames as frames, tool_call as call
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM

BODY = LESSON


async def post(
    make_client, llm, history: list | None = None, progress: dict | None = None
) -> tuple[int, str, dict]:
    """Progress, when given, is stored for the signed-in user first (004 R6):
    the request itself no longer carries it."""
    client, _ = make_client(llm)
    if progress is not None:
        seed_progress(client.app, client.user["id"], CHAPTER_ID, progress["done"], progress["active"])
    async with client:
        r = await client.post("/api/chat", json={**BODY, "history": history or []})
        return r.status_code, r.text, dict(r.headers)


# --- golden transcript 1: text only ---------------------------------------


async def test_golden_text_only(make_client) -> None:
    llm = FakeLLM([[TextDelta("Salut "), TextDelta("!"), Completed(usage={"input_tokens": 9})]])
    status, body, headers = await post(make_client, llm)
    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert body == (
        'event: turn.start\ndata: {"turn_id":'
        + json.dumps(frames(body)[0][1]["turn_id"])
        + "}\n\n"
        'event: text.delta\ndata: {"block_id":0,"text":"Salut "}\n\n'
        'event: text.delta\ndata: {"block_id":0,"text":"!"}\n\n'
        'event: turn.end\ndata: {"reason":"end","usage":{"input_tokens":9}}\n\n'
    )


# --- golden transcript 2: text, board, text -------------------------------


async def test_golden_text_board_text(make_client) -> None:
    llm = FakeLLM(
        [
            [TextDelta("Regarde le tableau."), call("display_board", {"card": CARD}), Completed()],
            [TextDelta("Tu suis ?"), Completed()],
        ]
    )
    _, body, _ = await post(make_client, llm)
    got = frames(body)
    assert [name for name, _ in got] == [
        "turn.start",
        "text.delta",
        "board.set",
        "text.delta",
        "turn.end",
    ]
    assert got[2][1]["marker"] == "explication affichée"
    assert got[2][1]["card"]["kind"] == "explanation"
    assert got[1][1]["block_id"] == 0
    assert got[3][1]["block_id"] == 1


# --- golden transcript 3: invalid tool call, then a corrected one ----------


async def test_golden_tool_self_correction(make_client) -> None:
    bad = {"card": {"kind": "explanation", "title": "T", "blocks": []}}
    llm = FakeLLM(
        [
            [call("display_board", bad), Completed()],
            [call("display_board", {"card": CARD}), Completed()],
            [TextDelta("voilà"), Completed()],
        ]
    )
    _, body, _ = await post(make_client, llm)
    names = [name for name, _ in frames(body)]
    assert names == ["turn.start", "board.set", "text.delta", "turn.end"]
    assert "error" not in names


# --- headers, errors, caps ------------------------------------------------


async def test_sse_headers(make_client) -> None:
    _, _, headers = await post(make_client, FakeLLM([[Completed()]]))
    assert headers["cache-control"] == "no-cache"
    assert headers["x-accel-buffering"] == "no"


async def test_history_is_replayed_to_the_model(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    await post(
        make_client,
        llm,
        history=[{"kind": "learner", "text": "salut"}, {"kind": "tutor", "text": "bonjour"}],
    )
    items = llm.calls[0]["input"]
    assert {"role": "user", "content": "salut"} in items
    assert {"role": "assistant", "content": "bonjour"} in items


async def test_provider_failure_after_first_byte_is_an_in_stream_error(make_client) -> None:
    llm = FakeLLM([[TextDelta("début"), Failed(code="provider_unavailable", message="boom")]])
    status, body, _ = await post(make_client, llm)
    assert status == 200
    names = [n for n, _ in frames(body)]
    assert names == ["turn.start", "text.delta", "error", "turn.end"]
    error = frames(body)[2][1]
    assert error["code"] == "provider_unavailable"
    assert "boom" not in body
    assert "Traceback" not in body


async def test_a_streamed_failure_keeps_its_code_like_a_raised_one(make_client) -> None:
    """Both provider error paths reach the learner through the same translation."""
    streamed = FakeLLM([[Failed(code="provider_rate_limited", message="slow down")]])
    _, from_stream, _ = await post(make_client, streamed)
    _, from_raise, _ = await post(make_client, ExplodingLLM(ProviderRateLimited()))

    for body in (from_stream, from_raise):
        error = next(data for name, data in frames(body) if name == "error")
        assert error["code"] == "provider_rate_limited"
        assert "Attends quelques secondes" in error["message"]


async def test_provider_raising_before_the_stream_is_still_in_stream(make_client) -> None:
    status, body, _ = await post(make_client, ExplodingLLM(ProviderRateLimited()))
    assert status == 200
    names = [n for n, _ in frames(body)]
    assert names == ["turn.start", "error", "turn.end"]
    assert frames(body)[1][1]["code"] == "provider_rate_limited"


async def test_chapter_not_ready_is_a_409_before_any_frame(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    client, _ = make_client(llm)
    async with client:
        repos = client.app.state.repos
        bare = repos.chapters.create(LESSON["course_id"], "texte collé", max_chapters=40)
        r = await client.post("/api/chat", json={"course_id": LESSON["course_id"], "chapter_id": bare.id, "history": []})
    assert r.status_code == 409 and r.json()["code"] == "chapter_not_ready"
    assert "event:" not in r.text
    assert llm.rounds_used == 0


async def test_chat_is_scoped_to_the_owner(make_client) -> None:
    """005 R6.2: 404, not 403, so ownership is not probeable."""
    llm = FakeLLM([[Completed()]])
    client, _ = make_client(llm)
    async with client:
        from tests.conftest import sign_in

        _, headers = sign_in(client.app, email="bob@example.be", name="Bob", lesson=False)
        foreign = await client.post("/api/chat", json={**BODY, "history": []}, headers=headers)
        wrong_chapter = await client.post("/api/chat", json={**BODY, "chapter_id": "ab" * 16, "history": []})
        bad_id = await client.post("/api/chat", json={**BODY, "chapter_id": "suites", "history": []})
    assert foreign.status_code == 404 and wrong_chapter.status_code == 404
    assert bad_id.status_code == 422
    assert llm.rounds_used == 0


async def test_system_text_carries_the_subject_prompt(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    status, _, _ = await post(make_client, llm)
    assert status == 200
    system = llm.calls[0]["input"][0]["content"][0]["text"]
    assert "## La matière : mathématiques" in system
    assert system.index("La matière") < system.index("# Les suites numériques") < system.index("Parcours du chapitre")

async def test_section_start_persists_progress(make_client) -> None:
    """004 R6.2: the transition is stored in the same request that emits the event."""
    llm = FakeLLM([[call("start_section", {"section_id": "suites"}), Completed()], [Completed()]])
    client, _ = make_client(llm)
    async with client:
        r = await client.post("/api/chat", json={**BODY, "history": []})
    assert r.status_code == 200 and "section.start" in r.text
    record = client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID)
    assert record and record.progress.active == "suites"


async def test_refused_start_persists_nothing(make_client) -> None:
    llm = FakeLLM([[call("start_section", {"section_id": "sg-applications"}), Completed()], [Completed()]])
    client, _ = make_client(llm)
    async with client:
        await client.post("/api/chat", json={**BODY, "history": []})
    assert client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID) is None


async def test_failing_store_is_a_tool_error_not_an_event(make_client, monkeypatch) -> None:
    llm = FakeLLM([[call("start_section", {"section_id": "suites"}), Completed()], [Completed()]])
    client, _ = make_client(llm)

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(client.app.state.repos.progress, "save", boom)
    async with client:
        r = await client.post("/api/chat", json={**BODY, "history": []})
    assert r.status_code == 200 and "section.start" not in r.text
    answered = next(i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output")
    output = json.loads(answered["output"])
    assert output["ok"] is False and "enregistrer" in output["error"]


@pytest.mark.parametrize(
    "history",
    [
        [{"kind": "learner", "text": "x" * 5000}],
        [{"kind": "learner", "text": "ok"}] * 401,
        [{"kind": "bogus", "text": "ok"}],
    ],
)
async def test_invalid_payloads_are_rejected_without_calling_the_provider(
    make_client, history: list
) -> None:
    llm = FakeLLM([[Completed()]])
    client, _ = make_client(llm)
    async with client:
        r = await client.post("/api/chat", json={**BODY, "history": history})
    assert r.status_code == 422
    assert llm.rounds_used == 0


# --- golden transcript 4: sections (002) -----------------------------------


async def test_golden_section_start_and_done(make_client) -> None:
    llm = FakeLLM(
        [
            [TextDelta("On commence."), call("start_section", {"section_id": "suites"}), Completed()],
            [TextDelta("Voilà le plan."), Completed()],
        ]
    )
    _, body, _ = await post(make_client, llm)
    got = frames(body)
    assert [name for name, _ in got] == ["turn.start", "text.delta", "section.start", "text.delta", "turn.end"]
    assert got[2][1] == {
        "section_id": "suites",
        "review": False,
        "marker": "section commencée · 1. Suites numériques",
    }

    llm = FakeLLM(
        [
            [call("complete_section", {"section_id": "suites", "summary": "Définition vue."}), Completed()],
            [Completed()],
        ]
    )
    _, body, _ = await post(make_client, llm, progress={"done": [], "active": "suites"})
    got = frames(body)
    assert [name for name, _ in got] == ["turn.start", "section.done", "turn.end"]
    assert got[1][1] == {
        "section_id": "suites",
        "next_section_id": "sa-definition",
        "marker": "section terminée · 1. Suites numériques",
    }


async def test_golden_step_ready(make_client) -> None:
    llm = FakeLLM(
        [
            [TextDelta("Bien vu."), call("propose_next_step", {}), Completed()],
            [TextDelta("Ensuite, la formule."), Completed()],
        ]
    )
    _, body, _ = await post(make_client, llm)
    got = frames(body)
    assert [name for name, _ in got] == ["turn.start", "text.delta", "step.ready", "text.delta", "turn.end"]
    assert got[2][1] == {"marker": "étape suivante proposée"}


async def test_refused_section_start_emits_no_event(make_client) -> None:
    llm = FakeLLM([[call("start_section", {"section_id": "synthese"}), Completed()], [Completed()]])
    _, body, _ = await post(make_client, llm)
    assert [name for name, _ in frames(body)] == ["turn.start", "turn.end"]
    outputs = [i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert json.loads(outputs[0]["output"])["ok"] is False


async def test_state_message_is_sent_last(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    await post(make_client, llm, progress={"done": ["suites"], "active": "sa-definition"})
    last = llm.calls[0]["input"][-1]
    assert last["role"] == "developer"
    assert "sa-definition" in last["content"][0]["text"]


async def test_inconsistent_progress_is_repaired_not_rejected(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    status, _, _ = await post(make_client, llm, progress={"done": ["suites"], "active": "suites"})
    assert status == 200
    last = llm.calls[0]["input"][-1]
    assert "Aucune section en cours" in last["content"][0]["text"]


async def test_progress_write_is_logged_with_who_and_where(make_client, caplog) -> None:
    """004 §9: the turn and the write both name the student and the chapter."""
    llm = FakeLLM([[call("start_section", {"section_id": "suites"}), Completed()], [Completed()]])
    client, _ = make_client(llm)
    async with client:
        with caplog.at_level("INFO"):
            await client.post("/api/chat", json={**BODY, "history": []})
    saved = next(r for r in caplog.records if r.getMessage() == "progress_saved")
    assert saved.chapter_id == CHAPTER_ID and saved.active == "suites"  # type: ignore[attr-defined]
    assert saved.user_id == client.user["id"]  # type: ignore[attr-defined]
    turn = next(r for r in caplog.records if r.getMessage() == "turn_complete")
    assert turn.user_id == client.user["id"] and turn.chapter_id == CHAPTER_ID  # type: ignore[attr-defined]
