"""The voice side of the tutor (003 design 3.2).

Stateless like the turn loop: the session configuration is a pure function of the
course files and settings, the seed is the mapped transcript, and a tool call is
executed in a TurnContext built from the posted progress.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from app.api.schemas.chat import Entry, ProgressDTO
from app.api.schemas.voice import (
    VoiceLimits,
    VoiceSessionResponse,
    VoiceToolResponse,
    VoiceUsageReport,
)
from app.config import Settings
from app.domain.ai_config import RoleConfig, calls_url, priced
from app.domain.chapter import LessonChapter
from app.domain.errors import ToolValidationError, VoiceDisabled
from app.providers.base import AiConfigSource, RealtimeClient
from app.services import curriculum_render, history, prompt_service
from app.services.prompts import PromptLibrary
from app.services.tool_events import event_of
from app.services.tools import registry
from app.domain.mode import DEFAULT_MODE, Mode
from app.services.tools.context import TurnContext

log = logging.getLogger(__name__)


class VoiceService:
    def __init__(
        self, realtime: RealtimeClient, prompts: PromptLibrary, settings: Settings, ai: AiConfigSource
    ) -> None:
        self._realtime = realtime
        self._prompts = prompts
        self._settings = settings
        self._ai = ai

    def _voice(self) -> RoleConfig:
        """The voice role in force (spec 014 R10): its model, its connection. Off means no session."""
        config = self._ai.config
        voice = config.voice if config else None
        if voice is None:
            raise VoiceDisabled()
        return voice

    # ----------------------------------------------------------------- session

    def instructions(self, chapter: LessonChapter, mode: Mode = DEFAULT_MODE) -> str:
        """The prompt as a Realtime session receives it: voice blocks kept."""
        language = chapter.language
        return prompt_service.render_system_text(
            self._prompts.tutor(language),
            self._prompts.subject(chapter.subject, language),
            chapter.pack,
            curriculum_render.overview(chapter.curriculum, mode, language),
            self._prompts.mode(mode, language),
            self._prompts.mode_opening(mode, language),
            voice=True,
        )

    def session_config(
        self, chapter: LessonChapter, mode: Mode = DEFAULT_MODE, voice: RoleConfig | None = None
    ) -> dict[str, Any]:
        """Byte-stable across calls given unchanged files, so the Realtime prompt
        cache hits. No audio `format` keys: WebRTC negotiates them."""
        s, voice = self._settings, voice or self._voice()
        config: dict[str, Any] = {
            "type": "realtime",
            "model": voice.model,
            "instructions": self.instructions(chapter, mode),
            "tools": registry.realtime_declarations(mode, chapter.language),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "noise_reduction": {"type": "near_field"},
                    "transcription": {"model": voice.voice_transcription_model, "language": chapter.language},
                    "turn_detection": {
                        "type": s.voice_turn_detection,
                        "create_response": True,
                        "interrupt_response": True,
                    },
                },
                "output": {"voice": s.voice_name, "speed": s.voice_speed},
            },
            "max_output_tokens": s.voice_max_output_tokens,
            "truncation": "auto",
            "tracing": None,
        }
        if voice.reasoning_effort:
            config["reasoning"] = {"effort": voice.reasoning_effort}
        return config

    def seed(
        self, entries: list[Entry], ctx: TurnContext, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        """The prior transcript as Realtime conversation items, then the path state
        as a system item (design 3.6)."""
        items = [
            _to_realtime_item(item)
            for item in history.to_provider_input(entries, self._settings.voice_seed_token_budget, ctx)
        ]
        items.append(
            _system_item(
                curriculum_render.state_message(ctx.curriculum, ctx.progress, now, ctx.mode, ctx.language)
            )
        )
        return items

    async def create_session(
        self, chapter: LessonChapter, entries: list[Entry], ctx: TurnContext
    ) -> VoiceSessionResponse:
        # Everything that can fail on our side fails before the provider is called.
        voice = self._voice()
        config = self.session_config(chapter, ctx.mode, voice)
        seed = self.seed(entries, ctx, now=self._settings.local_now())
        secret = await self._realtime.create_client_secret(
            session=config, ttl_s=self._settings.voice_secret_ttl_s
        )
        session_id = uuid.uuid4().hex[:12]
        log.info(
            "voice_session_created",
            extra={
                "session_id": session_id,
                "model": voice.model,
                "voice": self._settings.voice_name,
                "ttl_s": self._settings.voice_secret_ttl_s,
                "chapter_id": chapter.id,
                "subject": chapter.subject,
                "language": chapter.language,
                "seed_items": len(seed),
                "history_entries": len(entries),
            },
        )
        return VoiceSessionResponse(
            session_id=session_id,
            secret=secret.value,
            expires_at=secret.expires_at,
            model=voice.model,
            voice=self._settings.voice_name,
            calls_url=calls_url(voice.connection),
            limits=VoiceLimits(
                max_session_s=self._settings.voice_session_max_s, idle_s=self._settings.voice_idle_s
            ),
            seed=seed,
            opening=not entries,
        )

    # -------------------------------------------------------------------- tool

    def execute_tool(self, name: str, arguments: str, ctx: TurnContext) -> VoiceToolResponse:
        """What the text loop does for one call, as a response the browser relays.
        `ctx` carries the stored progress and the store, as in the text loop."""
        before = ctx.progress
        try:
            outcome = registry.execute(name, arguments, ctx)
        except ToolValidationError as exc:
            return VoiceToolResponse(
                output=registry.encode_output({"ok": False, "error": exc.message}),
                event=None,
                progress=ProgressDTO.from_progress(ctx.progress),
            )
        # A refreshed state message whenever the call moved the path (R2.4).
        state_text = (
            curriculum_render.state_message(
                ctx.curriculum, ctx.progress, self._settings.local_now(), ctx.mode, ctx.language
            )
            if ctx.progress != before
            else None
        )
        return VoiceToolResponse(
            output=registry.encode_output(registry.output_of(outcome)),
            event=event_of(outcome, ctx.locale).model_dump(mode="json"),
            progress=ProgressDTO.from_progress(ctx.progress),
            state_text=state_text,
        )

    # ------------------------------------------------------------------- usage

    def log_usage(self, report: VoiceUsageReport, user_id: str) -> float:
        """Logs the session and returns the cost estimate in USD."""
        s, u = self._settings, report.usage
        config = self._ai.config
        connection = config.voice.connection if config and config.voice else None
        # OpenAI's prices only mean something for OpenAI (or prices the operator set): R11.2.
        per_million = 0.0 if not priced(
            s, connection, "voice_price_audio_in", "voice_price_audio_cached", "voice_price_audio_out",
            "voice_price_text_in", "voice_price_text_cached", "voice_price_text_out",
        ) else (
            (u.input_audio - u.cached_audio) * s.voice_price_audio_in
            + u.cached_audio * s.voice_price_audio_cached
            + u.output_audio * s.voice_price_audio_out
            + (u.input_text - u.cached_text) * s.voice_price_text_in
            + u.cached_text * s.voice_price_text_cached
            + u.output_text * s.voice_price_text_out
        )
        cost = round(max(per_million, 0) / 1_000_000, 4)
        log.info(
            "voice_usage",
            extra={
                "session_id": report.session_id,
                "reason": report.reason,
                "duration_s": report.duration_s,
                "responses": report.responses,
                **u.model_dump(),
                "cost_estimate_usd": cost,
                "user_id": user_id,
            },
        )
        return cost



def _to_realtime_item(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("role") == "user":
        return {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": item["content"]}],
        }
    if item.get("role") == "assistant":
        return {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": item["content"]}],
        }
    return item  # function_call and function_call_output share the Responses shape


def _system_item(text: str) -> dict[str, Any]:
    return {"type": "message", "role": "system", "content": [{"type": "input_text", "text": text}]}


