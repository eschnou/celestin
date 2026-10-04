"""Courses, chapters and chapter content over HTTP (005 R1, R5, R6)."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from tests.conftest import CHAPTER_ID, COURSE_ID, LESSON, seed_progress, sign_in

CH = f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}"


async def test_subjects_lists_available_ones_with_limits(client: AsyncClient) -> None:
    body = (await client.get("/api/subjects")).json()
    assert body["subjects"] == [
        {"id": "mathematics", "label": "Mathématiques", "languages": ["fr", "en"]},
        {"id": "sciences", "label": "Sciences", "languages": ["fr", "en"]},
        {"id": "languages", "label": "Langues", "languages": ["fr", "en"]},
        {"id": "general", "label": "Cours généraux", "languages": ["fr", "en"]},
    ]
    assert body["limits"] == {
        "chapter_text_min_chars": 300, "chapter_text_max_chars": 100_000, "pack_max_chars": 60_000,
        "document_max_bytes": 26_214_400, "document_max_pages": 50, "document_min_pixels": 800,
        "document_types": ["application/pdf", "image/jpeg", "image/png", "image/webp"],
    }


async def test_course_crud(client: AsyncClient) -> None:
    created = await client.post("/api/courses", json={"name": "  Physique 5e ", "subject": "sciences"})
    assert created.status_code == 201
    course = created.json()
    assert course["name"] == "Physique 5e" and course["subject_label"] == "Sciences" and course["chapters_total"] == 0
    listed = (await client.get("/api/courses")).json()["courses"]
    assert [c["id"] for c in listed] == [course["id"], COURSE_ID]  # newest activity first
    renamed = await client.patch(f"/api/courses/{course['id']}", json={"name": "Physique"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Physique"
    detail = (await client.get(f"/api/courses/{course['id']}")).json()
    assert detail["chapters"] == [] and detail["subject"] == "sciences"
    assert (await client.delete(f"/api/courses/{course['id']}")).status_code == 204
    assert (await client.get(f"/api/courses/{course['id']}")).status_code == 404


@pytest.mark.parametrize("subject", ["history", "astrologie", ""])
async def test_unavailable_subject_is_refused(client: AsyncClient, subject: str) -> None:
    r = await client.post("/api/courses", json={"name": "X", "subject": subject})
    assert r.status_code == 422 and r.json()["code"] == "invalid_subject"


async def test_blank_name_is_refused(client: AsyncClient) -> None:
    assert (await client.post("/api/courses", json={"name": "   ", "subject": "sciences"})).status_code == 422


async def test_subject_cannot_be_changed(client: AsyncClient) -> None:
    r = await client.patch(f"/api/courses/{COURSE_ID}", json={"name": "M", "subject": "sciences"})
    assert r.status_code == 422
    assert (await client.get(f"/api/courses/{COURSE_ID}")).json()["subject"] == "mathematics"


async def test_course_limit(make_client) -> None:
    from tests.fixtures.fake_llm import FakeLLM

    client, _ = make_client(FakeLLM([]))
    client.app.state.settings.max_courses_per_student = 2
    async with client:
        assert (await client.post("/api/courses", json={"name": "B", "subject": "sciences"})).status_code == 201
        r = await client.post("/api/courses", json={"name": "C", "subject": "sciences"})
    assert r.status_code == 409 and r.json()["code"] == "course_limit"


async def test_course_detail_states_and_last(client: AsyncClient) -> None:
    repos = client.app.state.repos
    bare = repos.chapters.create(COURSE_ID, "texte", max_chapters=40)
    seed_progress(client.app, client.user["id"], CHAPTER_ID, ["suites"], "sa-definition")
    detail = (await client.get(f"/api/courses/{COURSE_ID}")).json()
    first, second = detail["chapters"]
    assert first["id"] == CHAPTER_ID and first["ready"] and first["state"] == "in_progress"
    assert first["done_count"] == 1 and first["last"] is True and first["title"] == "Les suites numériques"
    assert second["id"] == bare.id and second["ready"] is False and second["title"] is None
    assert detail["last_chapter"] == {"id": CHAPTER_ID, "title": "Les suites numériques"}
    assert detail["chapters_total"] == 2 and detail["chapters_done"] == 0


async def test_lesson_view_hides_internals_and_repairs_progress(client: AsyncClient) -> None:
    seed_progress(client.app, client.user["id"], CHAPTER_ID, ["suites", "ghost"], "suites")
    r = await client.get(CH)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["course_id"] == COURSE_ID and body["course_name"] == "Mathématiques 5e" and body["subject"] == "mathematics"
    assert body["progress"] == {"done": ["suites"], "active": None}
    text = json.dumps(body, ensure_ascii=False)
    for internal in ("beats", "exercises", "done_when", "Terminée", "6.1.1"):
        assert internal not in text


async def test_the_lesson_numbers_the_chapter_by_its_position(client: AsyncClient) -> None:
    """The model writes a title; the number is the chapter's rank in the course, so
    reordering chapters later renumbers them (006)."""
    repos = client.app.state.repos
    second = repos.chapters.create(COURSE_ID, "texte", max_chapters=40)
    content = (await client.get(f"{CH}/content")).json()
    numbered = content["pack"].replace("# Les suites", "# Chapitre 7 : les suites", 1)
    saved = await client.put(f"{CH}/pack", json={"version": content["version"], "pack": numbered})
    assert saved.status_code == 200 and saved.json()["title"] == "Les suites numériques"  # stored bare
    lesson = (await client.get(CH)).json()
    assert lesson["title"] == "Chapitre 1 — Les suites numériques" and lesson["position"] == 1
    assert second.position == 2


async def test_lesson_view_of_a_chapter_without_content_is_409(client: AsyncClient) -> None:
    bare = client.app.state.repos.chapters.create(COURSE_ID, "texte", max_chapters=40)
    r = await client.get(f"/api/courses/{COURSE_ID}/chapters/{bare.id}")
    assert r.status_code == 409 and r.json()["code"] == "chapter_not_ready"


async def test_content_view_carries_everything(client: AsyncClient) -> None:
    body = (await client.get(f"{CH}/content")).json()
    assert body["version"] == 1 and body["ready"] and body["subject"] == "mathematics"
    assert body["pack"].startswith("# Les suites numériques")
    first = body["curriculum"]["sections"][0]
    assert first["index"] == 1 and first["beats"] and first["done_when"]
    assert body["source_text"] and body["has_progress"] is False and body["authoring_state"] == "idle"
    assert body["source_kind"] == "text" and body["page_count"] == 0


async def _content(client: AsyncClient) -> dict:
    return (await client.get(f"{CH}/content")).json()


async def test_pack_edit_saves_and_resets_progress(client: AsyncClient) -> None:
    seed_progress(client.app, client.user["id"], CHAPTER_ID, [], "suites")
    content = await _content(client)
    assert content["has_progress"] is True
    new_pack = content["pack"].replace("# Les suites numériques", "# Les suites", 1)
    r = await client.put(f"{CH}/pack", json={"version": content["version"], "pack": new_pack})
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 2 and body["title"] == "Les suites" and body["has_progress"] is False
    assert client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID) is None
    lesson = (await client.get(CH)).json()
    # The lesson names the chapter by its position; the curriculum title is its own.
    assert lesson["title"] == "Chapitre 1 — Les suites numériques" and lesson["position"] == 1


async def test_invalid_pack_edit_lists_issues_and_saves_nothing(client: AsyncClient) -> None:
    content = await _content(client)
    broken = content["pack"].replace("## 5. Vocabulaire", "## 5. Lexique")
    r = await client.put(f"{CH}/pack", json={"version": content["version"], "pack": broken})
    assert r.status_code == 422 and r.json()["code"] == "content_invalid"
    assert {"where": "§ 5", "message": "section « ## 5. Vocabulaire » manquante ou mal intitulée"} in r.json()["issues"]
    assert (await _content(client))["version"] == content["version"]


async def test_pack_edit_that_breaks_a_reference_is_refused(client: AsyncClient) -> None:
    content = await _content(client)
    broken = content["pack"].replace("#### 6.1.2", "#### 6.1.20")
    r = await client.put(f"{CH}/pack", json={"version": content["version"], "pack": broken})
    assert r.status_code == 422
    assert any("6.1.2" in issue["message"] for issue in r.json()["issues"])


async def test_stale_pack_edit_is_409(client: AsyncClient) -> None:
    content = await _content(client)
    r = await client.put(f"{CH}/pack", json={"version": content["version"] - 1, "pack": content["pack"]})
    assert r.status_code == 409 and r.json()["code"] == "stale_version"


def _curriculum_in(content: dict) -> dict:
    return {
        "title": content["curriculum"]["title"],
        "sections": [{k: v for k, v in s.items() if k != "index"} for s in content["curriculum"]["sections"]],
    }


async def test_curriculum_edit_saves_and_resets_progress(client: AsyncClient) -> None:
    seed_progress(client.app, client.user["id"], CHAPTER_ID, [], "suites")
    content = await _content(client)
    curriculum = _curriculum_in(content)
    curriculum["sections"] = curriculum["sections"][:3]
    curriculum["sections"][0]["title"] = "Les suites, pour commencer"
    r = await client.put(f"{CH}/curriculum", json={"version": content["version"], "curriculum": curriculum})
    assert r.status_code == 200
    assert len(r.json()["curriculum"]["sections"]) == 3
    assert client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID) is None
    lesson = (await client.get(CH)).json()
    assert [s["title"] for s in lesson["sections"]][0] == "Les suites, pour commencer"


async def test_curriculum_edit_with_unknown_reference_names_the_section(client: AsyncClient) -> None:
    content = await _content(client)
    curriculum = _curriculum_in(content)
    practise = next(s for s in curriculum["sections"] if s["kind"] == "practise")
    practise["exercises"] = ["9.9.9"]
    r = await client.put(f"{CH}/curriculum", json={"version": content["version"], "curriculum": curriculum})
    assert r.status_code == 422
    assert r.json()["issues"] == [{"where": f"section « {practise['id']} »", "message": "l'exercice 9.9.9 n'existe pas dans le contenu"}]


async def test_curriculum_edit_with_shape_error_names_the_section(client: AsyncClient) -> None:
    content = await _content(client)
    curriculum = _curriculum_in(content)
    curriculum["sections"][0]["beats"] = []
    r = await client.put(f"{CH}/curriculum", json={"version": content["version"], "curriculum": curriculum})
    assert r.status_code == 422
    issue = r.json()["issues"][0]
    assert issue["where"] == f"section « {curriculum['sections'][0]['id']} »" and "beats" in issue["message"]


async def test_delete_chapter_and_reset_progress(client: AsyncClient) -> None:
    seed_progress(client.app, client.user["id"], CHAPTER_ID, [], "suites")
    assert (await client.delete(f"{CH}/progress")).status_code == 204
    assert client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID) is None
    assert (await client.delete(CH)).status_code == 204
    assert (await client.get(CH)).status_code == 404
    assert (await client.get(f"/api/courses/{COURSE_ID}")).json()["chapters"] == []


async def test_another_student_gets_404_everywhere(client: AsyncClient) -> None:
    """005 NFR 4.3.1: ids never grant access alone."""
    _, other = sign_in(client.app, email="bob@example.be", name="Bob", lesson=False)
    content = await _content(client)
    curriculum = _curriculum_in(content)
    calls = [
        ("get", f"/api/courses/{COURSE_ID}", None),
        ("patch", f"/api/courses/{COURSE_ID}", {"name": "x"}),
        ("delete", f"/api/courses/{COURSE_ID}", None),
        ("get", CH, None),
        ("get", f"{CH}/content", None),
        ("put", f"{CH}/pack", {"version": 1, "pack": content["pack"]}),
        ("put", f"{CH}/curriculum", {"version": 1, "curriculum": curriculum}),
        ("delete", f"{CH}/progress", None),
        ("delete", CH, None),
        ("post", "/api/chat", {**LESSON, "history": []}),
        ("post", "/api/voice/tool", {**LESSON, "call_id": "c1", "name": "clear_board", "arguments": "{}"}),
    ]
    for method, url, body in calls:
        kwargs = {"json": body} if body is not None else {}
        r = await getattr(client, method)(url, headers=other, **kwargs)
        assert r.status_code == 404, (method, url, r.status_code)
    assert (await client.get(f"/api/courses", headers=other)).json() == {"courses": []}
    assert (await _content(client))["version"] == content["version"]


async def test_chapter_of_another_course_of_the_same_student_is_404(client: AsyncClient) -> None:
    other = (await client.post("/api/courses", json={"name": "Physique", "subject": "sciences"})).json()
    assert (await client.get(f"/api/courses/{other['id']}/chapters/{CHAPTER_ID}")).status_code == 404


# --- authoring over HTTP (005 R2, R4, R9; 006 R1, R3, R5) ----------------

from tests.conftest import use_fake_authoring  # noqa: E402
from tests.fixtures.documents import encrypted_pdf, page_image, scanned_pdf  # noqa: E402
from tests.fixtures.fake_completion import data, text  # noqa: E402
from tests.unit.test_authoring_agent import CURRICULUM, PACK  # noqa: E402

SOURCE = "Chapitre : les fonctions du premier degré. " * 20
AUTHOR = [text(PACK), data(CURRICULUM)]
READ = text(f"--- page 1 ---\n{SOURCE}")


def photos(count: int = 1) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (f"IMG_{n}.jpg", page_image(text=f"Page {n}"), "image/jpeg")) for n in range(1, count + 1)]


async def _new_course(client: AsyncClient) -> str:
    return (await client.post("/api/courses", json={"name": "Maths bis", "subject": "mathematics"})).json()["id"]


async def _upload(client: AsyncClient, course_id: str, files=None, **kwargs):  # noqa: ANN001
    return await client.post(f"/api/courses/{course_id}/chapters", files=files or photos(), **kwargs)


async def test_add_chapter_reads_pages_then_becomes_ready(client: AsyncClient, caplog) -> None:
    use_fake_authoring(client.app, [READ, *AUTHOR], delay_s=0.1)
    course_id = await _new_course(client)
    with caplog.at_level("INFO"):
        r = await _upload(client, course_id)
    assert r.status_code == 202
    row = r.json()
    assert row["authoring_state"] == "generating" and row["ready"] is False and row["position"] == 1
    assert (row["authoring_stage"], row["pages_done"], row["page_count"]) == ("transcription", 0, 1)
    received = next(rec for rec in caplog.records if rec.getMessage() == "document_received")
    assert received.kind == "images" and received.pages == 1 and "IMG_1" not in str(received.__dict__)
    generating = (await client.get(f"/api/courses/{course_id}")).json()
    assert generating["generating"] == 1
    lesson = await client.get(f"/api/courses/{course_id}/chapters/{row['id']}")
    assert lesson.status_code == 409 and lesson.json()["code"] == "chapter_not_ready"

    await client.app.state.authoring.wait_idle()
    detail = (await client.get(f"/api/courses/{course_id}")).json()
    (ready,) = detail["chapters"]
    assert ready["ready"] and ready["authoring_state"] == "idle" and ready["title"] == "Les fonctions du premier degré"
    assert ready["section_count"] == 2 and detail["generating"] == 0 and ready["authoring_stage"] is None
    lesson = (await client.get(f"/api/courses/{course_id}/chapters/{row['id']}")).json()
    assert [s["id"] for s in lesson["sections"]] == ["definition", "graphiques"]
    content = (await client.get(f"/api/courses/{course_id}/chapters/{row['id']}/content")).json()
    assert content["source_kind"] == "document" and content["page_count"] == 1
    assert content["source_text"].startswith("--- page 1 ---")


async def test_a_scanned_pdf_is_one_page_per_pdf_page(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [])
    course_id = await _new_course(client)
    r = await _upload(client, course_id, [("files", ("cours.pdf", scanned_pdf(3), "application/pdf"))])
    assert r.status_code == 202 and r.json()["page_count"] == 3
    await client.app.state.authoring.shutdown()


@pytest.mark.parametrize(
    ("files", "code", "message"),
    [
        ([("files", ("a.pdf", b"not a document", "application/pdf"))], "document_invalid", "Dépose un PDF ou des photos"),
        ([("files", ("a.pdf", encrypted_pdf(), "application/pdf"))], "document_invalid", "mot de passe"),
        ([("files", ("a.jpg", page_image(600, 800), "image/jpeg"))], "document_invalid", "trop petite"),
        ([("files", ("a.pdf", scanned_pdf(1), "application/pdf"))] * 2, "document_invalid", "un seul PDF"),
        ([("files", ("a.pdf", scanned_pdf(51), "application/pdf"))], "too_many_pages", "50 pages"),
    ],
)
async def test_unreadable_documents_are_refused_in_french(client: AsyncClient, files, code, message) -> None:  # noqa: ANN001
    use_fake_authoring(client.app, [])
    course_id = await _new_course(client)
    r = await _upload(client, course_id, files)
    assert r.status_code == 422 and r.json()["code"] == code and message in r.json()["message"], r.json()
    assert (await client.get(f"/api/courses/{course_id}")).json()["chapters"] == []


async def test_an_empty_form_and_the_old_json_route_are_refused(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [])
    course_id = await _new_course(client)
    empty = await client.post(f"/api/courses/{course_id}/chapters", data={})
    assert empty.status_code == 422 and empty.json()["message"] == "Le document est vide."
    pasted = await client.post(f"/api/courses/{course_id}/chapters", json={"source_text": SOURCE})
    assert pasted.status_code == 422
    assert (await client.get(f"/api/courses/{course_id}")).json()["chapters"] == []


async def test_an_upload_over_the_size_cap_is_413(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [])
    course_id = await _new_course(client)
    big = [("files", ("a.jpg", b"\xff\xd8\xff" + b"0" * (26_214_400 + 70_000), "image/jpeg"))]
    r = await _upload(client, course_id, big)
    assert r.status_code == 413 and r.json()["code"] == "document_too_large"
    assert r.json()["message"] == "Le document dépasse 25 Mo."


async def test_a_streamed_upload_over_the_cap_is_413_in_french(client: AsyncClient) -> None:
    """No Content-Length: the bytes are counted as they arrive, and FastAPI's own
    « error parsing the body » answer must not replace ours."""
    use_fake_authoring(client.app, [])
    course_id = await _new_course(client)

    async def chunks():
        yield b"--b\r\nContent-Disposition: form-data; name=\"files\"; filename=\"a.jpg\"\r\n\r\n"
        for _ in range(27):
            yield b"0" * 1_048_576

    r = await client.post(
        f"/api/courses/{course_id}/chapters", content=chunks(),
        headers={"content-type": "multipart/form-data; boundary=b"},
    )
    assert r.status_code == 413 and r.json() == {"code": "document_too_large", "message": "Le document dépasse 25 Mo."}


async def test_a_streamed_json_body_over_the_cap_is_413(client: AsyncClient) -> None:
    async def chunks():
        yield b'{"source_text": "'
        yield b"x" * 1_100_000
        yield b'"}'

    r = await client.put(f"{CH}/source", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"


@pytest.mark.parametrize("source", ["trop court", "x" * 100_001])
async def test_source_length_is_checked(client: AsyncClient, source: str) -> None:
    use_fake_authoring(client.app, [])
    r = await client.put(f"{CH}/source", json={"source_text": source})
    assert r.status_code == 422 and r.json()["code"] == "source_length"
    assert "entre 300 et 100000 caractères" in r.json()["message"]


async def test_failed_chapter_shows_a_message_and_retries_from_its_transcription(client: AsyncClient) -> None:
    from app.domain.errors import ProviderUnavailable

    fake = use_fake_authoring(client.app, [READ, ProviderUnavailable(), *AUTHOR])
    course_id = await _new_course(client)
    chapter_id = (await _upload(client, course_id)).json()["id"]
    await client.app.state.authoring.wait_idle()
    (row,) = (await client.get(f"/api/courses/{course_id}")).json()["chapters"]
    assert row["authoring_state"] == "failed"
    assert row["authoring_message"].startswith("Le service de préparation est indisponible")
    content = (await client.get(f"/api/courses/{course_id}/chapters/{chapter_id}/content")).json()
    assert content["authoring_message"] == row["authoring_message"] and SOURCE.strip() in content["source_text"]

    retried = await client.post(f"/api/courses/{course_id}/chapters/{chapter_id}/retry")
    assert retried.status_code == 202 and retried.json()["authoring_stage"] == "pack"
    await client.app.state.authoring.wait_idle()
    (row,) = (await client.get(f"/api/courses/{course_id}")).json()["chapters"]
    assert row["ready"] and row["authoring_message"] is None, row
    assert len(fake.calls) == 4  # the pages were read once
    again = await client.post(f"/api/courses/{course_id}/chapters/{chapter_id}/retry")
    assert again.status_code == 409 and again.json()["code"] == "nothing_to_retry"


async def test_a_transcription_failure_asks_for_the_document_again(client: AsyncClient) -> None:
    from app.domain.errors import ProviderUnavailable

    use_fake_authoring(client.app, [ProviderUnavailable(), READ, *AUTHOR])
    course_id = await _new_course(client)
    chapter_id = (await _upload(client, course_id)).json()["id"]
    await client.app.state.authoring.wait_idle()
    (row,) = (await client.get(f"/api/courses/{course_id}")).json()["chapters"]
    assert row["authoring_message"].startswith("Le service de lecture est indisponible")
    assert row["authoring_stage"] == "transcription"
    retried = await client.post(f"/api/courses/{course_id}/chapters/{chapter_id}/retry")
    assert retried.status_code == 409 and retried.json()["code"] == "document_needed"
    replaced = await client.put(f"/api/courses/{course_id}/chapters/{chapter_id}/document", files=photos())
    assert replaced.status_code == 202 and replaced.json()["authoring_stage"] == "transcription"
    await client.app.state.authoring.wait_idle()
    (row,) = (await client.get(f"/api/courses/{course_id}")).json()["chapters"]
    assert row["ready"]


async def test_a_corrected_transcription_is_prepared_again_from_the_pack(client: AsyncClient) -> None:
    fake = use_fake_authoring(client.app, [text("--- page 1 ---\nun\n--- page 2 ---\ndeux"), *AUTHOR, *AUTHOR])
    course_id = await _new_course(client)
    chapter_id = (await _upload(client, course_id, photos(2))).json()["id"]
    await client.app.state.authoring.wait_idle()
    url = f"/api/courses/{course_id}/chapters/{chapter_id}"
    corrected = (await client.get(f"{url}/content")).json()["source_text"] + "\n" + SOURCE
    r = await client.put(f"{url}/source", json={"source_text": corrected})
    assert r.status_code == 202 and r.json()["authoring_stage"] == "pack" and r.json()["page_count"] == 2
    await client.app.state.authoring.wait_idle()
    content = (await client.get(f"{url}/content")).json()
    assert content["version"] == 2 and content["source_text"] == corrected.strip()
    assert (content["source_kind"], content["page_count"]) == ("document", 2)
    assert len(fake.calls) == 5  # one transcription, then pack and curriculum twice: no page read again


async def test_replacing_the_document_keeps_the_lesson_open_until_ready(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [text("--- page 1 ---\nun\n--- page 2 ---\ndeux"), *AUTHOR], delay_s=0.05)
    seed_progress(client.app, client.user["id"], CHAPTER_ID, [], "suites")
    r = await client.put(f"{CH}/document", files=photos(2))
    assert r.status_code == 202 and r.json()["ready"] and r.json()["page_count"] == 2
    assert (await client.get(CH)).status_code == 200  # old content still teaches
    again = await client.put(f"{CH}/document", files=photos())
    assert again.status_code == 409 and again.json()["code"] == "authoring_running"
    await client.app.state.authoring.wait_idle()
    content = (await _content(client))
    assert content["source_kind"] == "document" and content["title"] == "Les fonctions du premier degré"
    assert client.app.state.repos.chapters.uploads(CHAPTER_ID) == [(1, 2)]
    assert client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID) is None


async def test_source_edit_keeps_the_lesson_open_while_generating(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [text(PACK), data(CURRICULUM)], delay_s=0.05)
    seed_progress(client.app, client.user["id"], CHAPTER_ID, [], "suites")
    r = await client.put(f"{CH}/source", json={"source_text": SOURCE})
    assert r.status_code == 202 and r.json()["authoring_state"] == "generating" and r.json()["ready"]
    assert (await client.get(CH)).status_code == 200  # old content still teaches
    again = await client.put(f"{CH}/source", json={"source_text": SOURCE})
    assert again.status_code == 409 and again.json()["code"] == "authoring_running"
    await client.app.state.authoring.wait_idle()
    lesson = (await client.get(CH)).json()
    assert lesson["title"] == "Chapitre 1 — Les fonctions du premier degré"
    assert client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID) is None


async def test_busy_limit_over_http(client: AsyncClient) -> None:
    # Long enough that the first two runs are still in flight when the third upload
    # arrives, even on a loaded machine (0.05 s made this test flaky).
    use_fake_authoring(client.app, [READ, *AUTHOR] * 2, delay_s=0.5)
    course_id = await _new_course(client)
    for _ in range(2):
        assert (await _upload(client, course_id)).status_code == 202
    r = await _upload(client, course_id)
    assert r.status_code == 429 and r.json()["code"] == "authoring_busy"
    await client.app.state.authoring.wait_idle()
    assert len((await client.get(f"/api/courses/{course_id}")).json()["chapters"]) == 2


async def test_limits_are_checked_before_the_document_is_rendered(make_client) -> None:
    from tests.fixtures.fake_llm import FakeLLM

    client, _ = make_client(FakeLLM([]))
    async with client:
        use_fake_authoring(client.app, [])
        rendered: list[int] = []
        documents = client.app.state.documents
        real = documents.prepare

        async def counting(files, first_page=1):  # noqa: ANN001
            rendered.append(len(files))
            return await real(files, first_page)

        documents.prepare = counting
        client.app.state.settings.max_chapters_per_course = 1
        full = await _upload(client, COURSE_ID)  # the seeded course already has its one chapter
        assert full.status_code == 409 and full.json()["code"] == "chapter_limit"
        client.app.state.settings.authoring_concurrent_per_student = 0
        other = await _new_course(client)
        busy = await _upload(client, other)
        assert busy.status_code == 429 and busy.json()["code"] == "authoring_busy"
    assert rendered == []


async def test_authoring_routes_are_owner_only(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [])
    _, other = sign_in(client.app, email="eve@example.be", name="Eve", lesson=False)
    calls = [
        ("post", f"/api/courses/{COURSE_ID}/chapters", {"files": photos()}),
        ("put", f"{CH}/document", {"files": photos()}),
        ("put", f"{CH}/source", {"json": {"source_text": SOURCE}}),
        ("post", f"{CH}/retry", {}),
    ]
    for method, url, kwargs in calls:
        r = await getattr(client, method)(url, headers=other, **kwargs)
        assert r.status_code == 404, (method, url, r.status_code)
    assert client.app.state.authoring.active_count() == 0


async def test_health_reports_active_runs(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [READ, *AUTHOR], delay_s=0.1)
    course_id = await _new_course(client)
    await _upload(client, course_id)
    assert (await client.get("/api/health")).json()["authoring_active"] == 1
    await client.app.state.authoring.wait_idle()
    assert (await client.get("/api/health")).json()["authoring_active"] == 0


async def test_editors_are_refused_while_a_new_version_is_being_prepared(client: AsyncClient) -> None:
    use_fake_authoring(client.app, [text(PACK), data(CURRICULUM)], delay_s=0.1)
    content = await _content(client)
    assert (await client.put(f"{CH}/source", json={"source_text": SOURCE})).status_code == 202
    pack = await client.put(f"{CH}/pack", json={"version": content["version"], "pack": content["pack"]})
    assert pack.status_code == 409 and pack.json()["code"] == "authoring_running"
    path = await client.put(
        f"{CH}/curriculum", json={"version": content["version"], "curriculum": _curriculum_in(content)}
    )
    assert path.status_code == 409 and path.json()["code"] == "authoring_running"
    await client.app.state.authoring.wait_idle()
    assert (await client.get(CH)).json()["title"] == "Chapitre 1 — Les fonctions du premier degré"


async def test_a_turn_cannot_save_progress_after_the_content_changed(make_client) -> None:
    """A turn loaded version N; the student saves an edit (version N+1, progress
    deleted) before the turn's section tool writes. The stale write is refused."""
    from app.domain.content import validate_content
    from app.providers.base import Completed
    from tests.conftest import tool_call
    from tests.fixtures.fake_llm import FakeLLM

    llm = FakeLLM([[tool_call("start_section", {"section_id": "suites"}), Completed()], [Completed()]])
    client, _ = make_client(llm)
    async with client:
        app = client.app
        repos = app.state.repos
        save = repos.progress.save

        def save_after_an_edit(user_id, chapter_id, progress, version=None):  # noqa: ANN001
            chapter = repos.chapters.get_owned(user_id, COURSE_ID, CHAPTER_ID).chapter
            unchanged, _ = validate_content(chapter.pack, chapter.curriculum, app.state.prompts.template("mathematics"), 60_000)
            repos.chapters.adopt_content(CHAPTER_ID, unchanged)
            return save(user_id, chapter_id, progress, version)

        repos.progress.save = save_after_an_edit
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    assert "event: section.start" not in r.text
    assert repos.progress.load(client.user["id"], CHAPTER_ID) is None


# ------------------------------------------------------------ course language (spec 011)


async def test_a_course_without_a_language_is_french(client: AsyncClient) -> None:
    created = (await client.post("/api/courses", json={"name": "Physique", "subject": "sciences"})).json()
    assert created["language"] == "fr"
    assert (await client.get(f"/api/courses/{COURSE_ID}")).json()["language"] == "fr"


async def test_english_is_refused_for_a_subject_that_is_not_offered_in_it(
    client: AsyncClient, french_only: None
) -> None:
    r = await client.post("/api/courses", json={"name": "Physics", "subject": "sciences", "language": "en"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_language"
    assert r.json()["message"] == "Choisis une langue dans la liste."
    await client.patch("/api/auth/me", json={"locale": "en"})  # the account's language, not the course's
    english = await client.post("/api/courses", json={"name": "Physics", "subject": "sciences", "language": "en"})
    assert english.json()["message"] == "Pick a language from the list."


@pytest.mark.parametrize("language", ["de", "", "FR"])
async def test_an_unsupported_language_is_refused(client: AsyncClient, language: str) -> None:
    r = await client.post("/api/courses", json={"name": "X", "subject": "sciences", "language": language})
    assert r.status_code == 422 and r.json()["code"] == "invalid_language"


async def test_an_english_course_carries_its_language_everywhere(client: AsyncClient) -> None:
    created = await client.post("/api/courses", json={"name": "Physics", "subject": "sciences", "language": "en"})
    assert created.status_code == 201 and created.json()["language"] == "en"
    course_id = created.json()["id"]
    assert (await client.get(f"/api/courses/{course_id}")).json()["language"] == "en"
    assert {c["id"]: c["language"] for c in (await client.get("/api/courses")).json()["courses"]} == {
        course_id: "en",
        COURSE_ID: "fr",
    }
    subjects = (await client.get("/api/subjects")).json()["subjects"]
    assert all(s["languages"] == ["fr", "en"] for s in subjects)
    chapter = client.app.state.repos.chapters.create(course_id, "texte", max_chapters=40)
    content = (await client.get(f"/api/courses/{course_id}/chapters/{chapter.id}/content")).json()
    assert content["language"] == "en"


async def test_the_lesson_view_carries_the_courses_language(client: AsyncClient) -> None:
    assert (await client.get(CH)).json()["language"] == "fr"


async def test_the_language_cannot_be_changed(client: AsyncClient) -> None:
    r = await client.patch(f"/api/courses/{COURSE_ID}", json={"name": "M", "language": "en"})
    assert r.status_code == 422
    assert (await client.get(f"/api/courses/{COURSE_ID}")).json()["language"] == "fr"
