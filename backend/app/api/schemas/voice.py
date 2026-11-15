"""Voice wire DTOs (003 design 4.1)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.chat import Id, ProgressDTO
from app.domain.mode import DEFAULT_MODE, ChapterMode


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VoiceSessionRequest(_Model):
    """Which chapter, in which mode. No transcript is posted in either mode (spec 018): a
    parcours session is seeded from the stored live séance, a discussion from the
    stored conversation its `conversation_id` names (007 §3.10)."""

    course_id: Id
    chapter_id: Id
    mode: ChapterMode = DEFAULT_MODE
    conversation_id: Id | None = None


class VoiceLimits(_Model):
    max_session_s: int
    idle_s: int


class VoiceSessionResponse(_Model):
    session_id: str
    secret: str
    expires_at: int
    model: str
    voice: str
    # Where the browser posts its SDP offer: the voice connection's server (spec 014 R10.2).
    calls_url: str
    limits: VoiceLimits
    seed: list[dict[str, Any]]
    opening: bool


class VoiceToolRequest(_Model):
    # The mode the browser is in. `registry.execute` gates on it, so a section
    # tool cannot be run from a discussion whatever this request says (007 §3.5).
    mode: ChapterMode = DEFAULT_MODE
    session_id: Annotated[str, Field(max_length=32)] = ""
    call_id: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=64)]
    arguments: Annotated[str, Field(max_length=16_000)] = ""
    course_id: Id
    chapter_id: Id


class VoiceToolResponse(_Model):
    output: str
    # TurnEvent.model_dump(mode="json"), discriminator included; None for a refusal.
    event: dict[str, Any] | None
    progress: ProgressDTO
    state_text: str | None = None


# A session of two hours cannot come near this; it keeps a forged report from storing a negative or an absurd total
# (the usage ledger sums them), and under what a 32-bit column holds.
MAX_TOKENS = 100_000_000
TokenCount = Annotated[int, Field(ge=0, le=MAX_TOKENS)]


class VoiceUsageTotals(_Model):
    input_text: TokenCount = 0
    input_audio: TokenCount = 0
    cached_text: TokenCount = 0
    cached_audio: TokenCount = 0
    output_text: TokenCount = 0
    output_audio: TokenCount = 0


class VoiceUsageReport(_Model):
    session_id: Annotated[str, Field(max_length=32)] = ""
    reason: Literal["learner", "cap", "idle", "error", "unload"]
    duration_s: Annotated[int, Field(ge=0, le=7200)]
    responses: Annotated[int, Field(ge=0, le=10_000)]
    usage: VoiceUsageTotals = VoiceUsageTotals()
