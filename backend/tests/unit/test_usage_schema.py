"""Spec 015 §3.6: the ledger's DTOs carry no name of a course or a chapter and refuse unknown fields."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas.usage import CallDTO, TotalsDTO, UserUsageDTO

CALL_FIELDS = {
    "id", "created_at", "user_id", "user_name", "user_email", "course_id", "chapter_id", "course_subject",
    "course_language", "correlation_id", "role", "feature", "model", "provider", "status", "error_code",
    "latency_ms", "ttft_ms", "input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens",
    "input_audio_tokens", "output_audio_tokens", "audio_seconds", "cost_usd",
}


def test_a_call_carries_ids_subject_and_language_never_a_title() -> None:
    assert set(CallDTO.model_fields) == CALL_FIELDS
    assert not [f for f in CALL_FIELDS if "title" in f or f in ("course_name", "chapter_name", "name")]


def test_the_dtos_refuse_what_they_do_not_declare() -> None:
    with pytest.raises(ValidationError):
        TotalsDTO(calls=1, input_tokens=0, cached_tokens=0, output_tokens=0, reasoning_tokens=0, cost_usd=None, costed_calls=0, extra=1)  # type: ignore[call-arg]
    assert "course_name" not in UserUsageDTO.model_fields
