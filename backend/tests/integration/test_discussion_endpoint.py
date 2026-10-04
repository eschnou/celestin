"""The discussion routes (007 design 3.9)."""

from __future__ import annotations

import json

from app.domain.errors import ProviderRateLimited
from app.providers.base import Completed, TextDelta
from tests.conftest import CARD, CHAPTER_ID, COURSE_ID, LESSON
from tests.conftest import seed_progress, sse_frames as frames, tool_call as call
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM

DISCUSSION_URL = f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}/discussion"
TURN_URL = "/api/discussion/turn"


async def _start(client) -> dict:
    r = await client.post(DISCUSSION_URL)
    assert r.status_code == 201, r.text
    return r.json()["conversation"]


async def _turn(client, conversation_id: str, message: str | None) -> tuple[int, str]:
    r = await client.post(
        TURN_URL, json={**LESSON, "conversation_id": conversation_id, "message": message}
    )
    return r.status_code, r.text


# --- the conversation ---------------------------------------------------------


async def test_a_chapter_has_no_conversation_until_one_is_started(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        r = await client.get(DISCUSSION_URL)
        assert r.status_code == 200
        assert r.json() == {"conversation": None}


async def test_starting_returns_an_empty_conversation_and_get_finds_it(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        started = await _start(client)
        assert started["entries"] == [] and started["entry_count"] == 0
        assert (await client.get(DISCUSSION_URL)).json()["conversation"]["id"] == started["id"]


async def test_starting_again_replaces_the_live_conversation(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        first = await _start(client)
        second = await _start(client)
        assert second["id"] != first["id"]
        assert (await client.get(DISCUSSION_URL)).json()["conversation"]["id"] == second["id"]

        status, _ = await _turn(client, first["id"], "salut")
        assert status == 409


# --- the golden transcript ----------------------------------------------------


async def test_golden_opening_turn(make_client) -> None:
    """Byte-exact, like the chat goldens: the event set is unchanged (NFR 4.1.2)."""
    llm = FakeLLM([[TextDelta("Salut "), TextDelta("!"), Completed(usage={"input_tokens": 9})]])
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        status, body = await _turn(client, conversation["id"], None)

    assert status == 200
    assert body == (
        'event: turn.start\ndata: {"turn_id":'
        + json.dumps(frames(body)[0][1]["turn_id"])
        + "}\n\n"
        'event: text.delta\ndata: {"block_id":0,"text":"Salut "}\n\n'
        'event: text.delta\ndata: {"block_id":0,"text":"!"}\n\n'
        'event: turn.end\ndata: {"reason":"end","usage":{"input_tokens":9}}\n\n'
    )


async def test_a_turn_is_stored_and_read_back_with_its_markers(make_client) -> None:
    llm = FakeLLM(
        [
            [TextDelta("Regarde."), call("display_board", {"card": CARD}), Completed()],
            [TextDelta("Tu suis ?"), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        status, _ = await _turn(client, conversation["id"], "explique-moi les suites")
        assert status == 200

        entries = (await client.get(DISCUSSION_URL)).json()["conversation"]["entries"]

    assert [e["kind"] for e in entries] == ["learner", "tutor", "tool", "tutor"]
    assert entries[0]["text"] == "explique-moi les suites"
    assert entries[1]["text"] == "Regarde."
    assert entries[2]["name"] == "display_board"
    assert entries[2]["marker"] == "explication affichée"
    assert entries[3]["text"] == "Tu suis ?"


async def test_the_stored_transcript_is_what_the_next_turn_reads(make_client) -> None:
    llm = FakeLLM([[TextDelta("un"), Completed()], [TextDelta("deux"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        await _turn(client, conversation["id"], "première")
        await _turn(client, conversation["id"], "deuxième")

    # The second call's input carries the first exchange, which the browser never
    # sent back: the server is the source of truth (R4.4).
    texts = json.dumps(llm.calls[1], ensure_ascii=False)
    assert "première" in texts and "un" in texts and "deuxième" in texts


async def test_clear_board_round_trips_with_its_marker(make_client) -> None:
    llm = FakeLLM([[call("clear_board", {}), Completed()], [TextDelta("Voilà."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        await _turn(client, conversation["id"], "efface")
        entries = (await client.get(DISCUSSION_URL)).json()["conversation"]["entries"]

    tool = next(e for e in entries if e["kind"] == "tool")
    assert tool["name"] == "clear_board" and tool["marker"] == "tableau effacé"


# --- the rule the mode exists to keep -----------------------------------------


async def test_a_discussion_never_writes_progress(make_client) -> None:
    """R6.1, asserted against the database rather than against prompt text."""
    llm = FakeLLM(
        [
            [call("start_section", {"section_id": "suites"}), Completed()],
            [TextDelta("Je ne peux pas ouvrir de section ici."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        status, body = await _turn(client, conversation["id"], "commence la section 1")
        assert status == 200
        assert [name for name, _ in frames(body)] == ["turn.start", "text.delta", "turn.end"]
        progress = client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID)

    assert progress is None


async def test_the_refused_tool_is_reported_to_the_model_not_to_the_learner(make_client) -> None:
    llm = FakeLLM(
        [
            [call("complete_section", {"section_id": "suites", "summary": "fait"}), Completed()],
            [TextDelta("Ça se passe dans le parcours."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        await _turn(client, conversation["id"], "termine la section")

    outputs = json.dumps(llm.calls[1], ensure_ascii=False)
    assert "n'est pas disponible ici" in outputs


async def test_a_discussion_declares_only_the_board_tools(make_client) -> None:
    llm = FakeLLM([[TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        await _turn(client, conversation["id"], "salut")

    assert [t["name"] for t in llm.tools] == ["display_board", "clear_board"]


async def test_an_existing_progress_record_is_read_but_untouched(make_client) -> None:
    llm = FakeLLM([[TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    seed_progress(client.app, client.user["id"], CHAPTER_ID, ["suites"], None)
    async with client:
        conversation = await _start(client)
        await _turn(client, conversation["id"], "où en suis-je ?")
        after = client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID)

    assert after is not None and after.progress.done == frozenset({"suites"})
    state = json.dumps(llm.calls[0], ensure_ascii=False)
    assert "1 section(s) faite(s)" in state
    assert "start_section" not in state


# --- failures -----------------------------------------------------------------


async def test_a_provider_failure_stores_nothing(make_client) -> None:
    client, _ = make_client(ExplodingLLM(ProviderRateLimited()))
    async with client:
        conversation = await _start(client)
        status, body = await _turn(client, conversation["id"], "salut")
        assert status == 200
        # The turn started, then failed: the TurnEnd the error path emits never
        # passes through the completion hook, so nothing is stored.
        assert [name for name, _ in frames(body)] == ["turn.start", "error", "turn.end"]

        entries = (await client.get(DISCUSSION_URL)).json()["conversation"]["entries"]

    assert entries == []


async def test_an_opening_turn_on_a_started_conversation_is_refused(make_client) -> None:
    llm = FakeLLM([[TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        conversation = await _start(client)
        await _turn(client, conversation["id"], "salut")
        status, body = await _turn(client, conversation["id"], None)

    assert status == 422
    assert json.loads(body)["code"] == "empty_conversation_expected"


async def test_an_unknown_conversation_is_not_found(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        status, body = await _turn(client, "0" * 32, "salut")
    assert status == 404
    assert json.loads(body)["code"] == "not_found"


async def test_another_students_conversation_is_not_found(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    other, _ = make_client(FakeLLM([]), email="autre@example.be")
    async with other:
        theirs = await other.post(
            f"/api/courses/{other.course_id}/chapters/{other.chapter_id}/discussion"
        )
        theirs_id = theirs.json()["conversation"]["id"]
    async with client:
        status, _ = await _turn(client, theirs_id, "salut")
    assert status == 404


async def test_a_full_conversation_refuses_the_next_turn(make_client) -> None:
    llm = FakeLLM([[TextDelta("ok"), Completed()]])
    client, _ = make_client(llm, discussion_max_entries=2)
    async with client:
        conversation = await _start(client)
        assert (await _turn(client, conversation["id"], "salut"))[0] == 200
        status, body = await _turn(client, conversation["id"], "encore")

    assert status == 409
    assert json.loads(body)["code"] == "conversation_closed"
    assert "nouvelle discussion" in json.loads(body)["message"]


async def test_the_daily_quota_refuses_a_new_conversation(make_client) -> None:
    client, _ = make_client(FakeLLM([]), discussion_conversations_per_day=1)
    async with client:
        await _start(client)
        r = await client.post(DISCUSSION_URL)
    assert r.status_code == 429 and r.json()["code"] == "discussion_quota"


async def test_a_chapter_without_content_is_not_ready(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        repos = client.app.state.repos
        course = repos.courses.create(client.user["id"], "Physique", "sciences", max_courses=30)
        chapter = repos.chapters.create(course.id, "texte", max_chapters=40)
        r = await client.get(f"/api/courses/{course.id}/chapters/{chapter.id}/discussion")
    assert r.status_code == 409 and r.json()["code"] == "chapter_not_ready"


async def test_the_routes_need_a_signed_in_student(make_client) -> None:
    client, _ = make_client(FakeLLM([]), anonymous=True)
    async with client:
        assert (await client.get(DISCUSSION_URL)).status_code == 401
        assert (await client.post(DISCUSSION_URL)).status_code == 401
        assert (await client.post(TURN_URL, json={**LESSON, "conversation_id": "0" * 32})).status_code == 401
