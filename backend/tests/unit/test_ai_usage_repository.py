"""Spec 015 §3.5: the ledger's repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.repositories import CallFilters, Period, Repositories
from app.domain.usage import UsageEntry

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def entry(user_id: str, at: datetime = T0, **fields) -> UsageEntry:
    base = dict(
        created_at=at, user_id=user_id, role="tutor", feature="tutor_turn", model="m1", provider="api.test", status="ok"
    )
    return UsageEntry(**{**base, **fields})


@pytest.fixture
def two_users(repos: Repositories) -> tuple[str, str]:
    return repos.users.create("a@x.be", "Ana", "h").id, repos.users.create("b@x.be", "Élodie", "h").id


def test_add_round_trips_every_field(repos: Repositories, two_users) -> None:
    ana, _ = two_users
    course = repos.courses.create(ana, "Maths", "mathematics", max_courses=30).id
    full = entry(
        ana, course_id=course, correlation_id="turn1", error_code="provider_timeout", status="failed",
        latency_ms=1200, ttft_ms=300, input_tokens=100, cached_tokens=80, output_tokens=20, reasoning_tokens=5,
        input_audio_tokens=7, output_audio_tokens=3, audio_seconds=4.5, cost_usd=0.0123,
    )
    repos.ai_usage.add(full)
    (listed,), more = repos.ai_usage.calls(Period(), CallFilters())
    assert listed.entry == full and not more
    assert (listed.user_name, listed.course_subject, listed.course_language) == ("Ana", "mathematics", "fr")


def test_nulls_stay_nulls(repos: Repositories, two_users) -> None:
    repos.ai_usage.add(entry(two_users[0]))
    (listed,), _ = repos.ai_usage.calls(Period(), CallFilters())
    assert listed.entry.input_tokens is None and listed.entry.cost_usd is None and listed.course_subject is None


def test_totals_sum_what_was_reported_and_count_the_costs(repos: Repositories, two_users) -> None:
    ana, _ = two_users
    repos.ai_usage.add(entry(ana, input_tokens=100, output_tokens=10, cost_usd=0.5))
    repos.ai_usage.add(entry(ana, input_tokens=50, cached_tokens=20, output_tokens=5, reasoning_tokens=2, cost_usd=0.25))
    repos.ai_usage.add(entry(ana))  # the provider reported nothing
    totals = repos.ai_usage.summary(Period()).totals
    assert (totals.calls, totals.input_tokens, totals.cached_tokens, totals.output_tokens, totals.reasoning_tokens) == (3, 150, 20, 15, 2)
    assert totals.cost_usd == 0.75 and totals.costed_calls == 2


def test_no_reported_cost_is_none_not_zero(repos: Repositories, two_users) -> None:
    repos.ai_usage.add(entry(two_users[0], input_tokens=1))
    totals = repos.ai_usage.summary(Period()).totals
    assert totals.calls == 1 and totals.cost_usd is None and totals.costed_calls == 0
    assert repos.ai_usage.summary(Period(since=T0 + timedelta(days=1))).totals.calls == 0


def test_a_reported_zero_cost_is_a_cost(repos: Repositories, two_users) -> None:
    repos.ai_usage.add(entry(two_users[0], cost_usd=0.0))
    totals = repos.ai_usage.summary(Period()).totals
    assert totals.cost_usd == 0.0 and totals.costed_calls == 1


def test_the_summary_lists_the_models_without_the_unknown_one(repos: Repositories, two_users) -> None:
    ana, _ = two_users
    for model in ("b-model", "a-model", "a-model", ""):
        repos.ai_usage.add(entry(ana, model=model))
    assert repos.ai_usage.summary(Period()).models == ["a-model", "b-model"]


def test_the_period_is_half_open_and_any_offset(repos: Repositories, two_users) -> None:
    ana, _ = two_users
    for hours in (0, 1, 2):
        repos.ai_usage.add(entry(ana, T0 + timedelta(hours=hours), input_tokens=1))
    count = lambda p: repos.ai_usage.summary(p).totals.calls  # noqa: E731
    assert count(Period(since=T0 + timedelta(hours=1))) == 2
    assert count(Period(until=T0 + timedelta(hours=1))) == 1
    assert count(Period(T0 + timedelta(hours=1), T0 + timedelta(hours=2))) == 1
    # 14:00+02:00 is 12:00 UTC: the first row is in, whatever the offset the instant came with.
    assert count(Period(since=datetime(2026, 3, 1, 14, 0, tzinfo=timezone(timedelta(hours=2))), until=T0 + timedelta(hours=1))) == 1


def test_per_user_orders_and_pages(repos: Repositories, two_users) -> None:
    ana, elo = two_users
    for _ in range(3):
        repos.ai_usage.add(entry(ana, input_tokens=10, output_tokens=1, cost_usd=0.1))
    repos.ai_usage.add(entry(elo, input_tokens=500, output_tokens=9))
    users, total = repos.ai_usage.per_user(Period())
    assert total == 2 and [u.name for u in users] == ["Ana", "Élodie"] and users[0].totals.calls == 3
    assert [u.name for u in repos.ai_usage.per_user(Period(), order="input_tokens")[0]] == ["Élodie", "Ana"]
    assert [u.name for u in repos.ai_usage.per_user(Period(), order="output_tokens")[0]] == ["Élodie", "Ana"]
    assert [u.name for u in repos.ai_usage.per_user(Period(), order="name", descending=False)[0]] == ["Ana", "Élodie"]
    # Cost: the user whose provider reported none comes last in both directions.
    assert [u.name for u in repos.ai_usage.per_user(Period(), order="cost")[0]] == ["Ana", "Élodie"]
    assert [u.name for u in repos.ai_usage.per_user(Period(), order="cost", descending=False)[0]] == ["Ana", "Élodie"]
    page, total = repos.ai_usage.per_user(Period(), limit=1, offset=1)
    assert total == 2 and [u.name for u in page] == ["Élodie"]


def test_per_user_lists_only_users_with_calls_in_the_period(repos: Repositories, two_users) -> None:
    ana, elo = two_users
    repos.ai_usage.add(entry(ana, T0 - timedelta(days=9)))
    repos.ai_usage.add(entry(elo, T0))
    users, total = repos.ai_usage.per_user(Period(since=T0 - timedelta(days=1)))
    assert total == 1 and users[0].user_id == elo


@pytest.mark.parametrize(("query", "names"), [("élo", ["Élodie"]), ("ÉLO", ["Élodie"]), ("b@x", ["Élodie"]), ("%", []), ("_", []), ("", ["Ana", "Élodie"])])
def test_per_user_search(repos: Repositories, two_users, query: str, names: list[str]) -> None:
    for user in two_users:
        repos.ai_usage.add(entry(user))
    assert sorted(u.name for u in repos.ai_usage.per_user(Period(), query=query)[0]) == names


def test_a_disabled_user_is_listed_as_such(repos: Repositories, two_users, db_engine) -> None:
    ana, _ = two_users
    repos.ai_usage.add(entry(ana))
    with db_engine.begin() as conn:
        conn.execute(text("update users set enabled = 0 where id = :i"), {"i": ana})
    (user,), _ = repos.ai_usage.per_user(Period())
    assert user.enabled is False


def test_the_breakdown_by_role_and_model(repos: Repositories, two_users) -> None:
    ana, elo = two_users
    repos.ai_usage.add(entry(ana, input_tokens=10))
    repos.ai_usage.add(entry(ana, input_tokens=20))
    repos.ai_usage.add(entry(ana, role="authoring", feature="authoring", model="m2", provider="other.test", input_tokens=5, cost_usd=1.0))
    repos.ai_usage.add(entry(elo, input_tokens=999))
    breakdown = repos.ai_usage.user_breakdown(ana, Period())
    assert breakdown.totals.calls == 3 and breakdown.totals.input_tokens == 35
    assert [(r.role, r.totals.calls) for r in breakdown.by_role] == [("authoring", 1), ("tutor", 2)]
    assert [(m.model, m.provider, m.totals.calls) for m in breakdown.by_model] == [("m1", "api.test", 2), ("m2", "other.test", 1)]
    assert breakdown.by_model[1].totals.cost_usd == 1.0
    empty = repos.ai_usage.user_breakdown("nobody", Period())
    assert empty.totals.calls == 0 and empty.by_role == [] and empty.by_model == []


def test_calls_come_newest_first_and_filters_combine(repos: Repositories, two_users) -> None:
    ana, elo = two_users
    repos.ai_usage.add(entry(ana, T0, correlation_id="t1"))
    repos.ai_usage.add(entry(ana, T0 + timedelta(minutes=1), correlation_id="t1", status="failed", error_code="provider_timeout"))
    repos.ai_usage.add(entry(elo, T0 + timedelta(minutes=2), role="authoring", feature="authoring", model="m2"))
    ids = lambda f: [c.entry.created_at.minute for c in repos.ai_usage.calls(Period(), f)[0]]  # noqa: E731
    assert ids(CallFilters()) == [2, 1, 0]
    assert ids(CallFilters(user_id=ana)) == [1, 0]
    assert ids(CallFilters(correlation_id="t1", status="failed")) == [1]
    assert ids(CallFilters(role="authoring")) == [2]
    assert ids(CallFilters(feature="tutor_turn", model="m1", user_id=elo)) == []
    assert ids(CallFilters(model="m2")) == [2]


def test_calls_page_with_has_more(repos: Repositories, two_users) -> None:
    for minute in range(5):
        repos.ai_usage.add(entry(two_users[0], T0 + timedelta(minutes=minute)))
    first, more = repos.ai_usage.calls(Period(), CallFilters(), limit=2)
    assert [c.entry.created_at.minute for c in first] == [4, 3] and more
    last, more = repos.ai_usage.calls(Period(), CallFilters(), limit=2, offset=4)
    assert [c.entry.created_at.minute for c in last] == [0] and not more
    exact, more = repos.ai_usage.calls(Period(), CallFilters(), limit=5)
    assert len(exact) == 5 and not more


def test_deleting_a_user_deletes_their_rows(repos: Repositories, two_users, db_engine) -> None:
    ana, elo = two_users
    repos.ai_usage.add(entry(ana))
    repos.ai_usage.add(entry(elo))
    with db_engine.begin() as conn:
        conn.execute(text("delete from users where id = :i"), {"i": ana})
    users, _ = repos.ai_usage.per_user(Period())
    assert [u.user_id for u in users] == [elo]


def test_deleting_a_course_or_chapter_keeps_the_rows_and_nulls_the_ids(repos: Repositories, two_users, db_engine) -> None:
    ana, _ = two_users
    course = repos.courses.create(ana, "Maths", "mathematics", max_courses=30).id
    chapter = repos.chapters.create(course, "texte", max_chapters=40).id
    repos.ai_usage.add(entry(ana, course_id=course, chapter_id=chapter))
    with db_engine.begin() as conn:
        conn.execute(text("delete from chapters where id = :c"), {"c": chapter})
    (listed,), _ = repos.ai_usage.calls(Period(), CallFilters())
    assert listed.entry.chapter_id is None and listed.entry.course_id == course
    with db_engine.begin() as conn:
        conn.execute(text("delete from courses where id = :c"), {"c": course})
    (listed,), _ = repos.ai_usage.calls(Period(), CallFilters())
    assert listed.entry.course_id is None and listed.course_subject is None
    assert repos.ai_usage.summary(Period()).totals.calls == 1


def test_a_row_whose_course_was_deleted_mid_call_is_stored_without_it(repos: Repositories, two_users) -> None:
    """A call in flight when its course (or chapter) goes: the foreign key refuses the insert, the row is kept."""
    ana, _ = two_users
    repos.ai_usage.add(entry(ana, course_id="a-course-just-deleted", chapter_id="its-chapter", input_tokens=7))
    (listed,), _ = repos.ai_usage.calls(Period(), CallFilters())
    assert (listed.entry.course_id, listed.entry.chapter_id, listed.entry.input_tokens) == (None, None, 7)


def test_a_row_whose_user_is_gone_is_refused(repos: Repositories) -> None:
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        repos.ai_usage.add(entry("nobody", course_id="c"))
    with pytest.raises(IntegrityError):
        repos.ai_usage.add(entry("nobody"))


def test_add_once_stores_a_session_a_single_time(repos: Repositories, two_users) -> None:
    ana, elo = two_users
    session = dict(role="voice", feature="voice_session", correlation_id="s1")
    assert repos.ai_usage.add_once(entry(ana, **session)) is True
    assert repos.ai_usage.add_once(entry(ana, **session)) is False
    assert repos.ai_usage.add_once(entry(elo, **session)) is True  # another user's session with that id
    assert repos.ai_usage.add_once(entry(ana, **{**session, "correlation_id": "s2"})) is True
    assert repos.ai_usage.summary(Period()).totals.calls == 3


def test_add_once_cannot_tell_sessions_without_an_id_apart(repos: Repositories, two_users) -> None:
    ana, _ = two_users
    assert repos.ai_usage.add_once(entry(ana, feature="voice_session")) is True
    assert repos.ai_usage.add_once(entry(ana, feature="voice_session")) is True
    assert repos.ai_usage.summary(Period()).totals.calls == 2
