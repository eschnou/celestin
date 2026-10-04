"""A local test student with chapter 1, without the authoring agent (005 R11).

    uv run python -m scripts.seed --email eleve@example.be --password 'mot-de-passe-solide'
        [--name Léa] [--chapter-dir tests/fixtures/chapters/suites] [--language en] [--force]

Idempotent: one user, one « Mathématiques 5e » course, one chapter whose content
is refreshed from the files (and whose progress is therefore reset). Refuses a
non-SQLite database unless `--force`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import Settings, get_settings
from app.db.base import make_engine, make_session_factory
from app.db.repositories import Repositories
from app.db.schema import check_schema
from app.domain.language import COURSE_LANGUAGES, DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.subject import Subject
from app.services.auth_service import PasswordHasher
from app.services.prompts import PromptLibrary
from scripts.chapter_files import DEFAULT_CHAPTER_DIR, default_chapter_dir, load_chapter_files

COURSE_NAME = "Mathématiques 5e"
COURSE_NAME_BY_LANGUAGE = {"fr": COURSE_NAME, "en": "Mathematics Year 5"}


def install_chapter(
    repos: Repositories,
    prompts: PromptLibrary,
    settings: Settings,
    *,
    user_id: str,
    directory: Path = DEFAULT_CHAPTER_DIR,
    course_name: str = COURSE_NAME,
    subject: Subject = "mathematics",
    course_id: str | None = None,
    chapter_id: str | None = None,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> tuple[str, str]:
    """Find or create the course and its first chapter, then adopt the files as its
    content through the same transaction the editors and the runner use. The pack
    stands in for the pasted text: chapter 1 has no original."""
    course = repos.courses.find_by_name(user_id, course_name) or repos.courses.create(
        user_id, course_name, subject, settings.max_courses_per_student, course_id=course_id, language=language
    )
    chapter = repos.chapters.first_of(course.id)
    if chapter is None:
        pack = (directory / "pack.md").read_text(encoding="utf-8")
        chapter = repos.chapters.create(course.id, pack, settings.max_chapters_per_course, chapter_id=chapter_id)
    content = load_chapter_files(directory, subject, prompts, chapter.id, settings.pack_max_chars, language)
    repos.chapters.adopt_content(chapter.id, content)
    return course.id, chapter.id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Élève")
    parser.add_argument("--chapter-dir", type=Path)
    parser.add_argument("--language", choices=list(COURSE_LANGUAGES), default=DEFAULT_COURSE_LANGUAGE, help="the course language")
    parser.add_argument("--force", action="store_true", help="allow a non-SQLite DATABASE_URL")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.database_url.startswith("sqlite") and not args.force:
        print("Refusé : DATABASE_URL n'est pas SQLite. Ajoute --force si c'est voulu.", file=sys.stderr)
        return 2
    engine = make_engine(settings.database_url)
    check_schema(engine)
    repos = Repositories.from_factory(make_session_factory(engine))
    hasher = PasswordHasher(settings.argon2_memory_kib, settings.argon2_time, settings.argon2_parallelism)
    email = args.email.strip().lower()
    stored = repos.users.by_email(email)
    if stored is None:
        user = repos.users.create(email, args.name, hasher.hash(args.password))
    else:
        user = stored.user
        repos.users.update_hash(user.id, hasher.hash(args.password))
    course_id, chapter_id = install_chapter(
        repos,
        PromptLibrary(settings.prompts_dir),
        settings,
        user_id=user.id,
        directory=args.chapter_dir or default_chapter_dir(args.language),
        course_name=COURSE_NAME_BY_LANGUAGE[args.language],
        language=args.language,
    )
    print(f"élève {email} · cours {course_id} · chapitre {chapter_id}")
    print(f"/courses/{course_id}/chapters/{chapter_id}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
