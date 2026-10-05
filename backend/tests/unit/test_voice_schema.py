from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas.voice import VoiceToolRequest, VoiceUsageReport


IDS = {"course_id": "c0" * 16, "chapter_id": "5e" * 16}


def test_tool_request_defaults() -> None:
    r = VoiceToolRequest(call_id="c1", name="clear_board", **IDS)
    assert r.arguments == "" and r.session_id == "" and r.chapter_id == "5e" * 16


def test_tool_request_needs_ids() -> None:
    with pytest.raises(ValidationError):
        VoiceToolRequest(call_id="c1", name="clear_board")  # type: ignore[call-arg]


def test_tool_arguments_capped() -> None:
    with pytest.raises(ValidationError):
        VoiceToolRequest(call_id="c1", name="x", arguments="a" * 16_001, **IDS)


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        VoiceToolRequest(call_id="c1", name="x", result="{}", **IDS)  # type: ignore[call-arg]


def test_usage_report_bounds() -> None:
    VoiceUsageReport(reason="cap", duration_s=0, responses=0)
    with pytest.raises(ValidationError):
        VoiceUsageReport(reason="cap", duration_s=-1, responses=0)
    with pytest.raises(ValidationError):
        VoiceUsageReport(reason="bogus", duration_s=1, responses=0)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["input_text", "input_audio", "cached_text", "cached_audio", "output_text", "output_audio"])
def test_a_token_total_is_a_bounded_count(field: str) -> None:
    """Spec 015 R4.3: a forged report cannot store a negative or an absurd total."""
    from app.api.schemas.voice import MAX_TOKENS

    report = lambda value: VoiceUsageReport(  # noqa: E731
        reason="cap", duration_s=1, responses=1, usage={field: value}  # type: ignore[arg-type]
    )
    assert getattr(report(MAX_TOKENS).usage, field) == MAX_TOKENS and getattr(report(0).usage, field) == 0
    for bad in (-1, MAX_TOKENS + 1, 10**12):
        with pytest.raises(ValidationError):
            report(bad)
    assert MAX_TOKENS < 2**31  # what a 32-bit column holds
