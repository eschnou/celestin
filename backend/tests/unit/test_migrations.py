"""004 design 3.8: the migrations and the models agree, and the check bites."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from app.db.base import Base, make_engine
from app.db.schema import alembic_config, check_schema
from app.domain.errors import SchemaOutdated


def test_head_matches_the_models(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(alembic_config(url), "head")
    engine = make_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
    check_schema(engine)


def test_check_schema_refuses_an_empty_database() -> None:
    engine = make_engine("sqlite://")
    with pytest.raises(SchemaOutdated, match="alembic upgrade head"):
        check_schema(engine)


def test_upgrade_from_0002_drops_enrolments_and_adds_courses(tmp_path) -> None:
    from sqlalchemy import inspect

    url = f"sqlite:///{tmp_path / 'u.db'}"
    command.upgrade(alembic_config(url), "0002")
    command.upgrade(alembic_config(url), "head")
    tables = set(inspect(make_engine(url)).get_table_names())
    assert {"courses", "chapters", "authoring_runs", "progress"} <= tables
    assert "enrolments" not in tables
    command.downgrade(alembic_config(url), "0002")
    assert "enrolments" in set(inspect(make_engine(url)).get_table_names())


def test_upgrade_from_0003_adds_document_columns(tmp_path) -> None:
    from sqlalchemy import inspect

    url = f"sqlite:///{tmp_path / 'd.db'}"
    command.upgrade(alembic_config(url), "0003")
    command.upgrade(alembic_config(url), "head")
    inspector = inspect(make_engine(url))
    assert "chapter_uploads" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("chapters")}
    assert {"source_kind", "authoring_stage", "pages_done", "page_count"} <= columns
    command.downgrade(alembic_config(url), "0003")
    assert "chapter_uploads" not in inspect(make_engine(url)).get_table_names()


def test_upgrade_from_0005_gives_existing_users_french(tmp_path) -> None:
    from sqlalchemy import inspect, text

    url = f"sqlite:///{tmp_path / 'l.db'}"
    command.upgrade(alembic_config(url), "0005")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, email, name, password_hash, role, created_at) "
                "values ('u1', 'a@x.be', 'Ana', 'h', 'student', '2026-01-01 00:00:00')"
            )
        )
    command.upgrade(alembic_config(url), "head")
    with make_engine(url).connect() as conn:
        assert conn.execute(text("select locale from users where id = 'u1'")).scalar_one() == "fr"
    command.downgrade(alembic_config(url), "0005")
    assert "locale" not in {c["name"] for c in inspect(make_engine(url)).get_columns("users")}
    command.upgrade(alembic_config(url), "head")
    assert "locale" in {c["name"] for c in inspect(make_engine(url)).get_columns("users")}


def test_upgrade_from_0006_leaves_existing_courses_french(tmp_path) -> None:
    from sqlalchemy import inspect, text

    url = f"sqlite:///{tmp_path / 'c.db'}"
    command.upgrade(alembic_config(url), "0006")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, email, name, password_hash, role, locale, created_at) "
                "values ('u1', 'a@x.be', 'Ana', 'h', 'student', 'fr', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into courses (id, user_id, name, subject, created_at, updated_at) "
                "values ('c1', 'u1', 'Maths', 'mathematics', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
    command.upgrade(alembic_config(url), "head")
    with make_engine(url).connect() as conn:
        assert conn.execute(text("select language from courses where id = 'c1'")).scalar_one() == "fr"
    command.downgrade(alembic_config(url), "0006")
    assert "language" not in {c["name"] for c in inspect(make_engine(url)).get_columns("courses")}
    command.upgrade(alembic_config(url), "head")
    assert "language" in {c["name"] for c in inspect(make_engine(url)).get_columns("courses")}


def test_upgrade_from_0007_keeps_every_account_enabled_and_every_course(tmp_path) -> None:
    from sqlalchemy import inspect, text

    url = f"sqlite:///{tmp_path / 'e.db'}"
    command.upgrade(alembic_config(url), "0007")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, email, name, password_hash, role, locale, created_at) "
                "values ('u1', 'a@x.be', 'Ana', 'h', 'student', 'fr', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into courses (id, user_id, name, subject, language, created_at, updated_at) "
                "values ('c1', 'u1', 'Maths', 'mathematics', 'fr', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
    command.upgrade(alembic_config(url), "head")
    with make_engine(url).connect() as conn:
        assert conn.execute(text("select enabled from users where id = 'u1'")).scalar_one() == 1
        # The upgrade must not rebuild `users`: with foreign keys on, that deletes the courses.
        assert conn.execute(text("select count(*) from courses")).scalar_one() == 1
    command.downgrade(alembic_config(url), "0007")
    assert "enabled" not in {c["name"] for c in inspect(make_engine(url)).get_columns("users")}


def test_upgrade_from_0008_keeps_every_row_and_adds_app_settings(tmp_path) -> None:
    from sqlalchemy import inspect, text

    url = f"sqlite:///{tmp_path / 'f.db'}"
    command.upgrade(alembic_config(url), "0008")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, email, name, password_hash, role, locale, enabled, created_at) "
                "values ('u1', 'a@x.be', 'Ana', 'h', 'student', 'fr', 1, '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into courses (id, user_id, name, subject, language, created_at, updated_at) "
                "values ('c1', 'u1', 'Maths', 'mathematics', 'fr', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
    command.upgrade(alembic_config(url), "head")
    with make_engine(url).connect() as conn:
        assert conn.execute(text("select count(*) from users")).scalar_one() == 1
        assert conn.execute(text("select count(*) from courses")).scalar_one() == 1
        assert conn.execute(text("select count(*) from app_settings")).scalar_one() == 0
    assert {c["name"] for c in inspect(make_engine(url)).get_columns("app_settings")} == {
        "key",
        "value",
        "updated_at",
        "updated_by",
    }
    command.downgrade(alembic_config(url), "0008")
    assert "app_settings" not in inspect(make_engine(url)).get_table_names()
    command.upgrade(alembic_config(url), "head")


def test_upgrade_from_0009_carries_voice_usage_into_the_ledger(tmp_path) -> None:
    from sqlalchemy import inspect, text

    url = f"sqlite:///{tmp_path / 'g.db'}"
    command.upgrade(alembic_config(url), "0009")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, email, name, password_hash, role, locale, created_at) "
                "values ('u1', 'a@x.be', 'Ana', 'h', 'student', 'fr', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into courses (id, user_id, name, subject, language, created_at, updated_at) "
                "values ('c1', 'u1', 'Maths', 'mathematics', 'fr', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        for session, reason in (("s1", "learner"), ("s2", "error")):
            conn.execute(
                text(
                    "insert into voice_usage (user_id, session_id, reason, duration_s, responses, input_text, "
                    "input_audio, cached_text, cached_audio, output_text, output_audio, cost_estimate_usd, "
                    "created_at) values ('u1', :s, :r, 90, 3, 100, 40, 20, 10, 50, 30, 0.12, "
                    "'2026-02-01 10:00:00')"
                ),
                {"s": session, "r": reason},
            )
    command.upgrade(alembic_config(url), "head")
    with make_engine(url).connect() as conn:
        assert "voice_usage" not in inspect(conn).get_table_names()
        rows = conn.execute(
            text(
                "select correlation_id, role, feature, status, error_code, model, input_tokens, cached_tokens, "
                "output_tokens, input_audio_tokens, output_audio_tokens, audio_seconds, cost_usd, created_at "
                "from ai_usage order by correlation_id"
            )
        ).all()
        assert [tuple(r)[:6] for r in rows] == [
            ("s1", "voice", "voice_session", "ok", None, ""),
            ("s2", "voice", "voice_session", "failed", "voice_error", ""),
        ]
        assert tuple(rows[0])[6:13] == (140, 30, 80, 40, 30, 90.0, None)
        assert str(rows[0][13]).startswith("2026-02-01 10:00:00")
        # The upgrade must not rebuild `users`: with foreign keys on, that deletes the courses.
        assert conn.execute(text("select count(*) from courses")).scalar_one() == 1
    command.downgrade(alembic_config(url), "0009")
    with make_engine(url).connect() as conn:
        assert "ai_usage" not in inspect(conn).get_table_names()
        rows = conn.execute(
            text(
                "select session_id, reason, duration_s, input_text, input_audio, cached_text, output_text, "
                "output_audio from voice_usage order by session_id"
            )
        ).all()
        assert [tuple(r) for r in rows] == [("s1", "learner", 90, 100, 40, 30, 50, 30), ("s2", "error", 90, 100, 40, 30, 50, 30)]
    command.upgrade(alembic_config(url), "head")


def test_the_ledger_follows_the_user_and_forgets_a_deleted_course(tmp_path) -> None:
    from sqlalchemy import text

    url = f"sqlite:///{tmp_path / 'h.db'}"
    command.upgrade(alembic_config(url), "head")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into users (id, email, name, password_hash, role, locale, created_at) "
                "values ('u1', 'a@x.be', 'Ana', 'h', 'student', 'fr', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into courses (id, user_id, name, subject, language, created_at, updated_at) "
                "values ('c1', 'u1', 'Maths', 'mathematics', 'fr', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into ai_usage (created_at, user_id, course_id, role, feature, model, provider, status) "
                "values ('2026-02-01 10:00:00', 'u1', 'c1', 'tutor', 'tutor_turn', 'm', 'h', 'ok')"
            )
        )
    with engine.begin() as conn:
        conn.execute(text("delete from courses where id = 'c1'"))
        assert conn.execute(text("select course_id from ai_usage")).one() == (None,)
        conn.execute(text("delete from users where id = 'u1'"))
        assert conn.execute(text("select count(*) from ai_usage")).scalar_one() == 0
