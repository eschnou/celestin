"""Spec 015 R7: the ledger holds metadata only. One call of each feature with a distinctive string in everything
a student writes, says, uploads or a provider answers; none of it may be in a stored row or in the recorder's logs."""

from __future__ import annotations

import pytest
from sqlalchemy import text as sql

from app.db.models import AiUsageRow
from app.providers.base import Completed, TextDelta
from tests.conftest import LESSON, http_client, sign_in, tool_call
from tests.fixtures.documents import page_image
from tests.fixtures.fake_completion import data, text
from tests.integration.test_usage_ledger import SOURCE, USAGE, Scripted, make_app  # noqa: F401
from tests.unit.test_authoring_agent import CURRICULUM, PACK

SECRET = "zq-secret-marker-7731"
# What the ledger may hold: ids, enumerations, a model, a host, numbers, a time. Nothing else is a column.
COLUMNS = {
    "id", "created_at", "user_id", "course_id", "chapter_id", "correlation_id", "role", "feature", "model",
    "provider", "status", "error_code", "latency_ms", "ttft_ms", "input_tokens", "cached_tokens",
    "output_tokens", "reasoning_tokens", "input_audio_tokens", "output_audio_tokens", "audio_seconds", "cost_usd",
}
CARD_WITH_SECRET = {"kind": "explanation", "title": SECRET, "blocks": [{"type": "text", "text": SECRET}]}


def test_the_table_has_exactly_the_documented_columns() -> None:
    """A new column — above all a text one — fails here, and has to be argued for in the spec."""
    assert {c.name for c in AiUsageRow.__table__.columns} == COLUMNS


async def test_nothing_a_student_wrote_said_or_uploaded_reaches_the_ledger(make_app, db_engine, caplog) -> None:  # noqa: F811
    scripted = Scripted(
        tutor=[
            [tool_call("display_board", {"card": CARD_WITH_SECRET}), Completed(usage=USAGE)],
            [TextDelta(SECRET), Completed(usage=USAGE)],
            [TextDelta(SECRET), Completed(usage=USAGE)],
        ],
        authoring=[text(PACK), data(CURRICULUM)],
        transcription=[text(f"--- page 1 ---\n{SOURCE}\n{SECRET}"), text(SECRET), Exception(SECRET)],
    )
    app = make_app(scripted)
    scripted.transcriber._text = SECRET  # noqa: SLF001
    student, headers = sign_in(app)
    async with http_client(app, headers) as client:
        with caplog.at_level("DEBUG"):
            # A turn, with the secret in the transcript and in a tool call.
            await client.post("/api/chat", json={**LESSON, "history": []})
            # A document, named after the secret, whose transcription holds it.
            course = (await client.post("/api/courses", json={"name": SECRET, "subject": "mathematics"})).json()["id"]
            files = [("files", (f"{SECRET}.jpg", page_image(text=SECRET), "image/jpeg"))]
            await client.post(f"/api/courses/{course}/chapters", files=files)
            await app.state.authoring.wait_idle()
            # Work, read from a photo named after it; then a recording; then a provider that fails with it.
            await client.post(f"/api/courses/{course}/work", files={"photo": (f"{SECRET}.jpg", page_image(text=SECRET), "image/jpeg")})
            await client.post("/api/dictation", files={"audio": (f"{SECRET}.webm", SECRET.encode(), "audio/webm")}, data={"language": "fr"})
            with pytest.raises(Exception, match=SECRET):  # an unexpected error of the provider's, message and all
                await client.post(f"/api/courses/{course}/work", files={"photo": (f"{SECRET}.jpg", page_image(text=SECRET), "image/jpeg")})
    await app.state.usage_recorder.drain()
    with db_engine.connect() as conn:
        rows = conn.execute(sql("select * from ai_usage")).mappings().all()
    assert len(rows) >= 7, "every feature must have produced a row for this test to mean anything"
    assert {r["feature"] for r in rows} >= {"tutor_turn", "authoring", "document_reading", "work_reading", "dictation"}
    assert {r["user_id"] for r in rows} == {student["id"]}
    for row in rows:
        assert SECRET not in "|".join(str(v) for v in row.values()), dict(row)
    # What the administrator reads: the course is named after the secret too, and none of it comes back.
    _, admin_headers = sign_in(app, email="root@example.be", name="Root", role="admin", lesson=False)
    async with http_client(app, admin_headers) as admin:
        for path in ("/summary", "/users", f"/users/{student['id']}", "/calls?limit=200"):
            r = await admin.get("/api/admin/usage" + path)
            assert r.status_code == 200 and SECRET not in r.text, path
        calls = (await admin.get("/api/admin/usage/calls?limit=200")).json()["calls"]
    assert len(calls) == len(rows) and {c["course_subject"] for c in calls} >= {"mathematics"}
    recorder_logs = [r for r in caplog.records if r.name.startswith("app.providers.recording")]
    assert all(SECRET not in str(r.__dict__) for r in recorder_logs)


async def test_the_other_features_hold_no_content_either(settings, db_engine, caplog) -> None:
    """A discussion turn, a voice session and the admin's live test, with the marker in what the student says, in
    what a provider says when it fails, and in every log line the three routes write."""
    from app.providers.base import Failed
    from app.main import create_app
    from tests.fixtures.fake_clients import PassingFactory
    from tests.fixtures.fake_probe import FakeProbe

    scripted = Scripted(tutor=[[TextDelta(SECRET), Completed(usage=USAGE)]])
    app = create_app(settings, engine=db_engine, client_factory=scripted)
    student, headers = sign_in(app)
    course, chapter = LESSON["course_id"], LESSON["chapter_id"]
    async with http_client(app, headers) as client:
        with caplog.at_level("DEBUG"):
            conversation = (await client.post(f"/api/courses/{course}/chapters/{chapter}/discussion")).json()["conversation"]
            turn = await client.post(
                "/api/discussion/turn", json={**LESSON, "conversation_id": conversation["id"], "message": SECRET}
            )
            assert turn.status_code == 200
            minted = (await client.post("/api/voice/session", json={**LESSON, "history": []})).json()
            await client.post(
                "/api/voice/usage",
                json={"session_id": minted["session_id"], "reason": "learner", "duration_s": 9, "responses": 1,
                      "usage": {"input_audio": 5, "output_audio": 5}},
            )
    live = create_app(
        settings, engine=db_engine, probe=FakeProbe(),
        client_factory=PassingFactory(tutor=[[Failed(code="provider_unavailable", message=SECRET)]]),
    )
    admin, admin_headers = sign_in(live, email="root@example.be", name="Root", role="admin", lesson=False)
    async with http_client(live, admin_headers) as client:
        with caplog.at_level("DEBUG"):
            await client.post("/api/admin/ai/test", json={"live": True})
    await app.state.usage_recorder.drain()
    await live.state.usage_recorder.drain()

    with db_engine.connect() as conn:
        rows = conn.execute(sql("select * from ai_usage")).mappings().all()
    assert {r["feature"] for r in rows} == {"discussion_turn", "voice_session", "ai_test"}
    assert {r["user_id"] for r in rows} == {student["id"], admin["id"]}
    for row in rows:
        assert SECRET not in "|".join(str(v) for v in row.values()), dict(row)
    # Every log line of the three routes, not only the recorder's.
    assert not [r for r in caplog.records if SECRET in r.getMessage() or SECRET in str(r.__dict__.get("detail", ""))]
