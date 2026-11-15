"""The révision routes (spec 020): the page's read, starting one, and a turn."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select, text

from app.db.models import ConversationRow, ProgressRow, RevisionResultRow
from app.domain.errors import ProviderRateLimited
from app.providers.base import Completed, TextDelta
from tests.conftest import CHAPTER_ID, COURSE_ID, FIXTURES, seed_progress
from tests.conftest import sse_frames as frames
from tests.conftest import tool_call as call
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM

CHAPTERS = FIXTURES / "chapters"
SECOND = {"fr": CHAPTERS / "statistique", "en": CHAPTERS / "statistics_en", "nl": CHAPTERS / "statistiek_nl"}
TURN_URL = "/api/revision/turn"


def url(course_id: str = COURSE_ID) -> str:
    return f"/api/courses/{course_id}/revision"


def add_chapter(client, directory: Path | None = None, language: str = "fr") -> str:
    """A second ready chapter in the student's course (statistics by default), at position 2."""
    from scripts.chapter_files import load_chapter_files

    app = client.app
    repos, settings = app.state.repos, app.state.settings
    directory = directory or SECOND[language]
    chapter = repos.chapters.create(
        client.course_id, (directory / "pack.md").read_text(encoding="utf-8"), settings.max_chapters_per_course
    )
    content = load_chapter_files(
        directory, "mathematics", app.state.prompts, chapter.id, settings.pack_max_chars, language  # type: ignore[arg-type]
    )
    repos.chapters.adopt_content(chapter.id, content)
    return chapter.id


def bump(client, chapter_id: str, directory: Path) -> None:
    """A content change on a chapter: its version goes up (and its progress goes)."""
    from scripts.chapter_files import load_chapter_files

    app = client.app
    content = load_chapter_files(
        directory, "mathematics", app.state.prompts, chapter_id, app.state.settings.pack_max_chars
    )
    app.state.repos.chapters.adopt_content(chapter_id, content)


async def start(client, chapter_ids: list[str], course_id: str | None = None) -> dict:
    r = await client.post(url(course_id or client.course_id), json={"chapter_ids": chapter_ids})
    assert r.status_code == 201, r.text
    return r.json()["revision"]


async def turn(client, revision_id: str, message: str | None, course_id: str | None = None) -> tuple[int, str]:
    r = await client.post(
        TURN_URL, json={"course_id": course_id or client.course_id, "revision_id": revision_id, "message": message}
    )
    return r.status_code, r.text


def count(client, table, *where) -> int:
    with client.app.state.repos.courses._factory() as s:  # noqa: SLF001
        return s.scalar(select(func.count()).select_from(table).where(*where)) or 0


# --- the page's read ----------------------------------------------------------------------------------------


async def test_a_course_has_no_revision_until_one_is_started_and_lists_every_chapter(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        second = add_chapter(client)
        unready = client.app.state.repos.chapters.create(client.course_id, "texte du chapitre", 40).id
        seed_progress(client.app, client.user["id"], CHAPTER_ID, ["suites"], "sa-proprietes", skipped=["sa-definition"])
        r = await client.get(url())
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["revision"] is None and body["results"] == []
    assert [c["id"] for c in body["chapters"]] == [CHAPTER_ID, second, unready]
    first = body["chapters"][0]
    assert (first["position"], first["ready"], first["section_count"]) == (1, True, 7)
    assert (first["done_count"], first["skipped_count"]) == (1, 1)
    assert first["sections"][:3] == [
        {"id": "suites", "index": 1, "kind": "teach", "title": "Suites numériques", "state": "done"},
        {"id": "sa-definition", "index": 2, "kind": "teach", "title": "Les suites arithmétiques", "state": "skipped"},
        # An active section that is not done is `todo` in a révision.
        {"id": "sa-proprietes", "index": 3, "kind": "teach", "title": "Somme des termes d'une suite arithmétique", "state": "todo"},
    ]
    assert body["chapters"][1]["position"] == 2 and body["chapters"][1]["done_count"] == 0
    assert body["chapters"][2] == {
        "id": unready, "position": 3, "title": None, "ready": False,
        "section_count": 0, "done_count": 0, "skipped_count": 0, "sections": [],
    }


async def test_the_read_carries_no_beats_pools_or_end_criteria(make_client) -> None:
    """The leak sweep: a section's plan never crosses this wire, nor the pack."""
    llm = FakeLLM([[call("record_result", {"chapter": 1, "section_id": "suites", "outcome": "solid"}), Completed()],
                   [TextDelta("Noté."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        add_chapter(client)
        revision = await start(client, [CHAPTER_ID])
        await turn(client, revision["id"], "acquis")
        body = (await client.get(url())).text
        chapter = client.app.state.repos.chapters.get_owned(client.user["id"], client.course_id, CHAPTER_ID)
    for key in ('"beats"', '"exercises"', '"done_when"', '"goal"', '"pack"', '"tally"', '"count"'):
        assert key not in body, key
    curriculum = chapter.chapter.curriculum
    for section in curriculum["sections"]:
        assert section["done_when"] not in body
        for beat in section.get("beats", []):
            assert beat not in body
        for exercise in section.get("exercises", []):
            assert exercise not in body


# --- starting -----------------------------------------------------------------------------------------------


async def test_starting_returns_an_empty_revision_in_course_order(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        second = add_chapter(client)
        revision = await start(client, [second, CHAPTER_ID, second])
        assert revision["chapter_ids"] == [CHAPTER_ID, second]
        assert revision["entries"] == [] and revision["entry_count"] == 0
        read = (await client.get(url())).json()["revision"]
    assert read["id"] == revision["id"] and read["chapter_ids"] == [CHAPTER_ID, second]


async def test_starting_answers_the_pages_read_from_one_read_of_the_chapters(make_client, monkeypatch) -> None:
    """The POST answers the GET's body (the new révision, every chapter, the latest results), built from the chapters
    the start read once: the page needs no second read."""
    from app.db.repositories import ChapterRepository

    llm = FakeLLM([[_record(1, "suites", "shaky"), Completed()], [TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        second = add_chapter(client)
        first = await start(client, [CHAPTER_ID])
        await turn(client, first["id"], "fragile")
        reads: list[object] = []
        real = ChapterRepository.with_content

        def counted(self, course_id, ids=None):  # noqa: ANN001
            reads.append(ids)
            return real(self, course_id, ids)

        monkeypatch.setattr(ChapterRepository, "with_content", counted)
        r = await client.post(url(), json={"chapter_ids": [second, CHAPTER_ID]})
        assert reads == [None]
        monkeypatch.undo()
        read = (await client.get(url())).json()
    assert r.status_code == 201
    body = r.json()
    assert body == read
    assert body["revision"]["chapter_ids"] == [CHAPTER_ID, second] and body["revision"]["entries"] == []
    assert [c["id"] for c in body["chapters"]] == [CHAPTER_ID, second]
    assert [(x["section_id"], x["outcome"]) for x in body["results"]] == [("suites", "shaky")]


async def test_starting_again_replaces_the_live_revision(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        second = add_chapter(client)
        first = await start(client, [CHAPTER_ID])
        again = await start(client, [second])
        assert (await client.get(url())).json()["revision"]["id"] == again["id"]
        status, body = await turn(client, first["id"], "salut")
        row = client.app.state.repos.conversations.get_revision(client.user["id"], client.course_id, first["id"])
    assert status == 409 and json.loads(body)["code"] == "conversation_closed"
    assert "nouvelle révision" in json.loads(body)["message"]
    assert row is not None and row.closed_reason == "replaced"


async def test_starting_refuses_no_chapter(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        r = await client.post(url(), json={"chapter_ids": []})
    assert r.status_code == 422 and r.json()["code"] == "revision_no_chapter"
    assert r.json()["message"] == "Choisis au moins un chapitre à réviser."


async def test_starting_refuses_a_chapter_of_another_course_or_unknown(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    other, _ = make_client(FakeLLM([]), email="autre@example.be")
    async with other:
        theirs = other.chapter_id
        own_other_course = None
    async with client:
        repos = client.app.state.repos
        course = repos.courses.create(client.user["id"], "Autre cours", "mathematics", max_courses=30)
        own_other_course = repos.chapters.create(course.id, "texte", max_chapters=40).id
        for chapter_ids in ([theirs], [CHAPTER_ID, theirs], ["0" * 32], [own_other_course]):
            r = await client.post(url(), json={"chapter_ids": chapter_ids})
            assert r.status_code == 404, chapter_ids
        assert (await client.get(url())).json()["revision"] is None


async def test_starting_refuses_a_chapter_without_content(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        unready = client.app.state.repos.chapters.create(client.course_id, "texte du chapitre", 40).id
        r = await client.post(url(), json={"chapter_ids": [CHAPTER_ID, unready]})
    assert r.status_code == 409 and r.json()["code"] == "chapter_not_ready"


async def test_starting_refuses_a_selection_over_the_pack_budget(make_client) -> None:
    client, _ = make_client(FakeLLM([]), revision_max_pack_chars=10_000)
    async with client:
        second = add_chapter(client)
        assert (await client.post(url(), json={"chapter_ids": [CHAPTER_ID]})).status_code == 201
        r = await client.post(url(), json={"chapter_ids": [CHAPTER_ID, second]})
        # The live one is still the one-chapter révision: a refused start replaces nothing.
        live = (await client.get(url())).json()["revision"]
    assert r.status_code == 422 and r.json()["code"] == "revision_too_large"
    assert "Choisis-en moins" in r.json()["message"]
    assert live["chapter_ids"] == [CHAPTER_ID]


async def test_the_daily_quota_refuses_a_new_revision(make_client) -> None:
    client, _ = make_client(FakeLLM([]), revision_sessions_per_day=1)
    async with client:
        await start(client, [CHAPTER_ID])
        r = await client.post(url(), json={"chapter_ids": [CHAPTER_ID]})
        # A discussion started today does not count against the révision quota, nor the reverse.
        d = await client.post(f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}/discussion")
    assert r.status_code == 429 and r.json()["code"] == "revision_quota"
    assert d.status_code == 201


async def test_the_errors_follow_the_interface_language(make_client) -> None:
    client, _ = make_client(FakeLLM([]), locale="nl", email="nl@example.be")
    async with client:
        r = await client.post(url(), json={"chapter_ids": []})
    assert r.json()["message"] == "Kies minstens één hoofdstuk om te herhalen."


# --- the lazy close ---------------------------------------------------------------------------------------


async def test_a_revision_whose_chapter_changed_is_closed_when_read(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        second = add_chapter(client)
        revision = await start(client, [CHAPTER_ID, second])
        bump(client, second, SECOND["fr"])
        assert (await client.get(url())).json()["revision"] is None
        row = client.app.state.repos.conversations.get_revision(client.user["id"], client.course_id, revision["id"])
    assert row is not None and row.closed_reason == "content_changed"


async def test_a_turn_on_a_revision_whose_chapter_changed_is_refused(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        second = add_chapter(client)
        revision = await start(client, [CHAPTER_ID, second])
        bump(client, CHAPTER_ID, CHAPTERS / "suites")
        status, body = await turn(client, revision["id"], "salut")
    assert status == 409 and json.loads(body)["code"] == "conversation_closed"
    assert json.loads(body)["message"].startswith("Un des chapitres a changé")


async def test_a_revision_whose_chapter_was_deleted_is_closed(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        second = add_chapter(client)
        await start(client, [CHAPTER_ID, second])
        assert (await client.delete(f"/api/courses/{client.course_id}/chapters/{second}")).status_code == 204
        body = (await client.get(url())).json()
    assert body["revision"] is None
    assert [c["id"] for c in body["chapters"]] == [CHAPTER_ID]


async def test_a_change_to_a_chapter_outside_the_revision_does_not_close_it(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        second = add_chapter(client)
        revision = await start(client, [CHAPTER_ID])
        bump(client, second, SECOND["fr"])
        assert (await client.get(url())).json()["revision"]["id"] == revision["id"]


# --- turns ------------------------------------------------------------------------------------------------


async def test_the_opening_turn_reads_the_chosen_chapters_and_is_stored_once(make_client) -> None:
    llm = FakeLLM([[TextDelta("Bonsoir !"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        second = add_chapter(client)
        seed_progress(client.app, client.user["id"], CHAPTER_ID, ["suites"], None, skipped=["sa-definition"])
        revision = await start(client, [CHAPTER_ID, second])
        status, body = await turn(client, revision["id"], None)
        assert status == 200
        assert [name for name, _ in frames(body)] == ["turn.start", "text.delta", "turn.end"]
        read = (await client.get(url())).json()["revision"]
    assert [(e["kind"], e["text"]) for e in read["entries"]] == [("tutor", "Bonsoir !")] and read["entry_count"] == 1

    assert [t["name"] for t in llm.tools] == ["display_board", "clear_board", "record_result"]
    developer = llm.calls[0]["input"][0]["content"][0]["text"]
    first, second_head = developer.index("# Chapitre 1 — Les suites numériques"), developer.index("# Chapitre 2 — ")
    assert first < second_head < developer.index("## Les chapitres de cette révision") < developer.index("## La révision")
    assert "### Chapitre 1 — « Les suites numériques »" in developer and "`sa-definition` (cours)" in developer
    state = llm.calls[0]["input"][-1]["content"][0]["text"]
    assert "Chapitre 1 — « Les suites numériques » : 1 section(s) faite(s), 1 passée(s)" in state
    assert "- Passées, jamais travaillées avec toi : « 2. Les suites arithmétiques »." in state
    assert state.splitlines()[-1] == "Cette révision : rien de noté pour l'instant."
    # The opening turn reads no learner message.
    assert not any(item.get("role") == "user" for item in llm.calls[0]["input"])


async def test_a_turn_reads_the_chosen_chapters_only_and_the_results_once(make_client, monkeypatch) -> None:
    from app.db.repositories import ChapterRepository, ProgressRepository, RevisionResultRepository

    client, _ = make_client(FakeLLM([[TextDelta("Bonjour"), Completed()]]))
    async with client:
        second = add_chapter(client)
        third = add_chapter(client)
        revision = await start(client, [second])
        calls: dict[str, list] = {"chapters": [], "progress": [], "results": []}
        real = (ChapterRepository.with_content, ProgressRepository.for_chapters, RevisionResultRepository.latest)

        def chapters(self, course_id, ids=None):  # noqa: ANN001
            calls["chapters"].append(None if ids is None else sorted(ids))
            return real[0](self, course_id, ids)

        def progress(self, user_id, ids):  # noqa: ANN001
            calls["progress"].append(sorted(ids))
            return real[1](self, user_id, ids)

        def latest(self, *args, **kwargs):  # noqa: ANN001
            calls["results"].append(kwargs.get("conversation_id"))
            return real[2](self, *args, **kwargs)

        monkeypatch.setattr(ChapterRepository, "with_content", chapters)
        monkeypatch.setattr(ProgressRepository, "for_chapters", progress)
        monkeypatch.setattr(RevisionResultRepository, "latest", latest)
        status, _ = await turn(client, revision["id"], None)
    assert status == 200 and third != second
    assert calls == {"chapters": [[second]], "progress": [[second]], "results": [revision["id"]]}


async def test_an_opening_turn_on_a_started_revision_is_refused(make_client) -> None:
    llm = FakeLLM([[TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        await turn(client, revision["id"], "salut")
        status, body = await turn(client, revision["id"], None)
    assert status == 422
    assert json.loads(body) == {"code": "empty_conversation_expected", "message": "Cette révision a déjà commencé."}


async def test_the_stored_transcript_is_what_the_next_turn_reads(make_client) -> None:
    llm = FakeLLM([[TextDelta("un"), Completed()], [TextDelta("deux"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        await turn(client, revision["id"], "première")
        await turn(client, revision["id"], "deuxième")
        read = (await client.get(url())).json()["revision"]
    texts = json.dumps(llm.calls[1], ensure_ascii=False)
    assert "première" in texts and "un" in texts and "deuxième" in texts
    assert [e["kind"] for e in read["entries"]] == ["learner", "tutor", "learner", "tutor"]


async def test_a_provider_failure_stores_nothing(make_client) -> None:
    client, _ = make_client(ExplodingLLM(ProviderRateLimited()))
    async with client:
        revision = await start(client, [CHAPTER_ID])
        status, body = await turn(client, revision["id"], "salut")
        assert status == 200
        assert [name for name, _ in frames(body)] == ["turn.start", "error", "turn.end"]
        read = (await client.get(url())).json()["revision"]
    assert read["entries"] == [] and read["entry_count"] == 0


class _FailsOnce(FakeLLM):
    """Fails its first round (a provider error before any event), then plays its script."""

    def stream(self, **kwargs):  # type: ignore[override]
        if not getattr(self, "_failed", False):
            self._failed = True
            return ExplodingLLM(ProviderRateLimited()).stream(**kwargs)
        return super().stream(**kwargs)


async def test_a_failed_opening_can_be_sent_again_as_an_opening(make_client) -> None:
    client, _ = make_client(_FailsOnce([[TextDelta("Bonjour"), Completed()]]))
    async with client:
        revision = await start(client, [CHAPTER_ID])
        _, body = await turn(client, revision["id"], None)
        assert "error" in [name for name, _ in frames(body)]
        status, body = await turn(client, revision["id"], None)
        assert status == 200 and "error" not in [name for name, _ in frames(body)]
        assert (await client.get(url())).json()["revision"]["entry_count"] == 1


async def test_a_full_revision_refuses_the_next_turn(make_client) -> None:
    llm = FakeLLM([[TextDelta("ok"), Completed()]])
    client, _ = make_client(llm, discussion_max_entries=2)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        assert (await turn(client, revision["id"], "salut"))[0] == 200
        status, body = await turn(client, revision["id"], "encore")
    assert status == 409 and json.loads(body)["code"] == "conversation_closed"
    assert "nouvelle révision" in json.loads(body)["message"]


async def test_an_unknown_or_foreign_revision_is_not_found(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    other, _ = make_client(FakeLLM([]), email="autre@example.be")
    async with other:
        theirs = await start(other, [other.chapter_id])
        other_course = other.course_id
    async with client:
        assert (await turn(client, "0" * 32, "salut"))[0] == 404
        # Their révision, named under my course or under theirs.
        assert (await turn(client, theirs["id"], "salut"))[0] == 404
        assert (await turn(client, theirs["id"], "salut", course_id=other_course))[0] == 404
        # A discussion's id is not a révision's.
        discussion = (await client.post(f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}/discussion")).json()
        assert (await turn(client, discussion["conversation"]["id"], "salut"))[0] == 404


async def test_every_route_is_the_owners_only(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    other, _ = make_client(FakeLLM([]), email="autre@example.be")
    async with other:
        theirs = other.course_id
    async with client:
        assert (await client.get(url(theirs))).status_code == 404
        assert (await client.post(url(theirs), json={"chapter_ids": [CHAPTER_ID]})).status_code == 404
        assert (await client.get(url("0" * 32))).status_code == 404


async def test_the_routes_need_a_signed_in_student(make_client) -> None:
    client, _ = make_client(FakeLLM([]), anonymous=True)
    async with client:
        assert (await client.get(url())).status_code == 401
        assert (await client.post(url(), json={"chapter_ids": [CHAPTER_ID]})).status_code == 401
        body = {"course_id": COURSE_ID, "revision_id": "0" * 32, "message": "salut"}
        assert (await client.post(TURN_URL, json=body)).status_code == 401


async def test_the_voice_routes_refuse_the_revision_mode(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        lesson = {"course_id": COURSE_ID, "chapter_id": CHAPTER_ID}
        r = await client.post("/api/voice/tool", json={**lesson, "mode": "revision", "name": "record_result",
                                                          "arguments": "{}"})
        s = await client.post("/api/voice/session", json={**lesson, "mode": "revision"})
    assert r.status_code == 422 and s.status_code == 422


# --- the two locks on progress -------------------------------------------------------------------------------


async def test_a_revision_never_writes_progress(make_client) -> None:
    """D4, asserted against the database: no section tool is offered, and none runs."""
    llm = FakeLLM(
        [
            [
                call("start_section", {"section_id": "suites"}, "c1"),
                call("skip_section", {"section_id": "sa-definition"}, "c2"),
                call("complete_section", {"section_id": "suites", "summary": "fait"}, "c3"),
                Completed(),
            ],
            [TextDelta("Ça se passe dans le parcours."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        seed_progress(client.app, client.user["id"], CHAPTER_ID, ["suites"], None)
        before = client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID)
        revision = await start(client, [CHAPTER_ID])
        status, body = await turn(client, revision["id"], "ouvre la section 2")
        assert status == 200
        assert [name for name, _ in frames(body)] == ["turn.start", "text.delta", "turn.end"]
        after = client.app.state.repos.progress.load(client.user["id"], CHAPTER_ID)
        rows = count(client, ProgressRow)
    assert after == before and rows == 1
    outputs = [i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert len(outputs) == 3 and all("n'est pas disponible ici" in o["output"] for o in outputs)


async def test_a_revision_context_has_no_progress_store(make_client) -> None:
    from app.api.deps import revision_context
    from app.services.revision import RevisionService

    client, _ = make_client(FakeLLM([]))
    async with client:
        app = client.app
        revision = await start(client, [CHAPTER_ID])
        user = app.state.repos.users.by_id(client.user["id"])
        course = app.state.repos.courses.get_owned(user.id, client.course_id)
        service = RevisionService(app.state.repos, app.state.settings, app.state.curricula)
        opened = service.open_revision(user.id, course, revision["id"])
        ctx = revision_context(user, course, opened)
    assert ctx.mode == "revision" and ctx.save is None and ctx.curriculum is None and ctx.chapter_id is None
    assert ctx.course_id == client.course_id and ctx.scope is opened.scope
    # The board's checks read the chosen packs.
    assert ctx.pack == opened.scope.chapters[0].pack


# --- record_result ------------------------------------------------------------------------------------------


def _record(chapter: int, section_id: str, outcome: str, call_id: str = "c1"):
    return call("record_result", {"chapter": chapter, "section_id": section_id, "outcome": outcome}, call_id)


async def test_a_noted_result_is_an_event_a_row_and_a_stored_entry(make_client) -> None:
    llm = FakeLLM([[_record(2, "graphiques", "shaky"), Completed()], [TextDelta("On y revient."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        second = add_chapter(client)
        revision = await start(client, [CHAPTER_ID, second])
        status, body = await turn(client, revision["id"], "Pour moi, c'est fragile.")
        assert status == 200
        events = frames(body)
        read = (await client.get(url())).json()
        with client.app.state.repos.courses._factory() as s:  # noqa: SLF001
            rows = s.execute(select(RevisionResultRow)).scalars().all()
            stored = s.scalar(select(ConversationRow.entries).where(ConversationRow.id == revision["id"]))

    assert [name for name, _ in events] == ["turn.start", "revision.result", "text.delta", "turn.end"]
    # The wire carries the chapter's id, the section, the word and the marker: not the number nor the tally.
    assert events[1][1] == {
        "chapter_id": second, "section_id": "graphiques", "outcome": "shaky",
        "marker": "noté : fragile · 2. Représenter une série",
    }
    assert [(r.chapter_id, r.section_id, r.outcome, r.conversation_id, r.course_id) for r in rows] == [
        (second, "graphiques", "shaky", revision["id"], client.course_id)
    ]
    assert stored[1] == {
        "kind": "tool", "name": "record_result",
        "arguments": {"chapter": 2, "section_id": "graphiques", "outcome": "shaky"},
        "ok": True, "error": None, "chapter_id": second, "tally": {"solid": 0, "shaky": 1, "todo": 0},
    }
    entry = read["revision"]["entries"][1]
    assert entry == {
        "kind": "tool", "text": None, "name": "record_result",
        "arguments": {"chapter": 2, "section_id": "graphiques", "outcome": "shaky"},
        "marker": "noté : fragile · 2. Représenter une série",
        "chapter_id": second, "section_id": "graphiques", "outcome": "shaky",
    }
    (result,) = read["results"]
    assert {k: result[k] for k in ("chapter_id", "section_id", "outcome")} == {
        "chapter_id": second, "section_id": "graphiques", "outcome": "shaky"
    }
    # The tool answered the tally, in the course's language.
    output = next(i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output")
    assert json.loads(output["output"]) == {
        "ok": True, "result": "Bilan noté. Cette révision : 0 acquis, 1 fragile(s), 0 à revoir (1 section(s) notée(s)).",
    }


async def test_a_failed_turn_leaves_no_result(make_client) -> None:
    """D6 (amended): the call ran and the tally counted it, then the provider failed: nothing is stored, the call
    nor its result, so the browser's retry cannot leave a result behind that the transcript does not hold."""
    from app.providers.base import Failed

    llm = FakeLLM(
        [
            [_record(1, "suites", "shaky"), Completed()],
            [TextDelta("On y rev"), Failed(code="provider_unavailable", message="boom")],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        status, body = await turn(client, revision["id"], "Pour moi, c'est fragile.")
        read = (await client.get(url())).json()
    assert status == 200 and [name for name, _ in frames(body)][:2] == ["turn.start", "revision.result"]
    assert "error" in [name for name, _ in frames(body)]
    assert count(client, RevisionResultRow) == 0
    assert read["results"] == [] and read["revision"]["entries"] == []


async def test_a_turn_the_learner_left_leaves_no_result(make_client, monkeypatch) -> None:
    from starlette.requests import Request

    checks = 0

    async def gone_after_the_result(self) -> bool:  # noqa: ANN001
        nonlocal checks
        checks += 1
        return checks >= 3  # turn.start, revision.result; then she is gone

    llm = FakeLLM([[_record(1, "suites", "solid"), Completed()], [TextDelta("Bravo, on continue."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        monkeypatch.setattr(Request, "is_disconnected", gone_after_the_result)
        await turn(client, revision["id"], "acquis")
        monkeypatch.undo()
        read = (await client.get(url())).json()
    assert count(client, RevisionResultRow) == 0
    assert read["results"] == [] and read["revision"]["entries"] == []


async def test_a_completed_turn_stores_its_calls_and_their_results_together(make_client) -> None:
    """Two calls in one turn: the tally counts the first at once (the second call answers two sections), and the
    turn's end writes both entries and both rows, in call order."""
    llm = FakeLLM(
        [
            [_record(1, "suites", "solid", "c1"), _record(1, "sa-definition", "todo", "c2"), Completed()],
            [TextDelta("Noté."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        status, _ = await turn(client, revision["id"], "acquis pour la première, à revoir pour la seconde")
        read = (await client.get(url())).json()
        with client.app.state.repos.courses._factory() as s:  # noqa: SLF001
            rows = s.execute(select(RevisionResultRow).order_by(RevisionResultRow.id)).scalars().all()
    assert status == 200
    outputs = [json.loads(i["output"])["result"] for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert outputs == [
        "Bilan noté. Cette révision : 1 acquis, 0 fragile(s), 0 à revoir (1 section(s) notée(s)).",
        "Bilan noté. Cette révision : 1 acquis, 0 fragile(s), 1 à revoir (2 section(s) notée(s)).",
    ]
    assert [(r.section_id, r.outcome, r.conversation_id, r.content_version) for r in rows] == [
        ("suites", "solid", revision["id"], 1),
        ("sa-definition", "todo", revision["id"], 1),
    ]
    assert [e.get("name") for e in read["revision"]["entries"]] == [None, "record_result", "record_result", None]
    assert {(r["section_id"], r["outcome"]) for r in read["results"]} == {("suites", "solid"), ("sa-definition", "todo")}


async def test_a_turn_whose_store_fails_writes_neither_the_transcript_nor_the_results(make_client, monkeypatch) -> None:
    """One transaction: a write that fails after the results were added leaves no row of either kind."""
    from app.db import repositories

    llm = FakeLLM([[_record(1, "suites", "shaky"), Completed()], [TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        real = repositories._conversation  # noqa: SLF001

        def fails_once_extended(row):  # noqa: ANN001
            if row.entry_count:  # the append, after its entries and results were added: before the commit
                raise RuntimeError("disk full")
            return real(row)

        monkeypatch.setattr(repositories, "_conversation", fails_once_extended)
        _, body = await turn(client, revision["id"], "fragile")
        monkeypatch.undo()
        read = (await client.get(url())).json()
    assert "error" in [name for name, _ in frames(body)]
    assert count(client, RevisionResultRow) == 0 and read["revision"]["entries"] == []


async def test_the_marker_follows_the_reader(make_client) -> None:
    llm = FakeLLM([[_record(1, "suites", "todo"), Completed()], [TextDelta("ok"), Completed()]])
    client, _ = make_client(llm, locale="en", email="en@example.be")
    async with client:
        revision = await start(client, [client.chapter_id])
        _, body = await turn(client, revision["id"], "to review")
        entry = (await client.get(url())).json()["revision"]["entries"][1]
    assert frames(body)[1][1]["marker"] == entry["marker"] == "noted: to review · 1. Suites numériques"


async def test_a_replayed_result_answers_what_it_answered_even_after_later_ones(make_client) -> None:
    llm = FakeLLM(
        [
            [_record(1, "suites", "solid"), Completed()],
            [TextDelta("Suivante."), Completed()],
            [_record(1, "sa-definition", "shaky", "c2"), Completed()],
            [TextDelta("Encore une."), Completed()],
            [TextDelta("Bilan ?"), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        await turn(client, revision["id"], "acquis")
        await turn(client, revision["id"], "fragile")
        await turn(client, revision["id"], "on fait le point ?")

    def outputs(call_index: int) -> list[str]:
        return [i["output"] for i in llm.calls[call_index]["input"] if i.get("type") == "function_call_output"]

    first_live, second_live = outputs(1)[-1], outputs(3)[-1]
    assert "1 acquis, 0 fragile(s)" in first_live and "1 acquis, 1 fragile(s)" in second_live
    # Turn 3 replays both stored calls: each says what it said live, byte for byte, not the tally now.
    assert outputs(4) == [first_live, second_live]
    state = llm.calls[4]["input"][-1]["content"][0]["text"]
    assert state.splitlines()[-1] == "Cette révision : 2 section(s) notée(s) — 1 acquis, 1 fragile(s), 0 à revoir."
    assert "« 1. Suites numériques » : acquis" in state and "« 2. Les suites arithmétiques » : fragile" in state


async def test_the_latest_result_per_section_counts(make_client) -> None:
    llm = FakeLLM(
        [
            [_record(1, "suites", "todo", "c1"), _record(1, "suites", "solid", "c2"), Completed()],
            [TextDelta("ok"), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        await turn(client, revision["id"], "à revoir… non, acquis")
        results = (await client.get(url())).json()["results"]
    assert [(r["section_id"], r["outcome"]) for r in results] == [("suites", "solid")]
    second = [i["output"] for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"][-1]
    assert "1 acquis, 0 fragile(s), 0 à revoir (1 section(s) notée(s))" in second


async def test_results_of_an_older_content_version_are_not_read(make_client) -> None:
    llm = FakeLLM([[_record(1, "suites", "shaky"), Completed()], [TextDelta("ok"), Completed()],
                   [TextDelta("Bonsoir"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        await turn(client, revision["id"], "fragile")
        assert len((await client.get(url())).json()["results"]) == 1
        bump(client, CHAPTER_ID, CHAPTERS / "suites")
        assert (await client.get(url())).json()["results"] == []
        again = await start(client, [CHAPTER_ID])
        await turn(client, again["id"], None)
    state = llm.calls[2]["input"][-1]["content"][0]["text"]
    assert "Derniers bilans" not in state
    assert count(client, RevisionResultRow) == 1  # left behind, not deleted


async def test_results_from_an_earlier_revision_are_read_by_the_next(make_client) -> None:
    llm = FakeLLM([[_record(1, "sa-definition", "todo"), Completed()], [TextDelta("ok"), Completed()],
                   [TextDelta("Bonsoir"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        first = await start(client, [CHAPTER_ID])
        await turn(client, first["id"], "à revoir")
        second = await start(client, [CHAPTER_ID])
        await turn(client, second["id"], None)
    state = llm.calls[2]["input"][-1]["content"][0]["text"]
    assert "- Derniers bilans : « 2. Les suites arithmétiques » : à revoir (" in state
    # This révision has noted nothing yet: the tally is its own.
    assert state.splitlines()[-1] == "Cette révision : rien de noté pour l'instant."


async def test_a_result_outside_the_revision_is_refused_in_the_course_language(make_client) -> None:
    llm = FakeLLM(
        [
            [_record(3, "suites", "solid", "c1"), _record(1, "graphiques", "solid", "c2"),
             call("record_result", {"chapter": 1, "section_id": "suites", "outcome": "parfait"}, "c3"), Completed()],
            [TextDelta("ok"), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        add_chapter(client)
        revision = await start(client, [CHAPTER_ID])  # chapter 2 exists but is not in this révision
        status, body = await turn(client, revision["id"], "acquis")
        assert status == 200
        assert "revision.result" not in [name for name, _ in frames(body)]
        assert count(client, RevisionResultRow) == 0
    errors = [json.loads(i["output"])["error"] for i in llm.calls[1]["input"] if i.get("type") == "function_call_output"]
    assert errors[0] == "Le chapitre 3 ne fait pas partie de cette révision. Chapitres de la révision : 1."
    assert errors[1].startswith("La section « graphiques » n'est pas dans le chapitre 1. Sections de ce chapitre : suites, ")
    assert errors[2].startswith("Arguments invalides.")


async def test_an_english_and_a_dutch_course_refuse_in_their_language(make_client) -> None:
    for language, expected in (
        ("en", "Chapter 3 is not part of this revision. Chapters in the revision: 1."),
        ("nl", "Hoofdstuk 3 hoort niet bij deze herhaling. Hoofdstukken van de herhaling: 1."),
    ):
        llm = FakeLLM([[_record(3, "x", "solid"), Completed()], [TextDelta("ok"), Completed()]])
        client, _ = make_client(llm, email=f"{language}-course@example.be", language=language)
        async with client:
            revision = await start(client, [client.chapter_id])
            await turn(client, revision["id"], "ok")
        output = next(i for i in llm.calls[1]["input"] if i.get("type") == "function_call_output")
        assert json.loads(output["output"])["error"] == expected


# --- deletion ---------------------------------------------------------------------------------------------


async def test_results_and_revisions_go_with_the_chapter_and_the_course(make_client) -> None:
    llm = FakeLLM([[_record(1, "suites", "solid", "c1"), _record(2, "graphiques", "todo", "c2"), Completed()],
                   [TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        second = add_chapter(client)
        revision = await start(client, [CHAPTER_ID, second])
        await turn(client, revision["id"], "acquis puis à revoir")
        assert count(client, RevisionResultRow) == 2
        await client.delete(f"/api/courses/{client.course_id}/chapters/{second}")
        assert count(client, RevisionResultRow) == 1  # the chapter's results went with it
        assert count(client, ConversationRow, ConversationRow.mode == "revision") == 1  # closed lazily, kept
        assert (await client.delete(f"/api/courses/{client.course_id}")).status_code == 204
        assert count(client, RevisionResultRow) == 0
        assert count(client, ConversationRow, ConversationRow.mode == "revision") == 0


async def test_results_and_revisions_go_with_the_account(make_client) -> None:
    llm = FakeLLM([[_record(1, "suites", "solid"), Completed()], [TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        revision = await start(client, [CHAPTER_ID])
        await turn(client, revision["id"], "acquis")
        with client.app.state.repos.courses._factory() as s:  # noqa: SLF001
            s.execute(text("delete from users where id = :id"), {"id": client.user["id"]})
            s.commit()
        assert count(client, RevisionResultRow) == 0
        assert count(client, ConversationRow) == 0
