from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.repositories import Repositories
from app.domain.progress import Progress

NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)


def test_users_round_trip(repos: Repositories) -> None:
    user = repos.users.create("a@b.be", "Léa", "hash")
    assert user.role == "student"
    stored = repos.users.by_email("a@b.be")
    assert stored and stored.user == user and stored.password_hash == "hash"
    assert repos.users.by_id(user.id) == user
    assert repos.users.by_email("nobody@b.be") is None
    repos.users.update_hash(user.id, "hash2")
    assert repos.users.by_email("a@b.be").password_hash == "hash2"  # type: ignore[union-attr]


def test_a_user_has_an_interface_language(repos: Repositories) -> None:
    french = repos.users.create("a@b.be", "Léa", "hash")
    english = repos.users.create("e@b.be", "Ann", "hash", locale="en")
    assert french.locale == "fr" and english.locale == "en"
    assert repos.users.by_id(english.id).locale == "en"  # type: ignore[union-attr]
    assert repos.users.by_email("e@b.be").user.locale == "en"  # type: ignore[union-attr]
    changed = repos.users.set_locale(french.id, "en")
    assert changed and changed.locale == "en"
    assert repos.users.by_id(french.id).locale == "en"  # type: ignore[union-attr]
    assert repos.users.set_locale("absent", "fr") is None


def test_a_session_lookup_carries_the_language(repos: Repositories) -> None:
    user = repos.users.create("e@b.be", "Ann", "hash", locale="en")
    repos.sessions.create(user.id, "th", now=NOW)
    found = repos.sessions.lookup("th")
    assert found and found[1].locale == "en"


def test_sessions_lifecycle(repos: Repositories) -> None:
    user = repos.users.create("a@b.be", "Léa", "hash")
    created = repos.sessions.create(user.id, "th", now=NOW)
    found = repos.sessions.by_token_hash("th")
    assert found == created and found.last_seen_at == NOW
    repos.sessions.touch(created.id, NOW + timedelta(hours=2))
    assert repos.sessions.by_token_hash("th").last_seen_at == NOW + timedelta(hours=2)  # type: ignore[union-attr]
    repos.sessions.delete(created.id)
    assert repos.sessions.by_token_hash("th") is None


def test_sessions_purge(repos: Repositories) -> None:
    user = repos.users.create("a@b.be", "Léa", "hash")
    repos.sessions.create(user.id, "fresh", now=NOW)
    repos.sessions.create(user.id, "idle", now=NOW - timedelta(days=40))
    old = repos.sessions.create(user.id, "old", now=NOW - timedelta(days=100))
    repos.sessions.touch(old.id, NOW)
    purged = repos.sessions.purge_expired(NOW, idle=timedelta(days=30), absolute=timedelta(days=90))
    assert purged == 2
    assert repos.sessions.by_token_hash("fresh") and not repos.sessions.by_token_hash("idle")
    assert repos.sessions.by_token_hash("old") is None


def _chapters(repos: Repositories, user_id: str, n: int = 2) -> list[str]:
    course = repos.courses.create(user_id, "Maths", "mathematics", max_courses=30)
    return [repos.chapters.create(course.id, f"texte {i}", max_chapters=40).id for i in range(n)]


def test_progress_upsert_clear_and_for_chapters(repos: Repositories) -> None:
    user = repos.users.create("a@b.be", "Léa", "hash")
    suites, limites = _chapters(repos, user.id)
    assert repos.progress.load(user.id, suites) is None
    repos.progress.save(user.id, suites, Progress(active="intro"))
    record = repos.progress.load(user.id, suites)
    assert record and record.progress == Progress(active="intro")
    repos.progress.save(user.id, suites, Progress(done=frozenset({"intro"}), active=None))
    assert repos.progress.load(user.id, suites).progress.done == frozenset({"intro"})  # type: ignore[union-attr]
    repos.progress.save(user.id, limites, Progress())
    by_chapter = repos.progress.for_chapters(user.id, [suites, limites, "absent"])
    assert set(by_chapter) == {suites, limites}
    assert repos.progress.for_chapters(user.id, []) == {}
    repos.progress.clear(user.id, suites)
    assert repos.progress.load(user.id, suites) is None


def test_progress_is_per_user(repos: Repositories) -> None:
    a = repos.users.create("a@b.be", "A", "h")
    b = repos.users.create("b@b.be", "B", "h")
    (suites,) = _chapters(repos, a.id, 1)
    repos.progress.save(a.id, suites, Progress(active="intro"))
    assert repos.progress.load(b.id, suites) is None


def test_voice_usage_row(repos: Repositories, db_engine) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.api.schemas.voice import VoiceUsageReport, VoiceUsageTotals
    from app.db.models import VoiceUsageRow

    user = repos.users.create("a@b.be", "Léa", "hash")
    report = VoiceUsageReport(
        session_id="s1", reason="learner", duration_s=60, responses=2, usage=VoiceUsageTotals(input_audio=5)
    )
    repos.voice_usage.add(user.id, report, 0.01)
    with Session(db_engine) as s:
        row = s.scalar(select(VoiceUsageRow))
    assert row and row.input_audio == 5 and row.user_id == user.id and row.cost_estimate_usd == 0.01
    assert row.session_id == "s1" and row.reason == "learner"


def test_session_lookup_joins_the_user(repos: Repositories) -> None:
    user = repos.users.create("a@b.be", "Léa", "hash")
    repos.sessions.create(user.id, "th", now=NOW)
    found = repos.sessions.lookup("th")
    assert found and found[0].user_id == user.id and found[1] == user
    assert repos.sessions.lookup("nope") is None
