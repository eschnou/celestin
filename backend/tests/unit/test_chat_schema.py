from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.api.schemas.chat import ChatRequest, Entry, LearnerEntry, ToolEntry, TutorEntry, stored_form
from app.api.schemas.seance import SeanceReportRequest
from app.config import get_settings

S = get_settings()

IDS = {"course_id": "c0" * 16, "chapter_id": "5e" * 16}
ENTRIES = TypeAdapter(list[Entry])


def test_discriminator_routes_to_the_right_type() -> None:
    entries = ENTRIES.validate_python(
        [
            {"kind": "learner", "text": "ok"},
            {"kind": "tutor", "text": "salut"},
            {"kind": "tool", "name": "clear_board", "arguments": {}, "ok": True},
        ]
    )
    assert [type(e) for e in entries] == [LearnerEntry, TutorEntry, ToolEntry]


def test_the_opening_turn_has_no_message() -> None:
    """Spec 018: a parcours turn posts the learner's message; null (or absent) opens the lesson."""
    assert ChatRequest.model_validate({**IDS, "message": None}).message is None
    assert ChatRequest.model_validate({**IDS}).message is None
    assert ChatRequest.model_validate({**IDS, "message": "bonjour"}).message == "bonjour"


def test_oversized_message_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({**IDS, "message": "x" * (S.max_message_chars + 1)})
    with pytest.raises(ValidationError):
        ENTRIES.validate_python([{"kind": "learner", "text": "x" * (S.max_message_chars + 1)}])


def test_a_message_at_the_cap_is_accepted() -> None:
    assert len(ChatRequest.model_validate({**IDS, "message": "x" * S.max_message_chars}).message) == S.max_message_chars


def test_a_posted_transcript_is_refused() -> None:
    """The server owns the parcours transcript (spec 018 D1)."""
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({**IDS, "history": []})


def test_a_reported_voice_turn_is_bounded() -> None:
    one = [{"kind": "learner", "text": "x"}]
    assert len(SeanceReportRequest.model_validate({**IDS, "entries": one * 32}).entries) == 32
    with pytest.raises(ValidationError):
        SeanceReportRequest.model_validate({**IDS, "entries": one * 33})
    with pytest.raises(ValidationError):
        SeanceReportRequest.model_validate({**IDS, "entries": []})


def test_empty_learner_message_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({**IDS, "message": ""})
    with pytest.raises(ValidationError):
        ENTRIES.validate_python([{"kind": "learner", "text": ""}])


def test_request_needs_course_and_chapter_ids() -> None:
    req = ChatRequest.model_validate({**IDS})
    assert req.course_id == "c0" * 16 and req.chapter_id == "5e" * 16
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": None})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"course_id": "maths-5e", "chapter_id": "suites"})
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"class_id": "c0" * 16, "chapter_id": "5e" * 16})


def test_request_no_longer_carries_progress() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({**IDS, "progress": {"done": []}})


def test_review_is_recorded_on_a_start_section_entry_only() -> None:
    start = ToolEntry(kind="tool", name="start_section", arguments={"section_id": "s"}, review=True)
    assert start.review is True
    with pytest.raises(ValidationError):
        ToolEntry(kind="tool", name="display_board", arguments={}, review=False)


def test_the_stored_form_of_a_board_entry_is_what_it_always_was() -> None:
    """A discussion's rows keep their bytes: `review` is only stored when it is set."""
    board = ToolEntry(kind="tool", name="clear_board", arguments={})
    assert stored_form(board) == {"kind": "tool", "name": "clear_board", "arguments": {}, "ok": True, "error": None}
    start = ToolEntry(kind="tool", name="start_section", arguments={"section_id": "s"}, review=False)
    assert stored_form(start)["review"] is False
