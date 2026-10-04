"""Spec 010 R5.4, R5.5: the labels, titles, statuses and markers the server builds for
the student follow the account's language; the course's own text does not."""

from __future__ import annotations

import json

from httpx import AsyncClient

from app.domain.errors import ProviderUnavailable
from app.providers.base import Completed, TextDelta
from tests.conftest import CARD, CHAPTER_ID, COURSE_ID, LESSON
from tests.conftest import sse_frames as frames
from tests.conftest import tool_call as call
from tests.fixtures.fake_llm import FakeLLM
from tests.conftest import use_fake_authoring
from tests.integration.test_courses_endpoint import AUTHOR, READ, _new_course, _upload

DISCUSSION_URL = f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}/discussion"


async def _english(client: AsyncClient) -> None:
    assert (await client.patch("/api/auth/me", json={"locale": "en"})).status_code == 200


async def test_subjects_and_course_summaries_are_labelled_in_the_account_language(client: AsyncClient) -> None:
    await _english(client)
    subjects = (await client.get("/api/subjects")).json()["subjects"]
    assert [(s["id"], s["label"]) for s in subjects] == [
        ("mathematics", "Mathematics"),
        ("sciences", "Science"),
        ("languages", "Languages"),
        ("general", "General courses"),
    ]
    created = (await client.post("/api/courses", json={"name": "Physique 5e", "subject": "sciences"})).json()
    assert created["subject_label"] == "Science" and created["name"] == "Physique 5e"  # the name is the student's
    listed = (await client.get("/api/courses")).json()["courses"]
    assert {c["subject_label"] for c in listed} == {"Mathematics", "Science"}
    detail = (await client.get(f"/api/courses/{COURSE_ID}")).json()
    assert detail["subject_label"] == "Mathematics"
    await client.patch("/api/auth/me", json={"locale": "fr"})
    assert (await client.get(f"/api/courses/{COURSE_ID}")).json()["subject_label"] == "Mathématiques"


async def test_the_chapter_number_is_the_interfaces_and_the_title_the_courses(client: AsyncClient) -> None:
    french = (await client.get(f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}")).json()["title"]
    assert french.startswith("Chapitre 1 — ")
    await _english(client)
    english = (await client.get(f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}")).json()["title"]
    assert english.startswith("Chapter 1 — ")
    assert english.removeprefix("Chapter 1 — ") == french.removeprefix("Chapitre 1 — ")


async def test_a_failed_preparation_is_explained_in_the_account_language(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [READ, ProviderUnavailable(), *AUTHOR])
    course_id = await _new_course(client)
    chapter_id = (await _upload(client, course_id)).json()["id"]
    await client.app.state.authoring.wait_idle()
    row = (await client.get(f"/api/courses/{course_id}")).json()["chapters"][0]
    assert row["authoring_message"].startswith("Le service de préparation est indisponible")
    await _english(client)
    row = (await client.get(f"/api/courses/{course_id}")).json()["chapters"][0]
    assert row["authoring_message"] == "The preparation service isn't available right now. Try again in a few minutes."
    content = (await client.get(f"/api/courses/{course_id}/chapters/{chapter_id}/content")).json()
    assert content["authoring_message"] == row["authoring_message"]


async def test_a_transcription_failure_asks_for_the_document_again_in_english(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [ProviderUnavailable(), READ, *AUTHOR])
    await _english(client)
    course_id = await _new_course(client)
    await _upload(client, course_id)
    await client.app.state.authoring.wait_idle()
    row = (await client.get(f"/api/courses/{course_id}")).json()["chapters"][0]
    assert row["authoring_message"].startswith("The reading service isn't available")


async def test_a_live_board_event_is_marked_in_the_account_language(make_client) -> None:
    llm = FakeLLM([[call("display_board", {"card": CARD}), Completed()], [TextDelta("Voilà."), Completed()]])
    client, _ = make_client(llm, locale="en")
    async with client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    board = next(data for name, data in frames(r.text) if name == "board.set")
    assert board["marker"] == "explanation shown"
    assert board["card"]["title"] == CARD["title"]  # the card is Célestin's, untouched


async def test_a_stored_discussion_is_read_back_in_the_readers_language(make_client) -> None:
    llm = FakeLLM(
        [
            [TextDelta("Regarde."), call("display_board", {"card": CARD}), Completed()],
            [call("clear_board", {}), Completed()],
            [TextDelta("Voilà."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        conversation = (await client.post(DISCUSSION_URL)).json()["conversation"]
        await client.post("/api/discussion/turn", json={**LESSON, "conversation_id": conversation["id"], "message": "montre"})
        french = (await client.get(DISCUSSION_URL)).json()["conversation"]["entries"]
        await _english(client)
        english = (await client.get(DISCUSSION_URL)).json()["conversation"]["entries"]
    markers = lambda entries: [e["marker"] for e in entries if e["kind"] == "tool"]  # noqa: E731
    assert markers(french) == ["explication affichée", "tableau effacé"]
    assert markers(english) == ["explanation shown", "board cleared"]
    # What was said is stored once, as it was said.
    assert [e.get("text") for e in french if e["kind"] != "tool"] == [e.get("text") for e in english if e["kind"] != "tool"]


async def test_a_voice_tool_call_returns_its_marker_in_the_account_language(make_voice_client) -> None:
    from tests.integration.test_voice_endpoint import FakeRealtime

    async with make_voice_client(FakeRealtime(), locale="en") as client:
        r = await client.post(
            "/api/voice/tool",
            json={**LESSON, "name": "clear_board", "arguments": json.dumps({}), "call_id": "c1"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["event"]["marker"] == "board cleared"


# --- why a content edit is refused (spec 010 R5.6) -----------------------------------

CH = f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}"


async def _content(client: AsyncClient) -> dict:
    return (await client.get(f"{CH}/content")).json()


async def test_a_refused_pack_edit_explains_itself_in_the_account_language(client: AsyncClient) -> None:
    content = await _content(client)
    broken = content["pack"].replace("## 5. Vocabulaire", "## 5. Lexique")
    body = {"version": content["version"], "pack": broken}

    french = await client.put(f"{CH}/pack", json=body)
    assert french.json()["message"] == "Le contenu n'est pas valide. Corrige les points indiqués."
    assert {"where": "§ 5", "message": "section « ## 5. Vocabulaire » manquante ou mal intitulée"} in french.json()["issues"]

    await _english(client)
    english = await client.put(f"{CH}/pack", json=body)
    assert english.status_code == 422 and english.json()["code"] == "content_invalid"
    assert english.json()["message"] == "The content isn't valid. Fix the points shown."
    assert {"where": "§ 5", "message": "section “## 5. Vocabulaire” is missing or has the wrong title"} in english.json()["issues"]
    # Nothing was saved either way.
    assert (await _content(client))["version"] == content["version"]


async def test_a_refused_curriculum_edit_keeps_the_form_the_editor_parses(client: AsyncClient) -> None:
    content = await _content(client)
    curriculum = {k: v for k, v in content["curriculum"].items()}
    curriculum["sections"] = [dict(s) for s in curriculum["sections"]]
    first = curriculum["sections"][0]
    first["beats"] = []
    body = {"version": content["version"], "curriculum": _as_input(curriculum)}
    await _english(client)
    r = await client.put(f"{CH}/curriculum", json=body)
    assert r.status_code == 422
    issue = r.json()["issues"][0]
    assert issue["where"] == f"section « {first['id']} »"  # unchanged: the editor finds the section by it
    assert issue["message"] == "a “teach” section must have beats"


def _as_input(curriculum: dict) -> dict:
    """The editor sends the curriculum without the display-only `index`."""
    return {
        **{k: v for k, v in curriculum.items()},
        "sections": [{k: v for k, v in s.items() if k != "index"} for s in curriculum["sections"]],
    }
