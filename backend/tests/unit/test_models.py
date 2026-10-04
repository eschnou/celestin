from __future__ import annotations

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import UserRow


def test_role_is_checked(db_engine: Engine) -> None:
    with Session(db_engine) as s:
        s.add(UserRow(id="u1", email="a@b.be", name="A", password_hash="h", role="teacher", created_at=utcnow()))
        with pytest.raises(IntegrityError):
            s.commit()


def test_email_is_unique(db_engine: Engine) -> None:
    with Session(db_engine) as s:
        s.add(UserRow(id="u1", email="a@b.be", name="A", password_hash="h", role="student", created_at=utcnow()))
        s.commit()
        s.add(UserRow(id="u2", email="a@b.be", name="B", password_hash="h", role="student", created_at=utcnow()))
        with pytest.raises(IntegrityError):
            s.commit()


def test_engine_creates_a_missing_database_directory(tmp_path) -> None:
    """004: a fresh clone has no `data/`; SQLite makes the file, never the folder."""
    from sqlalchemy import text

    from app.db.base import make_engine

    target = tmp_path / "never-created" / "celestin.db"
    engine = make_engine(f"sqlite:///{target}")
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    assert target.parent.is_dir() and target.exists()


def _course_and_chapter(s: Session) -> None:
    from app.db.models import ChapterRow, CourseRow

    now = utcnow()
    s.add(UserRow(id="u1", email="a@b.be", name="A", password_hash="h", role="student", created_at=now))
    s.flush()
    s.add(CourseRow(id="c1", user_id="u1", name="Physique", subject="sciences", created_at=now, updated_at=now))
    s.flush()  # no ORM relationships: parents first, explicitly
    s.add(
        ChapterRow(
            id="h1", course_id="c1", position=1, source_text="t", created_at=now, updated_at=now,
        )
    )
    s.commit()


def test_course_subject_is_checked(db_engine: Engine) -> None:
    from app.db.models import CourseRow

    with Session(db_engine) as s:
        now = utcnow()
        s.add(UserRow(id="u1", email="a@b.be", name="A", password_hash="h", role="student", created_at=now))
        s.flush()
        s.add(CourseRow(id="c1", user_id="u1", name="X", subject="astrologie", created_at=now, updated_at=now))
        with pytest.raises(IntegrityError):
            s.commit()


def test_chapter_defaults(db_engine: Engine) -> None:
    from app.db.models import ChapterRow

    with Session(db_engine) as s:
        _course_and_chapter(s)
        row = s.get(ChapterRow, "h1")
        assert row.content_version == 0 and row.authoring_state == "idle" and row.pack is None


def test_deleting_a_course_cascades_to_chapters_and_progress_and_nulls_runs(db_engine: Engine) -> None:
    from sqlalchemy import delete, select

    from app.db.models import AuthoringRunRow, ChapterRow, CourseRow, ProgressRow

    with Session(db_engine) as s:
        _course_and_chapter(s)
        now = utcnow()
        s.add(ProgressRow(user_id="u1", chapter_id="h1", done=[], active=None, updated_at=now))
        s.flush()
        s.add(AuthoringRunRow(id="r1", user_id="u1", chapter_id="h1", trigger="create", state="succeeded", model="m", started_at=now))
        s.commit()
        s.execute(delete(CourseRow).where(CourseRow.id == "c1"))
        s.commit()
        assert s.scalars(select(ChapterRow)).all() == []
        assert s.scalars(select(ProgressRow)).all() == []
        run = s.get(AuthoringRunRow, "r1")
        s.refresh(run)
        assert run.chapter_id is None


def test_progress_requires_an_existing_chapter(db_engine: Engine) -> None:
    from app.db.models import ProgressRow

    with Session(db_engine) as s:
        _course_and_chapter(s)
        s.add(ProgressRow(user_id="u1", chapter_id="ghost", done=[], active=None, updated_at=utcnow()))
        with pytest.raises(IntegrityError):
            s.commit()
