"""Transcript to provider input (design 3.4) and the trimming policy (design 7)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.api.schemas.chat import Entry, LearnerEntry, ToolEntry, TutorEntry
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.services.tools import registry
from app.services.tools.context import TurnContext

log = logging.getLogger(__name__)

# French prose runs a little under 3.2 characters per token, English a little over 4. The
# budget is an order-of-magnitude guard, not a hard limit, so a tokenizer would be overkill;
# the ratio only has to keep English from being trimmed as if it were French.
# Dutch: an estimate between the two (long compounds tokenise worse than English); to check against `ai_usage`.
CHARS_PER_TOKEN = by_language(fr=3.2, en=4.0, nl=3.4)


def estimate_tokens(entries: list[Entry], language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> int:
    chars = 0
    for entry in entries:
        if isinstance(entry, ToolEntry):
            chars += len(entry.name) + len(json.dumps(entry.arguments, ensure_ascii=False))
        else:
            chars += len(entry.text)
    return int(chars / CHARS_PER_TOKEN[language])


def _split_turns(entries: list[Entry]) -> list[list[Entry]]:
    """A turn starts at a learner message. Anything before the first one — the
    opening turn — forms its own group so a tool entry is never orphaned."""
    turns: list[list[Entry]] = []
    for entry in entries:
        if isinstance(entry, LearnerEntry) or not turns:
            turns.append([entry])
        else:
            turns[-1].append(entry)
    return turns


def _latest_start(entries: list[Entry]) -> ToolEntry | None:
    for entry in reversed(entries):
        if isinstance(entry, ToolEntry) and entry.ok and entry.name == "start_section":
            return entry
    return None


def trim(
    entries: list[Entry],
    token_budget: int,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    keep_brief: bool = False,
) -> list[Entry]:
    """Drop whole turns oldest-first. The most recent turn always survives.

    `keep_brief` is the parcours (spec 018 D10): a séance is one section's work and
    outlives a reload, so a long one would otherwise lose the call whose replayed output
    is the section's brief (its beats, its end criterion, the reprise note) long before
    the row rolls over. The latest ok `start_section` among the dropped turns is then
    carried at the head of what is kept, unless what is kept already holds one; the
    total stays within the budget plus that one call."""
    turns = _split_turns(entries)
    costs = [estimate_tokens(turn, language) for turn in turns]
    total = sum(costs)
    dropped: list[Entry] = []
    while len(turns) > 1 and total > token_budget:
        oldest = turns.pop(0)
        total -= costs.pop(0)
        dropped.extend(oldest)
        log.info("history_trimmed", extra={"dropped_entries": len(oldest)})
    kept = [entry for turn in turns for entry in turn]
    if keep_brief and dropped and _latest_start(kept) is None:
        brief = _latest_start(dropped)
        if brief is not None:
            log.info("history_brief_kept", extra={"kept_entries": len(kept)})
            kept = [brief, *kept]
    return kept


def to_provider_input(
    entries: list[Entry], token_budget: int, ctx: TurnContext
) -> list[dict[str, Any]]:
    """Map the transcript onto provider items.

    Call ids are synthesized from the entry index (design 10.4): they only need to
    be consistent within one request, and keeping them out of the DTO keeps the
    transcript provider-neutral.

    A replayed section tool answers with its brief again (design 3.8), so the model
    keeps the beats in front of it on every later turn; in the parcours the trim keeps
    that call even when it drops the turn it was made in (spec 018 D10).
    """
    items: list[dict[str, Any]] = []
    kept = trim(entries, token_budget, ctx.language, keep_brief=ctx.mode == "parcours")
    for index, entry in enumerate(kept):
        if isinstance(entry, LearnerEntry):
            items.append({"role": "user", "content": entry.text})
        elif isinstance(entry, TutorEntry):
            if entry.text:
                items.append({"role": "assistant", "content": entry.text})
        else:
            call_id = f"call_{index}"
            # A function_call is never emitted without its output: the model would
            # reject an unanswered call on the next turn.
            items.append(
                {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": entry.name,
                    "arguments": json.dumps(entry.arguments, ensure_ascii=False),
                }
            )
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(
                        registry.replay_output(entry, ctx)
                        if entry.ok
                        else {"ok": False, "error": entry.error},
                        ensure_ascii=False,
                    ),
                }
            )
    return items
