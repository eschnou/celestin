from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import make_engine
from app.db.models import ChapterRow, CourseRow, UserRow
from app.domain.progress import Progress


def _prepare(tmp_path, monkeypatch) -> str:
    from alembic import command

    from app.config import get_settings
    from app.db.schema import alembic_config

    url = f"sqlite:///{tmp_path / 'seed.db'}"
    command.upgrade(alembic_config(url), "head")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("ARGON2_MEMORY_KIB", "8192")
    monkeypatch.setenv("ARGON2_TIME", "1")
    get_settings.cache_clear()
    return url


def test_seed_is_idempotent_and_resets_progress(tmp_path, monkeypatch, capsys) -> None:
    from app.config import get_settings
    from app.db.base import make_session_factory
    from app.db.repositories import Repositories
    from scripts.seed import main

    url = _prepare(tmp_path, monkeypatch)
    try:
        assert main(["--email", "Eleve@Example.be", "--password", "mot-de-passe-solide"]) == 0
        engine = make_engine(url)
        repos = Repositories.from_factory(make_session_factory(engine))
        user = repos.users.by_email("eleve@example.be").user
        (entry,) = repos.courses.list_for_user(user.id)
        (chapter,) = entry.chapters
        assert entry.course.name == "Mathématiques 5e" and entry.course.subject == "mathematics"
        assert chapter.ready and chapter.content_version == 1 and chapter.title == "Les suites numériques"
        repos.progress.save(user.id, chapter.id, Progress(active="suites"))

        assert main(["--email", "eleve@example.be", "--password", "autre-mot-de-passe"]) == 0
        with Session(engine) as s:
            assert s.scalar(select(func.count()).select_from(UserRow)) == 1
            assert s.scalar(select(func.count()).select_from(CourseRow)) == 1
            assert s.scalar(select(func.count()).select_from(ChapterRow)) == 1
            assert s.get(ChapterRow, chapter.id).content_version == 2
        assert repos.progress.load(user.id, chapter.id) is None
        assert f"/courses/{entry.course.id}/chapters/{chapter.id}" in capsys.readouterr().out
    finally:
        get_settings.cache_clear()


def test_seed_refuses_a_non_sqlite_database(monkeypatch, capsys) -> None:
    from app.config import get_settings
    from scripts.seed import main

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x@localhost/celestin")
    get_settings.cache_clear()
    try:
        assert main(["--email", "a@b.be", "--password", "x"]) == 2
        assert "--force" in capsys.readouterr().err
    finally:
        get_settings.cache_clear()
