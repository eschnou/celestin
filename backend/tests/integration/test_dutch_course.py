"""Spec 017 R3, R4, task 7.2: a Dutch course end to end over HTTP, against the scripted providers. The English
equivalent is `test_english_course.py`, the French ones `test_courses_endpoint.py`."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.providers.base import Completed, TextDelta
from tests.conftest import CHAPTER_ID, COURSE_ID, LESSON, sign_in, use_fake_authoring
from tests.fixtures.fake_completion import data, text
from tests.fixtures.fake_llm import FakeLLM
from tests.integration.test_courses_endpoint import _upload
from tests.unit.test_authoring_agent_nl import ENGLISH_PACK, FRENCH_PACK, PACK, PROMPTS, curriculum_for

READ = text("--- page 1 ---\n" + "De geplakte Nederlandstalige les over eerstegraadsfuncties. " * 20)
AUTHOR = [text(PACK), data(curriculum_for(PACK))]
SUBJECTS = ("mathematics", "sciences", "languages", "general")


async def _dutch_course(client: AsyncClient, subject: str = "mathematics") -> str:
    created = await client.post("/api/courses", json={"name": "Wiskunde", "subject": subject, "language": "nl"})
    assert created.status_code == 201, created.text
    assert created.json()["language"] == "nl"
    return created.json()["id"]


async def _ready_chapter(client: AsyncClient) -> tuple[str, str, object]:
    fake = use_fake_authoring(client.app, [READ, *AUTHOR])
    course_id = await _dutch_course(client)
    chapter_id = (await _upload(client, course_id)).json()["id"]
    await client.app.state.authoring.wait_idle()
    return course_id, chapter_id, fake


@pytest.mark.parametrize("subject", SUBJECTS)
async def test_every_subject_takes_a_dutch_course(client: AsyncClient, subject: str) -> None:
    course_id = await _dutch_course(client, subject)
    assert (await client.get(f"/api/courses/{course_id}")).json()["language"] == "nl"
    assert {c["id"]: c["language"] for c in (await client.get("/api/courses")).json()["courses"]}[course_id] == "nl"


async def test_dutch_is_offered_for_every_subject(client: AsyncClient) -> None:
    subjects = (await client.get("/api/subjects")).json()["subjects"]
    assert [s["id"] for s in subjects] == list(SUBJECTS)
    assert all(s["languages"] == ["fr", "en", "nl"] for s in subjects)


@pytest.mark.parametrize("language", ["de", "nl-BE", "NL", ""])
async def test_an_unsupported_dutch_spelling_is_refused(client: AsyncClient, language: str) -> None:
    r = await client.post("/api/courses", json={"name": "X", "subject": "sciences", "language": language})
    assert r.status_code == 422 and r.json()["code"] == "invalid_language"


async def test_the_language_of_a_dutch_course_cannot_be_changed(client: AsyncClient) -> None:
    course_id = await _dutch_course(client)
    for language in ("fr", "en"):
        r = await client.patch(f"/api/courses/{course_id}", json={"name": "Wiskunde", "language": language})
        assert r.status_code == 422
    assert (await client.get(f"/api/courses/{course_id}")).json()["language"] == "nl"


async def test_a_dutch_document_becomes_a_dutch_chapter(client: AsyncClient) -> None:
    course_id, chapter_id, fake = await _ready_chapter(client)
    assert fake.calls[0]["instructions"] == [PROMPTS.transcribe("nl")]  # type: ignore[attr-defined]
    assert fake.calls[1]["instructions"][0] == PROMPTS.authoring_pack("nl")  # type: ignore[attr-defined]
    detail = (await client.get(f"/api/courses/{course_id}")).json()
    (row,) = detail["chapters"]
    assert detail["language"] == "nl" and row["ready"] and row["title"] == "Eerstegraadsfuncties"
    lesson = (await client.get(f"/api/courses/{course_id}/chapters/{chapter_id}")).json()
    assert lesson["language"] == "nl" and [s["id"] for s in lesson["sections"]] == ["definitie", "grafieken"]
    content = (await client.get(f"/api/courses/{course_id}/chapters/{chapter_id}/content")).json()
    assert content["language"] == "nl" and content["pack"].startswith("# Eerstegraadsfuncties")


async def test_a_dutch_pack_edit_is_validated_against_the_dutch_template(client: AsyncClient) -> None:
    course_id, chapter_id, _ = await _ready_chapter(client)
    url = f"/api/courses/{course_id}/chapters/{chapter_id}"
    content = (await client.get(f"{url}/content")).json()
    edited = content["pack"].replace("Eerstegraadsfuncties", "Eerstegraadsfuncties, herzien", 1)
    saved = await client.put(f"{url}/pack", json={"version": content["version"], "pack": edited})
    assert saved.status_code == 200, saved.text
    assert saved.json()["pack"].startswith("# Eerstegraadsfuncties, herzien")


@pytest.mark.parametrize(
    ("pack", "french", "english"),
    [
        (
            FRENCH_PACK,
            "le document suit le modèle en français, mais ce cours est en néerlandais",
            "the document follows the French template, but this course is in Dutch",
        ),
        (
            ENGLISH_PACK,
            "le document suit le modèle en anglais, mais ce cours est en néerlandais",
            "the document follows the English template, but this course is in Dutch",
        ),
    ],
)
async def test_a_pack_in_another_language_is_a_language_mismatch(
    client: AsyncClient, pack: str, french: str, english: str
) -> None:
    course_id, chapter_id, _ = await _ready_chapter(client)
    url = f"/api/courses/{course_id}/chapters/{chapter_id}"
    content = (await client.get(f"{url}/content")).json()
    refused = await client.put(f"{url}/pack", json={"version": content["version"], "pack": pack})
    assert refused.status_code == 422 and refused.json()["code"] == "content_invalid"
    assert refused.json()["issues"][0]["message"] == french
    await client.patch("/api/auth/me", json={"locale": "en"})  # the account's language, not the course's
    again = await client.put(f"{url}/pack", json={"version": content["version"], "pack": pack})
    assert again.json()["issues"][0]["message"] == english
    assert (await client.get(f"{url}/content")).json()["version"] == content["version"]  # nothing changed


async def test_the_french_course_refuses_a_dutch_pack(client: AsyncClient) -> None:
    url = f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}"
    content = (await client.get(f"{url}/content")).json()
    refused = await client.put(f"{url}/pack", json={"version": content["version"], "pack": PACK})
    assert refused.status_code == 422
    assert refused.json()["issues"][0]["message"] == (
        "le document suit le modèle en néerlandais, mais ce cours est en français"
    )


# --- the tutor ------------------------------------------------------------------------------------------------


async def test_a_dutch_turn_is_built_from_the_dutch_prompt_files(make_client) -> None:
    llm = FakeLLM([[TextDelta("Dag!"), Completed(usage={"input_tokens": 9})]])
    client, _ = make_client(llm, language="nl")
    async with client:
        r = await client.post("/api/chat", json={"course_id": client.course_id, "chapter_id": client.chapter_id, "history": []})
        assert r.status_code == 200, r.text
    system = llm.calls[0]["input"][0]["content"][0]["text"]
    assert "Je bent Célestin" in system and "Het vak: wiskunde" in system
    assert "Tu es Célestin" not in system and "You are Célestin" not in system
    trailing = llm.calls[0]["input"][-1]["content"][0]["text"]
    assert "Stand van het traject" in trailing


async def test_a_dutch_discussion_is_a_dutch_prefix_with_the_board_tools_only(make_client) -> None:
    llm = FakeLLM([[TextDelta("Vertel."), Completed(usage={"input_tokens": 9})]])
    client, _ = make_client(llm, language="nl")
    async with client:
        url = f"/api/courses/{client.course_id}/chapters/{client.chapter_id}/discussion"
        started = await client.post(url)
        assert started.status_code == 201, started.text
        r = await client.post(
            "/api/discussion/turn",
            json={
                "course_id": client.course_id,
                "chapter_id": client.chapter_id,
                "conversation_id": started.json()["conversation"]["id"],
                "message": "Wat is een rij?",
            },
        )
        assert r.status_code == 200, r.text
    system = llm.calls[0]["input"][0]["content"][0]["text"]
    assert "Je bent Célestin" in system and "## De bespreking" in system and "Hier is geen traject" in system
    assert {t["name"] for t in llm.tools} == {"display_board", "clear_board"}


# --- privacy --------------------------------------------------------------------------------------------------


async def test_another_students_dutch_course_is_a_404(client: AsyncClient) -> None:
    course_id, chapter_id, _ = await _ready_chapter(client)
    _, other = sign_in(client.app, email="bob@example.be", name="Bob", lesson=False)
    url = f"/api/courses/{course_id}"
    for target in (url, f"{url}/chapters/{chapter_id}", f"{url}/chapters/{chapter_id}/content"):
        assert (await client.get(target, headers=other)).status_code == 404, target
    turn = await client.post("/api/chat", json={"course_id": course_id, "chapter_id": chapter_id, "history": []}, headers=other)
    assert turn.status_code == 404
    assert (await client.get("/api/courses", headers=other)).json() == {"courses": []}
    assert LESSON["course_id"] == COURSE_ID  # the French fixture course is a different one
