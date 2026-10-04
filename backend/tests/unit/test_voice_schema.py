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
