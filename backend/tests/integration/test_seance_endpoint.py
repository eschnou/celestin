"""Stored séances over HTTP (spec 018): the parcours turn, the restore, the notebook,
the chapter view, the reset, the reported turn (spoken or stopped) and the voice seed."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text as sql

from app.domain.errors import ProviderRateLimited
from app.providers.base import Completed, TextDelta
from tests.conftest import CARD, CHAPTER_ID, COURSE_ID, LESSON, seed_progress, seed_seance, sign_in
from tests.conftest import sse_frames as frames
from tests.conftest import tool_call as call
from tests.fixtures.fake_llm import ExplodingLLM, FakeLLM
from tests.fixtures.fake_realtime import FakeRealtime

CH = f"/api/courses/{COURSE_ID}/chapters/{CHAPTER_ID}"
SEANCE = f"{CH}/seance"
NOTEBOOK = f"{CH}/notebook"
CHECK = {
    "kind": "check_question",
    "question": "Quel est le premier terme ?",
    "options": [{"id": "a", "text": "$u_1$"}, {"id": "b", "text": "$u_0$"}],
    "correct_option_id": "a",
    "feedback": "On indexe à partir de $u_1$.",
}


async def _chat(client, message: str | None) -> tuple[int, str]:
    r = await client.post("/api/chat", json={**LESSON, "message": message})
    return r.status_code, r.text


async def _seance(client) -> dict | None:
    r = await client.get(SEANCE)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    return r.json()["seance"]


def _rows(app) -> list:
    return app.state.repos.conversations.seances(app.state.repos.users.by_email("lea@example.be").user.id, CHAPTER_ID, 1)


# --- a turn is stored, and read back --------------------------------------------------


async def test_no_seance_until_a_turn_is_stored(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        assert await _seance(client) is None


async def test_the_opening_turn_is_stored_and_restored_with_its_markers(make_client) -> None:
    llm = FakeLLM(
        [
            [TextDelta("On commence."), call("start_section", {"section_id": "suites"}), Completed()],
            [call("display_board", {"card": CARD}), call("propose_next_step", {}), Completed()],
            [TextDelta("Prête ?"), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        status, _ = await _chat(client, None)
        assert status == 200
        seance = await _seance(client)
        (row,) = _rows(client.app)

    assert seance is not None and seance["section_id"] == "suites" and "entry_count" not in seance
    assert row.entry_count == len(seance["entries"]) == 5
    assert seance["entries"] == [
        {"kind": "tutor", "text": "On commence.", "name": None, "arguments": None, "marker": None},
        {
            "kind": "tool", "text": None, "name": "start_section", "arguments": {"section_id": "suites"},
            "marker": "section commencée · 1. Suites numériques", "review": False,
        },
        {
            "kind": "tool", "text": None, "name": "display_board", "arguments": {"card": CARD},
            "marker": "explication affichée",
        },
        {
            "kind": "tool", "text": None, "name": "propose_next_step", "arguments": {},
            "marker": "étape suivante proposée",
        },
        {"kind": "tutor", "text": "Prête ?", "name": None, "arguments": None, "marker": None},
    ]


async def test_the_markers_follow_the_account_and_next_section_comes_from_the_progress(make_client) -> None:
    client, _ = make_client(FakeLLM([]), locale="en")
    async with client:
        user = client.user["id"]
        seed_seance(client.app, user, [
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}, "review": True},
            {"kind": "tool", "name": "complete_section", "arguments": {"section_id": "suites"}},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CARD}, "ok": False, "error": "non"},
            {"kind": "tool", "name": "clear_board", "arguments": {}},
        ], section_id="suites")
        seed_progress(client.app, user, CHAPTER_ID, ["suites"], None)
        entries = (await _seance(client))["entries"]

    start, complete, clear = entries  # the refused call was never shown: not returned
    assert start["marker"] == "review · 1. Suites numériques" and start["review"] is True
    assert "next_section_id" not in start
    assert complete["marker"] == "section completed · 1. Suites numériques"
    assert complete["next_section_id"] == "sa-definition" and "review" not in complete
    assert clear["marker"] == "board cleared" and "review" not in clear and "next_section_id" not in clear


async def test_the_next_turn_reads_the_live_seance_and_the_message(make_client) -> None:
    llm = FakeLLM([[TextDelta("un"), Completed()], [TextDelta("deux"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        user = client.user["id"]
        # An earlier séance of another section: never read again (D4).
        seed_seance(client.app, user, [{"kind": "tutor", "text": "zz-ancienne"}], section_id="suites", closed_reason="done")
        await _chat(client, None)
        await _chat(client, "deuxième")

    second = json.dumps(llm.calls[1]["input"], ensure_ascii=False)
    assert '"un"' in second and "deuxième" in second
    assert "zz-ancienne" not in json.dumps(llm.calls, ensure_ascii=False)


async def test_an_opening_turn_on_a_started_seance_is_refused(make_client) -> None:
    llm = FakeLLM([[TextDelta("Bonjour."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        await _chat(client, None)
        status, body = await _chat(client, None)
    assert status == 422
    assert json.loads(body)["code"] == "empty_conversation_expected"
    assert json.loads(body)["message"] == "Cette séance a déjà commencé."
    assert llm.rounds_used == 1


async def test_a_turn_switching_section_splits_the_seance(make_client) -> None:
    llm = FakeLLM(
        [
            [call("start_section", {"section_id": "suites"}), Completed()],
            [TextDelta("Définition."), Completed()],
            [call("complete_section", {"section_id": "suites", "summary": "vu"}), Completed()],
            [TextDelta("Bravo."), call("start_section", {"section_id": "sa-definition"}), Completed()],
            [TextDelta("Section 2."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        await _chat(client, None)
        await _chat(client, "j'ai compris")
        seance = await _seance(client)
        rows = _rows(client.app)

    assert [(r.section_id, r.closed_reason) for r in rows] == [("suites", "done"), ("sa-definition", None)]
    assert [e.get("text") for e in rows[0].entries if e["kind"] != "tool"] == ["Définition.", "j'ai compris", "Bravo."]
    assert seance["section_id"] == "sa-definition"
    assert [e.get("name") or e["kind"] for e in seance["entries"]] == ["start_section", "tutor"]


# --- failures and cancellations (D7) -----------------------------------------------------


async def test_a_provider_failure_stores_nothing(make_client) -> None:
    client, _ = make_client(ExplodingLLM(ProviderRateLimited()))
    async with client:
        status, body = await _chat(client, "salut")
        assert status == 200 and [n for n, _ in frames(body)] == ["turn.start", "error", "turn.end"]
        assert await _seance(client) is None


async def test_a_failure_after_some_text_stores_nothing(make_client) -> None:
    from app.providers.base import Failed

    llm = FakeLLM([[TextDelta("début"), Failed(code="provider_unavailable", message="boom")]])
    client, _ = make_client(llm)
    async with client:
        await _chat(client, "salut")
        assert await _seance(client) is None


async def test_a_turn_the_learner_left_stores_nothing(make_client, monkeypatch) -> None:
    """D7 (amended): a stream that ends early stores nothing on its own, whatever ended it. A turn
    the learner stopped is reported by the browser (`/api/seance/report`); a dropped connection is a
    turn the browser retries, the same message again."""
    from starlette.requests import Request

    checks = 0

    async def gone_after_three(self) -> bool:  # noqa: ANN001
        nonlocal checks
        checks += 1
        return checks >= 4  # turn.start, the text, the board; then she is gone

    llm = FakeLLM(
        [
            [TextDelta("Regarde."), call("display_board", {"card": CARD}), Completed()],
            [TextDelta("jamais dit"), Completed()],
            [TextDelta("Voilà."), Completed()],  # the retry
        ]
    )
    client, _ = make_client(llm)
    async with client:
        monkeypatch.setattr(Request, "is_disconnected", gone_after_three)
        await _chat(client, "montre-moi")
        monkeypatch.undo()
        assert await _seance(client) is None
        # The browser's retry: the same message again, read once by the model and stored once.
        status, _ = await _chat(client, "montre-moi")
        seance = await _seance(client)

    assert status == 200
    assert json.dumps(llm.calls[-1]["input"], ensure_ascii=False).count("montre-moi") == 1
    assert [(e["kind"], e["text"]) for e in seance["entries"]] == [("learner", "montre-moi"), ("tutor", "Voilà.")]


async def test_an_opening_turn_that_failed_can_be_sent_again(make_client) -> None:
    from app.providers.base import Failed

    llm = FakeLLM(
        [
            [TextDelta("Bonj"), Failed(code="provider_unavailable", message="boom")],
            [TextDelta("Bonjour."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        await _chat(client, None)
        status, _ = await _chat(client, None)  # not `422 seance_started`: nothing was stored
        seance = await _seance(client)
    assert status == 200 and [e["text"] for e in seance["entries"]] == ["Bonjour."]


async def test_a_completed_turn_is_not_stored_twice(make_client) -> None:
    llm = FakeLLM([[TextDelta("Bonjour."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        await _chat(client, None)
        assert len((await _seance(client))["entries"]) == 1
        assert _rows(client.app)[0].entry_count == 1


# --- the reprise note (D5) ------------------------------------------------------------------


def _brief_output(call_input: list) -> str:
    outputs = [i for i in call_input if i.get("type") == "function_call_output"]
    return json.loads(outputs[-1]["output"])["result"]


async def test_a_section_taken_up_again_gets_the_note_and_the_replay_repeats_it(make_client) -> None:
    llm = FakeLLM(
        [
            [call("start_section", {"section_id": "suites"}), Completed()],
            [TextDelta("Reprenons."), Completed()],
            [TextDelta("Bien."), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        user = client.user["id"]
        seed_progress(client.app, user, CHAPTER_ID, [], "suites")
        seed_seance(client.app, user, [
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}, "review": False},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CARD}},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CHECK}},
        ], section_id="suites", closed_reason="left")
        await _chat(client, None)
        await _chat(client, "oui")

    live = _brief_output(llm.calls[1]["input"])
    assert live.endswith(
        "Cartes déjà montrées, dans l'ordre :\n"
        "- explication : Somme d'une SG\n"
        "- question de compréhension : Quel est le premier terme ?\n"
        "Dis en une phrase à ton élève où vous en étiez, puis continue après la dernière carte, "
        "sans reprendre la section depuis le début."
    )
    assert _brief_output(llm.calls[2]["input"]) == live  # replayed on the next turn, byte for byte


def _start_output(call_input: list) -> str:
    """The output answering the first `start_section` call of a request's input."""
    start = next(i for i in call_input if i.get("type") == "function_call" and i["name"] == "start_section")
    output = next(
        i for i in call_input if i.get("type") == "function_call_output" and i["call_id"] == start["call_id"]
    )
    return json.loads(output["output"])["result"]


async def test_a_start_replays_as_it_was_once_its_section_is_completed(make_client) -> None:
    """D5: the replay reads what the call was at the time (its stored `review`), not the
    section's state now. Completing the section in the same séance must not turn the
    replayed brief into a review brief, nor drop its reprise note."""
    llm = FakeLLM(
        [
            [call("start_section", {"section_id": "suites"}), Completed()],
            [TextDelta("Reprenons."), Completed()],
            [call("complete_section", {"section_id": "suites", "summary": "Vu."}), Completed()],
            [TextDelta("Bravo."), Completed()],
            [TextDelta("Et maintenant ?"), Completed()],
        ]
    )
    client, _ = make_client(llm)
    async with client:
        user = client.user["id"]
        seed_progress(client.app, user, CHAPTER_ID, [], "suites")
        seed_seance(client.app, user, [
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}, "review": False},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CARD}},
        ], section_id="suites", closed_reason="left")
        await _chat(client, None)
        await _chat(client, "j'ai fini")
        await _chat(client, "suite")
        progress = (await client.get(SEANCE)).json()["progress"]

    live = _brief_output(llm.calls[1]["input"])
    assert "Reprise" in live and progress["done"] == ["suites"]
    assert _start_output(llm.calls[4]["input"]) == live


async def test_without_an_earlier_seance_the_brief_has_no_note(make_client) -> None:
    llm = FakeLLM([[call("start_section", {"section_id": "suites"}), Completed()], [Completed()]])
    client, _ = make_client(llm)
    async with client:
        await _chat(client, None)
    assert "Reprise" not in _brief_output(llm.calls[1]["input"])


async def test_the_note_is_the_same_whatever_the_interface_language(make_client) -> None:
    """The model input wall holds for the note: it takes the course language only."""
    seen = []
    for locale in ("fr", "en"):
        llm = FakeLLM([[call("start_section", {"section_id": "suites"}), Completed()], [Completed()]])
        client, _ = make_client(llm, email=f"{locale}@example.be", locale=locale)
        async with client:
            user = client.user["id"]
            seed_progress(client.app, user, client.chapter_id, [], "suites")
            seed_seance(client.app, user, [{"kind": "tool", "name": "display_board", "arguments": {"card": CARD}}],
                        section_id="suites", chapter_id=client.chapter_id, closed_reason="left")
            await client.post("/api/chat", json={"course_id": client.course_id, "chapter_id": client.chapter_id})
        seen.append(_brief_output(llm.calls[1]["input"]))
    assert seen[0] == seen[1] and "Reprise" in seen[0]


async def test_review_is_never_sent_to_the_model(make_client) -> None:
    llm = FakeLLM([[Completed()]])
    client, _ = make_client(llm)
    async with client:
        seed_seance(client.app, client.user["id"], [
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}, "review": True},
        ], section_id="suites")
        await _chat(client, "salut")
    call_item = next(i for i in llm.calls[0]["input"] if i.get("type") == "function_call")
    assert call_item["arguments"] == '{"section_id": "suites"}' and "review" not in json.dumps(call_item)


# --- the notebook, the chapter view, the reset ------------------------------------------------


async def test_the_notebook_and_the_chapter_view(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        user = client.user["id"]
        seed_seance(client.app, user, [
            {"kind": "learner", "text": "bonjour"},
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "sa-definition"}},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CARD}},
            {"kind": "tutor", "text": "Tu vois ?"},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CHECK}, "ok": False, "error": "x"},
        ], section_id="sa-definition", closed_reason="left")
        seed_seance(client.app, user, [
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CHECK}},
        ], section_id="suites")
        notebook = await client.get(NOTEBOOK)
        read = (await client.get(SEANCE)).json()
        view = (await client.get(CH)).json()

    assert notebook.status_code == 200 and notebook.headers["cache-control"] == "no-store"
    assert notebook.json() == {
        "sections": [
            {"section_id": "suites", "items": [{"kind": "card", "card": CHECK}]},
            {
                "section_id": "sa-definition",
                "items": [
                    {"kind": "learner", "text": "bonjour"},
                    {"kind": "card", "card": CARD},
                    {"kind": "tutor", "text": "Tu vois ?"},
                ],
            },
        ]
    }
    # The card counts travel with the séance, read with its progress; the chapter view no longer carries them.
    assert read["seances"] == {"suites": {"cards": 1}, "sa-definition": {"cards": 1}}
    assert read["progress"] == {"done": [], "active": None, "skipped": []}
    assert "seances" not in view


async def test_an_empty_notebook(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        assert (await client.get(NOTEBOOK)).json() == {"sections": []}
        assert (await client.get(SEANCE)).json() == {"seance": None, "progress": {"done": [], "active": None, "skipped": []}, "seances": {}}


async def test_a_content_change_hides_the_old_seances(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        seed_seance(client.app, client.user["id"], [
            {"kind": "tool", "name": "display_board", "arguments": {"card": CARD}},
        ], section_id="suites")
        with client.app.state.engine.begin() as conn:
            conn.execute(sql("update chapters set content_version = content_version + 1"))
        assert await _seance(client) is None
        assert (await client.get(NOTEBOOK)).json() == {"sections": []}
        assert (await client.get(SEANCE)).json()["seances"] == {}


async def test_reset_deletes_the_seances_and_keeps_the_discussion(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        user = client.user["id"]
        seed_seance(client.app, user, [{"kind": "tutor", "text": "x"}], section_id="suites", closed_reason="done")
        seed_seance(client.app, user, [{"kind": "tutor", "text": "y"}], section_id="sa-definition")
        discussion = (await client.post(f"{CH}/discussion")).json()["conversation"]
        assert (await client.delete(f"{CH}/progress")).status_code == 204
        assert await _seance(client) is None
        assert (await client.get(NOTEBOOK)).json() == {"sections": []}
        assert (await client.get(f"{CH}/discussion")).json()["conversation"]["id"] == discussion["id"]


async def test_a_discussion_and_a_seance_live_side_by_side(make_client) -> None:
    llm = FakeLLM([[TextDelta("zz-mot-du-parcours"), Completed()], [TextDelta("discussion"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        await _chat(client, None)
        conversation = (await client.post(f"{CH}/discussion")).json()["conversation"]
        r = await client.post("/api/discussion/turn", json={**LESSON, "conversation_id": conversation["id"], "message": "salut"})
        assert r.status_code == 200
        seance = await _seance(client)
        stored = (await client.get(f"{CH}/discussion")).json()["conversation"]
    assert [e["text"] for e in seance["entries"]] == ["zz-mot-du-parcours"]
    assert [e["text"] for e in stored["entries"]] == ["salut", "discussion"]
    # The discussion's model input held nothing of the séance.
    assert "zz-mot-du-parcours" not in json.dumps(llm.calls[1]["input"], ensure_ascii=False)


# --- the reported turn (D7, D10) and the voice seed ---------------------------------------------------------


async def test_a_reported_parcours_turn_is_stored_with_the_split_rule(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        user = client.user["id"]
        seed_seance(client.app, user, [{"kind": "tutor", "text": "Bonjour."}], section_id="suites")
        r = await client.post("/api/seance/report", json={**LESSON, "entries": [
            {"kind": "learner", "text": "je passe à la suite"},
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "sa-definition"}, "review": False},
            {"kind": "tutor", "text": "Allons-y."},
        ]})
        assert r.status_code == 204
        rows = _rows(client.app)
    assert [(row.section_id, row.closed_reason) for row in rows] == [("suites", "left"), ("sa-definition", None)]
    assert rows[0].entries[-1] == {"kind": "learner", "text": "je passe à la suite"}
    assert rows[1].entries[0]["review"] is False


REPORT = "/api/seance/report"


async def _report(client, entries: list[dict]):
    return await client.post(REPORT, json={**LESSON, "entries": entries})


async def test_a_reported_turn_is_validated(make_client) -> None:
    from app.api.schemas.chat import REPORTED_ARGUMENTS_MAX, REPORTED_TEXT_MAX

    client, _ = make_client(FakeLLM([]))
    async with client:
        refused = {
            "a review on a board call": [{"kind": "tool", "name": "display_board", "arguments": {}, "review": True}],
            "a recorded next section on a start": [
                {"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}, "next_section_id": None}
            ],
            "a recorded active section on a completion": [
                {"kind": "tool", "name": "complete_section", "arguments": {"section_id": "suites"},
                 "active_section_id": "suites"}
            ],
            "no entries": [],
            "a card that is not a card": [{"kind": "tool", "name": "display_board", "arguments": {"card": {"kind": "x"}}}],
            "a board call without a card": [{"kind": "tool", "name": "display_board", "arguments": {}}],
            "a text over the limit": [{"kind": "tutor", "text": "a" * (REPORTED_TEXT_MAX + 1)}],
            "arguments over the limit": [
                {"kind": "tool", "name": "clear_board", "arguments": {"x": "a" * REPORTED_ARGUMENTS_MAX}}
            ],
        }
        for label, entries in refused.items():
            r = await _report(client, entries)
            assert r.status_code == 422, label
        invalid = {
            "an unknown section": [{"kind": "tool", "name": "start_section", "arguments": {"section_id": "zz-nope"}}],
            "a completion of an unknown section": [
                {"kind": "tool", "name": "complete_section", "arguments": {"section_id": "x" * 40}}
            ],
            "a section id that is not a string": [
                {"kind": "tool", "name": "start_section", "arguments": {"section_id": 3}}
            ],
            "a tool the parcours does not offer": [{"kind": "tool", "name": "reveal_answer", "arguments": {}}],
            "a skip that recorded an unknown next section": [
                {"kind": "tool", "name": "skip_section", "arguments": {"section_id": "suites"},
                 "next_section_id": "zz-nope", "active_section_id": None}
            ],
            "a skip that recorded an unknown active section": [
                {"kind": "tool", "name": "skip_section", "arguments": {"section_id": "suites"},
                 "next_section_id": None, "active_section_id": "zz-nope"}
            ],
            "a completion that recorded an unknown next section": [
                {"kind": "tool", "name": "complete_section", "arguments": {"section_id": "suites"},
                 "next_section_id": "zz-nope"}
            ],
        }
        for label, entries in invalid.items():
            r = await _report(client, [{"kind": "learner", "text": "ok"}, *entries])
            assert r.status_code == 422 and r.json()["code"] == "seance_report_invalid", label
            assert r.json()["message"] == "Cet échange ne correspond pas à ce chapitre et n'a pas été enregistré."
        assert _rows(client.app) == []  # nothing of a refused report is kept, not even its valid entries
        # A real card passes, the one the lesson's board was sent.
        assert (await _report(client, [{"kind": "tool", "name": "display_board", "arguments": {"card": CARD}}])).status_code == 204


async def test_a_reported_skip_keeps_what_it_answered_and_replays_it(make_client) -> None:
    """Spec 019: a spoken skip is reported with the ids its event carried; the next turn replays
    the call from them, though the student has started the skipped section since."""
    llm = FakeLLM([[TextDelta("On reprend."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        r = await _report(client, [
            {"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}, "review": False},
            {"kind": "tool", "name": "skip_section", "arguments": {"section_id": "suites"},
             "next_section_id": "sa-definition", "active_section_id": None},
        ])
        assert r.status_code == 204
        seed_progress(client.app, client.user["id"], CHAPTER_ID, [], "suites")  # taken up again since
        await client.post("/api/chat", json={**LESSON, "message": "finalement je la fais"})
    assert _rows(client.app)[0].entries[1] == {
        "kind": "tool", "name": "skip_section", "arguments": {"section_id": "suites"}, "ok": True, "error": None,
        "next_section_id": "sa-definition", "active_section_id": None,
    }
    outputs = [i for i in llm.calls[0]["input"] if i.get("type") == "function_call_output"]
    assert json.loads(outputs[1]["output"])["result"] == (
        "Section passée. Prochaine section : « 2. Les suites arithmétiques » (cours), id : sa-definition."
    )


async def test_a_start_reported_without_its_review_gets_it_from_the_progress(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        seed_progress(client.app, client.user["id"], CHAPTER_ID, ["suites"], None)
        r = await _report(client, [{"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"}}])
        assert r.status_code == 204
        start = (await _seance(client))["entries"][0]
    assert _rows(client.app)[0].entries[0]["review"] is True
    assert start["review"] is True and start["marker"].startswith("révision")


async def test_reported_turns_are_rate_limited(make_client) -> None:
    client, _ = make_client(FakeLLM([]), seance_reports_per_hour=2)
    async with client:
        codes = [(await _report(client, [{"kind": "learner", "text": f"m{i}"}])).status_code for i in range(3)]
        last = await _report(client, [{"kind": "learner", "text": "encore"}])
    assert codes == [204, 204, 429]
    assert last.json()["code"] == "seance_report_rate"
    assert [e["text"] for e in _rows(client.app)[0].entries] == ["m0", "m1"]


async def test_a_chapter_at_the_row_cap_refuses_a_report_but_not_a_model_turn(make_client) -> None:
    llm = FakeLLM([[TextDelta("On continue."), Completed()]])
    client, _ = make_client(llm, seance_max_rows=2)
    async with client:
        user = client.user["id"]
        seed_seance(client.app, user, [{"kind": "tutor", "text": "a"}], section_id="suites", closed_reason="left")
        seed_seance(client.app, user, [{"kind": "tutor", "text": "b"}], section_id="suites")
        r = await _report(client, [{"kind": "learner", "text": "un mot"}])
        assert r.status_code == 409 and r.json()["code"] == "seance_full"
        status, _ = await _chat(client, "un mot")
        seance = await _seance(client)
    assert status == 200
    assert [e["text"] for e in seance["entries"]] == ["b", "un mot", "On continue."]


async def test_a_stopped_turn_is_reported_then_the_next_turn_reads_it(make_client) -> None:
    """D7: what the browser kept of a stopped turn, then her next message: the model reads both,
    in that order, and the séance holds each once."""
    llm = FakeLLM([[TextDelta("Ensuite."), Completed()]])
    client, _ = make_client(llm)
    async with client:
        user = client.user["id"]
        seed_seance(client.app, user, [{"kind": "tool", "name": "start_section", "arguments": {"section_id": "suites"},
                                         "review": False}], section_id="suites")
        r = await _report(client, [
            {"kind": "learner", "text": "montre-moi"},
            {"kind": "tutor", "text": "Regarde bien ce"},
            {"kind": "tool", "name": "display_board", "arguments": {"card": CARD}},
        ])
        assert r.status_code == 204
        await _chat(client, "stop, autre chose")
        seance = await _seance(client)
    read = json.dumps(llm.calls[0]["input"], ensure_ascii=False)
    assert read.index("montre-moi") < read.index("Regarde bien ce") < read.index("stop, autre chose")
    assert [(e["kind"], e["text"] or e["name"]) for e in seance["entries"]] == [
        ("tool", "start_section"),
        ("learner", "montre-moi"),
        ("tutor", "Regarde bien ce"),
        ("tool", "display_board"),
        ("learner", "stop, autre chose"),
        ("tutor", "Ensuite."),
    ]


async def test_a_discussions_spoken_turn_gets_the_same_entry_checks(make_client) -> None:
    from app.api.schemas.chat import REPORTED_TEXT_MAX

    client, _ = make_client(FakeLLM([]))
    async with client:
        conversation = (await client.post(f"{CH}/discussion")).json()["conversation"]
        url, base = "/api/discussion/voice/turn", {**LESSON, "conversation_id": conversation["id"]}
        bad_card = await client.post(url, json={**base, "entries": [
            {"kind": "tool", "name": "display_board", "arguments": {"card": {"kind": "x"}}}]})
        too_long = await client.post(url, json={**base, "entries": [{"kind": "tutor", "text": "a" * (REPORTED_TEXT_MAX + 1)}]})
        fine = await client.post(url, json={**base, "entries": [
            {"kind": "learner", "text": "salut"}, {"kind": "tool", "name": "display_board", "arguments": {"card": CARD}}]})
    assert bad_card.status_code == 422 and too_long.status_code == 422 and fine.status_code == 204


async def test_a_parcours_voice_session_is_seeded_from_the_live_seance(make_voice_client) -> None:
    realtime = FakeRealtime()
    async with make_voice_client(realtime) as client:
        user = client.user["id"]
        seed_seance(client.app, user, [{"kind": "tutor", "text": "zz-dernier-mot"}], section_id="suites")
        r = await client.post("/api/voice/session", json=LESSON)
    body = r.json()
    assert r.status_code == 201 and body["opening"] is False
    assert "zz-dernier-mot" in json.dumps(body["seed"], ensure_ascii=False)


# --- ownership, readiness, roles and what never leaves -------------------------------------------


async def test_another_students_chapter_is_a_404_on_every_new_route(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        _, other = sign_in(client.app, email="bob@example.be", name="Bob", lesson=False)
        seed_seance(client.app, client.user["id"], [{"kind": "tutor", "text": "x"}], section_id="suites")
        calls = [
            ("get", SEANCE, None),
            ("get", NOTEBOOK, None),
            ("post", "/api/seance/report", {**LESSON, "entries": [{"kind": "tutor", "text": "x"}]}),
            ("post", "/api/chat", {**LESSON, "message": "salut"}),
            ("post", "/api/voice/session", LESSON),
        ]
        for method, url, body in calls:
            kwargs = {"json": body} if body is not None else {}
            r = await getattr(client, method)(url, headers=other, **kwargs)
            assert r.status_code == 404, (url, r.status_code)
        assert _rows(client.app)[0].entry_count == 1


async def test_a_chapter_without_content_is_not_ready(make_client) -> None:
    client, _ = make_client(FakeLLM([]))
    async with client:
        repos = client.app.state.repos
        bare = repos.chapters.create(COURSE_ID, "texte collé", max_chapters=40)
        base = f"/api/courses/{COURSE_ID}/chapters/{bare.id}"
        for r in (
            await client.get(f"{base}/seance"),
            await client.get(f"{base}/notebook"),
            await client.post("/api/seance/report", json={"course_id": COURSE_ID, "chapter_id": bare.id,
                                                              "entries": [{"kind": "tutor", "text": "x"}]}),
        ):
            assert r.status_code == 409 and r.json()["code"] == "chapter_not_ready"


async def test_the_routes_need_a_signed_in_student(make_client) -> None:
    client, _ = make_client(FakeLLM([]), anonymous=True)
    async with client:
        assert (await client.get(SEANCE)).status_code == 401
        assert (await client.get(NOTEBOOK)).status_code == 401
        assert (await client.post("/api/seance/report", json={**LESSON, "entries": []})).status_code == 401


@pytest.mark.parametrize("url", [SEANCE, NOTEBOOK, CH])
async def test_the_path_internals_never_cross_the_new_bodies(make_client, url: str) -> None:
    """Beats, exercise pools and `done_when` stay on the server, whatever is stored."""
    llm = FakeLLM([[call("start_section", {"section_id": "suites"}), Completed()], [TextDelta("ok"), Completed()]])
    client, _ = make_client(llm)
    async with client:
        await _chat(client, None)
        seed_seance(client.app, client.user["id"], [{"kind": "tool", "name": "display_board", "arguments": {"card": CARD}}],
                    section_id="sa-definition", closed_reason="left")
        text = (await client.get(url)).text
    for internal in ("beats", "exercises", "done_when", "Terminée", "6.1.1", "Déroulé"):
        assert internal not in text, internal


async def test_seance_logs_carry_ids_and_counts_never_content(make_client, caplog) -> None:
    secret = "zq-secret-seance-4411"
    card = {**CARD, "title": secret}
    llm = FakeLLM(
        [
            [TextDelta(secret), call("start_section", {"section_id": "suites"}), Completed()],
            [call("display_board", {"card": card}), Completed()],
            [TextDelta(secret), Completed()],
            [call("start_section", {"section_id": "sa-definition"}), Completed()],
            [Completed()],
        ]
    )
    client, _ = make_client(llm, discussion_max_entries=4)
    async with client:
        with caplog.at_level("DEBUG"):
            await _chat(client, None)
            await _chat(client, secret)  # rolls the full séance over, then splits it
            await client.get(SEANCE)
            await client.get(NOTEBOOK)
            await client.post("/api/seance/report", json={**LESSON, "entries": [{"kind": "learner", "text": secret}]})
    names = {r.getMessage() for r in caplog.records}
    assert {"seance_stored", "seance_capped", "seance_notebook", "seance_reported"} <= names
    for record in caplog.records:
        if record.getMessage().startswith(("seance_", "conversation_", "progress_")):
            assert secret not in str(record.__dict__), record.getMessage()
