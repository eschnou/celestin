"""The usage ledger's vocabulary (spec 015 §3.1): what a call is attributed to and what it is recorded as.

Pure data. A row holds metadata only: ids, enumerations, a model name, a host name, numbers. Nothing a student
wrote, said or uploaded, and no provider text, ever becomes a field of an entry.

The *scope* says who a call is for. The services that know the user, the course and the chapter open one around
the code that calls a model; the recording wrappers of `app/providers/recording.py` read it when a call starts.
It is a `contextvar` (as the request id is), so a background task inherits it at creation and so does every
child of a `gather`.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, get_args

from app.domain.ai_config import Role

Feature = Literal[
    "tutor_turn",
    "discussion_turn",
    "authoring",
    "document_reading",
    "work_reading",
    "dictation",
    "voice_session",
    "ai_test",
]
FEATURES: tuple[str, ...] = get_args(Feature)
Status = Literal["ok", "failed", "truncated", "cancelled"]
STATUSES: tuple[str, ...] = get_args(Status)


@dataclass(frozen=True)
class UsageScope:
    """Who a call is for, and what it is for."""

    user_id: str
    feature: Feature
    course_id: str | None = None
    chapter_id: str | None = None
    correlation_id: str | None = None  # a turn id, a run id, a voice session id
    audio_seconds: float | None = None  # dictation: known before the call is made


@dataclass(frozen=True)
class UsageEntry:
    """One row of the ledger (R1.5)."""

    created_at: datetime
    user_id: str
    role: Role
    feature: Feature
    model: str
    provider: str
    status: Status
    course_id: str | None = None
    chapter_id: str | None = None
    correlation_id: str | None = None
    error_code: str | None = None
    latency_ms: int | None = None
    ttft_ms: int | None = None
    input_tokens: int | None = None
    cached_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    input_audio_tokens: int | None = None
    output_audio_tokens: int | None = None
    audio_seconds: float | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class UsageNumbers:
    """What a provider's usage block says. `None` is « not reported », which is not zero."""

    input_tokens: int | None = None
    cached_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None


_scope: ContextVar[UsageScope | None] = ContextVar("usage_scope", default=None)


def current_scope() -> UsageScope | None:
    return _scope.get()


@contextmanager
def usage_scope(scope: UsageScope | None) -> Iterator[None]:
    """Open a scope for the code inside. Restores with `set(previous)`, never `reset(token)`: a scope opened inside
    an async generator (a tutor turn) can be closed from another context, where `reset` raises."""
    previous = _scope.get()
    _scope.set(scope)
    try:
        yield
    finally:
        _scope.set(previous)


def feature_of(scope: UsageScope, role: Role) -> Feature:
    """An authoring run reads its document with the transcription role: that is its own feature."""
    if scope.feature == "authoring" and role == "transcription":
        return "document_reading"
    return scope.feature


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _amount(value: Any) -> float | None:
    """A cost the provider reported: a finite, non-negative number. A string is not coerced."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _detail(usage: dict[str, Any], group: str, key: str) -> int | None:
    details = usage.get(group)
    return _count(details.get(key)) if isinstance(details, dict) else None


def read_usage(usage: dict[str, Any] | None) -> UsageNumbers:
    """The numbers of a Responses-shaped usage dict (what both adapters hand over)."""
    if not usage:
        return UsageNumbers()
    return UsageNumbers(
        input_tokens=_count(usage.get("input_tokens")),
        cached_tokens=_detail(usage, "input_tokens_details", "cached_tokens"),
        output_tokens=_count(usage.get("output_tokens")),
        reasoning_tokens=_detail(usage, "output_tokens_details", "reasoning_tokens"),
        cost_usd=_amount(usage.get("cost")),
    )


def add_usage(total: dict[str, Any], one: dict[str, Any]) -> dict[str, Any]:
    """The sum of two usage dicts, for a turn made of several rounds. Only the figures the application reads are
    kept (the same shape for one round or many); a figure only one side reports is kept as it is, and a cost is
    summed over the sides that reported one."""
    summed: dict[str, Any] = {}  # always the known figures, whatever the number of rounds
    for key in ("input_tokens", "output_tokens"):
        _add_figure(summed, key, _count(total.get(key)), _count(one.get(key)))
    for group, key in (("input_tokens_details", "cached_tokens"), ("output_tokens_details", "reasoning_tokens")):
        a, b = total.get(group), one.get(group)
        inner: dict[str, Any] = {}
        _add_figure(
            inner, key, _count(a.get(key)) if isinstance(a, dict) else None, _count(b.get(key)) if isinstance(b, dict) else None
        )
        if inner:
            summed[group] = inner
    _add_figure(summed, "cost", _amount(total.get("cost")), _amount(one.get("cost")))
    return summed


def _add_figure(into: dict[str, Any], key: str, x: float | None, y: float | None) -> None:
    """`into[key]` = the sum of the sides that reported it; nothing when neither did."""
    if x is not None or y is not None:
        into[key] = (x or 0) + (y or 0)
