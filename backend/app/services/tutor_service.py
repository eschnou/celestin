"""The turn loop (design 3.4)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any

from app.api.schemas.chat import Entry
from app.api.schemas.events import TextDeltaEvent, TurnEnd, TurnEvent, TurnStart
from app.config import Settings
from app.domain import errors
from app.domain.chapter import LessonChapter
from app.domain.errors import ToolValidationError
from app.domain.usage import UsageScope, add_usage, usage_scope
from app.providers.base import Completed, Failed, LLMClient, TextDelta, ToolCallRequested
from app.services import history, prompt_service
from app.services.prompts import PromptLibrary
from app.services.tool_events import event_of
from app.services.tools import registry
from app.services.tools.context import TurnContext
from app.services.tools.section import SectionCompleted, SectionStarted

log = logging.getLogger(__name__)


class TutorService:
    def __init__(self, llm: LLMClient, prompts: PromptLibrary, settings: Settings) -> None:
        self._llm = llm
        self._prompts = prompts
        self._settings = settings

    def build_input(
        self, chapter: LessonChapter, entries: list[Entry], ctx: TurnContext
    ) -> list[dict[str, Any]]:
        """The model input for one turn of `chapter`. Raises PromptUnavailable before
        the stream opens, so it can still be an HTTP status. `ctx` comes from the
        controller, with the progress, the store and the mode already bound
        (004 design 3.6, 007 design 3.6)."""
        language = chapter.language
        return prompt_service.build(
            self._prompts.tutor(language),
            self._prompts.subject(chapter.subject, language),
            chapter.pack,
            ctx.curriculum,
            ctx.progress,
            history.to_provider_input(entries, self._settings.history_token_budget, ctx),
            self._prompts.mode(ctx.mode, language),
            self._prompts.mode_opening(ctx.mode, language),
            ctx.mode,
            now=self._settings.local_now(),
            language=language,
        )

    async def run_turn(
        self, items: list[dict[str, Any]], ctx: TurnContext
    ) -> AsyncIterator[TurnEvent]:
        """One turn. Its provider calls are recorded in the usage ledger for the student whose turn it is
        (spec 015): the scope is open for as long as the turn runs, and a context without a user (a unit test, a
        script) records nothing."""
        turn_id = uuid.uuid4().hex[:12]
        scope = (
            UsageScope(
                user_id=ctx.user_id,
                feature="discussion_turn" if ctx.mode == "discussion" else "tutor_turn",
                course_id=ctx.course_id,
                chapter_id=ctx.chapter_id,
                correlation_id=turn_id,
            )
            if ctx.user_id
            else None
        )
        with usage_scope(scope):
            async with aclosing(self._turn(items, ctx, turn_id)) as turn:
                async for event in turn:
                    yield event

    async def _turn(
        self, items: list[dict[str, Any]], ctx: TurnContext, turn_id: str
    ) -> AsyncIterator[TurnEvent]:
        started = time.monotonic()
        first_token_at: float | None = None
        block_id = 0
        usage: dict[str, Any] = {}
        tool_log: list[str] = []

        yield TurnStart(turn_id=turn_id)

        for round_index in range(self._settings.max_tool_rounds):
            text_parts: list[str] = []
            calls: list[ToolCallRequested] = []
            failure: Failed | None = None

            async with self._llm.stream(input=items, tools=registry.declarations(ctx.mode, ctx.language)) as stream:
                async for event in stream:
                    if isinstance(event, TextDelta):
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        text_parts.append(event.text)
                        yield TextDeltaEvent(block_id=block_id, text=event.text)
                    elif isinstance(event, ToolCallRequested):
                        calls.append(event)
                    elif isinstance(event, Completed):
                        usage = add_usage(usage, event.usage)  # the turn's rounds, summed (spec 015 R1.7)
                    elif isinstance(event, Failed):
                        failure = event

            if failure is not None:
                self._log_turn(
                    turn_id, round_index + 1, tool_log, "error", started, first_token_at, usage, ctx
                )
                log.warning("provider_failed", extra={"turn_id": turn_id, "detail": failure.message})
                raise errors.from_code(failure.code)

            if not calls:
                self._log_turn(
                    turn_id, round_index + 1, tool_log, "end", started, first_token_at, usage, ctx
                )
                yield TurnEnd(reason="end", usage=_for_the_student(usage))
                return

            # Replay what the model said and did, so the next round has its own context.
            joined = "".join(text_parts)
            if joined:
                items.append({"role": "assistant", "content": joined})

            for call in calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments_json,
                    }
                )
                try:
                    # Section tools write to the store: keep that off the event loop.
                    outcome = await asyncio.to_thread(registry.execute, call.name, call.arguments_json, ctx)
                except ToolValidationError as exc:
                    # Not an error: hand the message back so the model can fix it (R4.6).
                    tool_log.append(f"{call.name}:invalid")
                    items.append(_tool_output(call.call_id, {"ok": False, "error": exc.message}))
                    continue

                tool_log.append(f"{call.name}:ok")
                items.append(_tool_output(call.call_id, registry.output_of(outcome)))
                if isinstance(outcome, SectionStarted):
                    log.info(
                        "section_started",
                        extra={"turn_id": turn_id, "section_id": outcome.section.id, "review": outcome.review},
                    )
                elif isinstance(outcome, SectionCompleted):
                    log.info(
                        "section_completed",
                        extra={"turn_id": turn_id, "section_id": outcome.section.id, "summary": outcome.summary},
                    )
                yield event_of(outcome, ctx.locale)

            block_id += 1

        self._log_turn(
            turn_id, self._settings.max_tool_rounds, tool_log, "max_rounds", started, first_token_at, usage, ctx
        )
        yield TurnEnd(reason="max_rounds", usage=_for_the_student(usage))

    def _log_turn(
        self,
        turn_id: str,
        rounds: int,
        tools: list[str],
        reason: str,
        started: float,
        first_token_at: float | None,
        usage: dict[str, Any],
        ctx: TurnContext,
    ) -> None:
        log.info(
            "turn_complete",
            extra={
                "turn_id": turn_id,
                "user_id": ctx.user_id,
                "chapter_id": ctx.chapter_id,
                "mode": ctx.mode,
                "language": ctx.language,
                "section_active": ctx.progress.active,
                "model": self._llm.model,
                "rounds": rounds,
                "tools": tools,
                "reason": reason,
                "ttft_ms": None if first_token_at is None else round((first_token_at - started) * 1000),
                "total_ms": round((time.monotonic() - started) * 1000),
                "usage": usage,
                "cached_tokens": (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
            },
        )


def _for_the_student(usage: dict[str, Any]) -> dict[str, Any]:
    """What `turn.end` carries: the tokens, not a cost the provider reported (the ledger is the administrator's)."""
    return {key: value for key, value in usage.items() if key != "cost"}


def _tool_output(call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": registry.encode_output(payload),
    }
