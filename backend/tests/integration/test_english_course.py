"""Spec 011 R1, R4.7, task 7.6: an English course end to end over HTTP, against the
scripted authoring provider. The French equivalents are `test_courses_endpoint.py`."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import use_fake_authoring
from tests.fixtures.fake_completion import data, text
from tests.integration.test_courses_endpoint import _upload
from tests.unit.test_authoring_agent_en import FRENCH_PACK, PACK, curriculum_for

READ = text("--- page 1 ---\n" + "The pasted English lesson on linear functions. " * 20)
AUTHOR = [text(PACK), data(curriculum_for(PACK))]


async def _english_course(client: AsyncClient) -> str:
    created = await client.post("/api/courses", json={"name": "Maths", "subject": "mathematics", "language": "en"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _ready_chapter(client: AsyncClient, script) -> tuple[str, str, object]:  # noqa: ANN001
    fake = use_fake_authoring(client.app, script)
    course_id = await _english_course(client)
    chapter_id = (await _upload(client, course_id)).json()["id"]
    await client.app.state.authoring.wait_idle()
    return course_id, chapter_id, fake


async def test_an_english_document_becomes_an_english_chapter(client: AsyncClient) -> None:
    course_id, chapter_id, fake = await _ready_chapter(client, [READ, *AUTHOR])
    from tests.unit.test_authoring_agent_en import PROMPTS

    assert fake.calls[0]["instructions"] == [PROMPTS.transcribe("en")]  # type: ignore[attr-defined]
    assert fake.calls[1]["instructions"][0] == PROMPTS.authoring_pack("en")  # type: ignore[attr-defined]
    detail = (await client.get(f"/api/courses/{course_id}")).json()
    (row,) = detail["chapters"]
    assert detail["language"] == "en" and row["ready"] and row["title"] == "Linear functions"
    lesson = (await client.get(f"/api/courses/{course_id}/chapters/{chapter_id}")).json()
    assert lesson["language"] == "en" and [s["id"] for s in lesson["sections"]] == ["definition", "graphs"]
    content = (await client.get(f"/api/courses/{course_id}/chapters/{chapter_id}/content")).json()
    assert content["language"] == "en" and content["pack"].startswith("# Linear functions")


async def test_an_english_pack_edit_is_validated_against_the_english_template(
    client: AsyncClient
) -> None:
    course_id, chapter_id, _ = await _ready_chapter(client, [READ, *AUTHOR])
    url = f"/api/courses/{course_id}/chapters/{chapter_id}"
    content = (await client.get(f"{url}/content")).json()
    edited = content["pack"].replace("Linear functions", "Linear functions, revised", 1)
    saved = await client.put(f"{url}/pack", json={"version": content["version"], "pack": edited})
    assert saved.status_code == 200, saved.text
    assert saved.json()["pack"].startswith("# Linear functions, revised")


async def test_a_french_pack_saved_to_an_english_course_is_a_language_mismatch(
    client: AsyncClient
) -> None:
    course_id, chapter_id, _ = await _ready_chapter(client, [READ, *AUTHOR])
    url = f"/api/courses/{course_id}/chapters/{chapter_id}"
    content = (await client.get(f"{url}/content")).json()
    refused = await client.put(f"{url}/pack", json={"version": content["version"], "pack": FRENCH_PACK})
    assert refused.status_code == 422 and refused.json()["code"] == "content_invalid"
    first = refused.json()["issues"][0]
    assert first["message"] == "le document suit le modèle en français, mais ce cours est en anglais"
    # In the student's interface language, whatever the course's.
    await client.patch("/api/auth/me", json={"locale": "en"})
    english = await client.put(f"{url}/pack", json={"version": content["version"], "pack": FRENCH_PACK})
    assert english.json()["issues"][0]["message"] == (
        "the document follows the French template, but this course is in English"
    )
    assert (await client.get(f"{url}/content")).json()["version"] == content["version"]  # nothing changed


async def test_the_french_course_is_validated_against_the_french_template_as_before(
    client: AsyncClient
) -> None:
    from tests.conftest import CHAPTER_ID, COURSE_ID

    url = f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}"
    content = (await client.get(f"{url}/content")).json()
    refused = await client.put(f"{url}/pack", json={"version": content["version"], "pack": PACK})
    assert refused.status_code == 422
    assert refused.json()["issues"][0]["message"] == (
        "le document suit le modèle en anglais, mais ce cours est en français"
    )
