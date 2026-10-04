from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas.chat import ChatRequest, LearnerEntry, ToolEntry, TutorEntry
from app.config import get_settings

S = get_settings()

IDS = {"course_id": "c0" * 16, "chapter_id": "5e" * 16}


def test_discriminator_routes_to_the_right_type() -> None:
    req = ChatRequest.model_validate(
        {**IDS, 
            "history": [
                {"kind": "learner", "text": "ok"},
                {"kind": "tutor", "text": "salut"},
                {"kind": "tool", "name": "clear_board", "arguments": {}, "ok": True},
            ]
        }
    )
    assert [type(e) for e in req.history] == [LearnerEntry, TutorEntry, ToolEntry]


def test_empty_history_is_valid() -> None:
    assert ChatRequest.model_validate({**IDS, "history": []}).history == []
    assert ChatRequest.model_validate({**IDS}).history == []


def test_oversized_message_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {**IDS, "history": [{"kind": "learner", "text": "x" * (S.max_message_chars + 1)}]}
        )


def test_oversized_history_rejected() -> None:
    entries = [{"kind": "learner", "text": "x"}] * (S.max_history_entries + 1)
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({**IDS, "history": entries})


def test_a_long_session_is_not_rejected() -> None:
    """Roughly 25 exchanges at four entries each: a full session must go through,
    because trimming the transcript is the token budget's job, not validation's."""
    entries = [{"kind": "learner", "text": "x"}] * 100
    assert len(ChatRequest.model_validate({**IDS, "history": entries}).history) == 100


def test_empty_learner_message_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({**IDS, "history": [{"kind": "learner", "text": ""}]})


def test_request_needs_course_and_chapter_ids() -> None:
    import pytest as _pytest

    req = ChatRequest.model_validate({**IDS, "history": []})
    assert req.course_id == "c0" * 16 and req.chapter_id == "5e" * 16
    with _pytest.raises(ValidationError):
        ChatRequest.model_validate({"history": []})
    with _pytest.raises(ValidationError):
        ChatRequest.model_validate({"course_id": "maths-5e", "chapter_id": "suites", "history": []})
    with _pytest.raises(ValidationError):
        ChatRequest.model_validate({"class_id": "c0" * 16, "chapter_id": "5e" * 16, "history": []})


def test_request_no_longer_carries_progress() -> None:
    import pytest as _pytest

    with _pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {**IDS, "history": [], "progress": {"done": []}}
        )
