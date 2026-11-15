"""Spec 020 and spec 015 R7: a révision turn is in the usage ledger (role tutor, feature `revision_turn`, the
course and no chapter) and holds metadata only; the révision's own log lines carry ids and counts, never what was
said or noted."""

from __future__ import annotations

from sqlalchemy import text as sql

from app.providers.base import Completed, TextDelta
from tests.conftest import CHAPTER_ID, COURSE_ID, http_client, sign_in, tool_call
from tests.integration.test_usage_ledger import USAGE, Scripted, make_app  # noqa: F401

SECRET = "zq-secret-marker-9952"
CARD_WITH_SECRET = {"kind": "explanation", "title": SECRET, "blocks": [{"type": "text", "text": SECRET}]}


async def test_a_revision_turn_is_in_the_ledger_with_its_course_and_no_content(make_app, db_engine, caplog) -> None:  # noqa: F811
    scripted = Scripted(
        tutor=[
            [
                TextDelta(SECRET),
                tool_call("display_board", {"card": CARD_WITH_SECRET}, "c1"),
                tool_call("record_result", {"chapter": 1, "section_id": "suites", "outcome": "shaky"}, "c2"),
                Completed(usage=USAGE),
            ],
            [TextDelta(SECRET), Completed(usage=USAGE)],
        ]
    )
    app = make_app(scripted)
    student, headers = sign_in(app)
    async with http_client(app, headers) as client:
        with caplog.at_level("DEBUG"):
            revision = (await client.post(f"/api/courses/{COURSE_ID}/revision", json={"chapter_ids": [CHAPTER_ID]})).json()
            r = await client.post(
                "/api/revision/turn",
                json={"course_id": COURSE_ID, "revision_id": revision["revision"]["id"], "message": SECRET},
            )
            assert r.status_code == 200 and "revision.result" in r.text
    await app.state.usage_recorder.drain()
    with db_engine.connect() as conn:
        rows = conn.execute(sql("select * from ai_usage")).mappings().all()
        results = conn.execute(sql("select * from revision_results")).mappings().all()
    assert len(rows) == 2
    assert {(r["user_id"], r["role"], r["feature"], r["course_id"], r["chapter_id"]) for r in rows} == {
        (student["id"], "tutor", "revision_turn", COURSE_ID, None)
    }
    for row in [*rows, *results]:
        assert SECRET not in "|".join(str(v) for v in row.values()), dict(row)
    assert [(r["section_id"], r["outcome"]) for r in results] == [("suites", "shaky")]
    # Every log line of the révision routes: ids, counts, mode.
    assert not [rec for rec in caplog.records if SECRET in rec.getMessage() or SECRET in str(rec.__dict__)]
    turn = next(rec for rec in caplog.records if rec.getMessage() == "turn_complete")
    assert (turn.mode, turn.course_id, turn.chapter_id) == ("revision", COURSE_ID, None)  # type: ignore[attr-defined]
    noted = next(rec for rec in caplog.records if rec.getMessage() == "revision_result")
    assert noted.outcome == "shaky" and noted.section_id == "suites"  # type: ignore[attr-defined]
    # The administrator reads the course's subject for it, no chapter.
    _, admin_headers = sign_in(app, email="root@example.be", name="Root", role="admin", lesson=False)
    async with http_client(app, admin_headers) as admin:
        calls = (await admin.get("/api/admin/usage/calls?limit=50")).json()["calls"]
        assert SECRET not in (await admin.get("/api/admin/usage/calls?limit=50")).text
    assert {c["feature"] for c in calls} == {"revision_turn"}
