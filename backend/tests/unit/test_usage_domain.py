"""Spec 015 §3.1: the ledger's vocabulary, the reading of a usage block and the scope."""

from __future__ import annotations

import asyncio
import math

import pytest

from app.domain.usage import (
    FEATURES,
    STATUSES,
    UsageNumbers,
    UsageScope,
    add_usage,
    current_scope,
    feature_of,
    read_usage,
    usage_scope,
)

RESPONSES = {
    "input_tokens": 120,
    "input_tokens_details": {"cached_tokens": 100},
    "output_tokens": 30,
    "output_tokens_details": {"reasoning_tokens": 10},
}


def test_read_usage_reads_the_responses_shape() -> None:
    assert read_usage(RESPONSES) == UsageNumbers(120, 100, 30, 10, None)


def test_read_usage_of_nothing_is_nothing_not_zero() -> None:
    assert read_usage(None) == UsageNumbers()
    assert read_usage({}) == UsageNumbers()


def test_read_usage_leaves_out_what_the_provider_did_not_send() -> None:
    assert read_usage({"input_tokens": 5, "output_tokens": 2}) == UsageNumbers(5, None, 2, None, None)
    assert read_usage({"input_tokens": 5, "input_tokens_details": None}).cached_tokens is None


def test_a_reported_zero_is_a_zero() -> None:
    assert read_usage({"input_tokens": 0, "input_tokens_details": {"cached_tokens": 0}}).cached_tokens == 0


@pytest.mark.parametrize(
    ("cost", "expected"),
    [(0.0123, 0.0123), (2, 2.0), (0, 0.0), ("0.01", None), (True, None), (-1, None), (math.nan, None),
     (math.inf, None), (None, None), ([1], None)],
)
def test_only_a_finite_non_negative_number_is_a_cost(cost, expected) -> None:
    assert read_usage({"cost": cost}).cost_usd == expected


@pytest.mark.parametrize("bad", [-1, "3", 1.5, True, None])
def test_a_token_count_is_a_non_negative_integer(bad) -> None:
    assert read_usage({"input_tokens": bad}).input_tokens is None


def test_add_usage_sums_the_rounds() -> None:
    total = add_usage(RESPONSES, {**RESPONSES, "cost": 0.5})
    assert total["input_tokens"] == 240 and total["output_tokens"] == 60
    assert total["input_tokens_details"] == {"cached_tokens": 200}
    assert total["output_tokens_details"] == {"reasoning_tokens": 20}
    assert total["cost"] == 0.5


def test_add_usage_keeps_a_figure_only_one_side_reports() -> None:
    total = add_usage({"input_tokens": 5}, {"input_tokens": 7, "input_tokens_details": {"cached_tokens": 3}})
    assert total == {"input_tokens": 12, "input_tokens_details": {"cached_tokens": 3}}


def test_add_usage_with_an_empty_side_is_the_other_side() -> None:
    assert add_usage({}, RESPONSES) == RESPONSES
    assert add_usage(RESPONSES, {}) == RESPONSES
    assert add_usage({}, {}) == {}


def test_add_usage_does_not_mutate_its_arguments() -> None:
    first = {"input_tokens": 1, "input_tokens_details": {"cached_tokens": 1}}
    add_usage(first, {"input_tokens": 2})
    assert first == {"input_tokens": 1, "input_tokens_details": {"cached_tokens": 1}}


def test_a_document_run_reads_pages_with_the_transcription_role() -> None:
    scope = UsageScope("u", "authoring")
    assert feature_of(scope, "authoring") == "authoring"
    assert feature_of(scope, "transcription") == "document_reading"
    assert feature_of(UsageScope("u", "work_reading"), "transcription") == "work_reading"


def test_the_vocabularies_are_closed() -> None:
    assert "voice_session" in FEATURES and "ai_test" in FEATURES
    assert set(STATUSES) == {"ok", "failed", "truncated", "cancelled"}


def test_a_scope_nests_and_is_restored() -> None:
    assert current_scope() is None
    outer, inner = UsageScope("a", "tutor_turn"), UsageScope("b", "dictation")
    with usage_scope(outer):
        assert current_scope() is outer
        with usage_scope(inner):
            assert current_scope() is inner
        assert current_scope() is outer
    assert current_scope() is None


def test_a_scope_is_restored_after_an_exception() -> None:
    with pytest.raises(RuntimeError), usage_scope(UsageScope("a", "tutor_turn")):
        raise RuntimeError
    assert current_scope() is None


async def test_a_scope_opened_in_a_generator_can_be_closed_from_another_task() -> None:
    """A turn's scope lives in an async generator that another task may close: `reset(token)` would raise."""

    async def turn():
        with usage_scope(UsageScope("a", "tutor_turn")):
            yield 1
            yield 2

    generator = turn()
    assert await generator.__anext__() == 1
    await asyncio.create_task(generator.aclose())


async def test_a_child_task_inherits_the_scope() -> None:
    seen: list[UsageScope | None] = []

    async def child() -> None:
        seen.append(current_scope())

    scope = UsageScope("a", "authoring", "c", "ch", "run")
    with usage_scope(scope):
        task = asyncio.create_task(child())
        await asyncio.gather(child(), child())
    await task
    assert seen == [scope, scope, scope]


def test_a_turn_has_the_same_shape_for_one_round_or_many() -> None:
    """The figures the application reads, whatever else the provider sent."""
    raw = {**RESPONSES, "total_tokens": 150, "input_tokens_details": {"cached_tokens": 100, "audio_tokens": 0}}
    assert add_usage({}, raw) == RESPONSES
    assert set(add_usage(RESPONSES, raw)) == set(RESPONSES)
    assert add_usage({}, {}) == {}


def test_a_cost_is_summed_over_the_rounds_that_reported_one() -> None:
    assert add_usage({"cost": 0.25}, {"input_tokens": 1})["cost"] == 0.25
    assert add_usage({"cost": 0.25}, {"cost": 0.5})["cost"] == 0.75
    assert "cost" not in add_usage({"input_tokens": 1}, {"input_tokens": 1})
