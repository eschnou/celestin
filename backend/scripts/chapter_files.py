"""A chapter directory (`pack.md` + `curriculum.yaml`) as a `LessonChapter`.

The file format of specs 002–004 survives only as seed and script input
(005 design 3.14): the seed command stores it in the database, and the smoke and
probe scripts run a lesson on it without one.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.chapter import LessonChapter
from app.domain.content import ValidContent, validate_content
from app.domain.curriculum import parse_curriculum
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.pack import ContentIssue
from app.domain.subject import Subject
from app.services.prompts import PromptLibrary

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CHAPTER_DIR = BACKEND_DIR.parent / "courses" / "chapitre_1"
# The English counterpart of chapter 1 (spec 011 R9.1): a fixture written for the tests, so the
# English scripts run without the private course.
DEFAULT_ENGLISH_CHAPTER_DIR = BACKEND_DIR / "tests" / "fixtures" / "chapters" / "sequences_en"


def default_chapter_dir(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> Path:
    return DEFAULT_ENGLISH_CHAPTER_DIR if language == "en" else DEFAULT_CHAPTER_DIR


class ChapterFilesInvalid(RuntimeError):
    def __init__(self, directory: Path, issues: list[ContentIssue]) -> None:
        details = "; ".join(f"{i.where} : {i.message}" for i in issues)
        super().__init__(f"{directory}: {details}")
        self.issues = issues


def load_chapter_files(
    directory: Path,
    subject: Subject,
    prompts: PromptLibrary,
    chapter_id: str | None = None,
    max_chars: int = 60_000,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> ValidContent:
    """Parse and validate both files against the subject's template, with the same
    rules as the editors. `chapter_id` replaces the curriculum's own id when given."""
    pack = (directory / "pack.md").read_text(encoding="utf-8")
    path = directory / "curriculum.yaml"
    curriculum = parse_curriculum(path.read_text(encoding="utf-8"), path, language)
    data = {**curriculum.model_dump(mode="json"), "id": chapter_id or curriculum.id}
    content, issues = validate_content(
        pack, data, prompts.template(subject, language), max_chars, prompts.other_templates(subject, language)
    )
    if content is None:
        raise ChapterFilesInvalid(directory, issues)
    return content


def load_chapter_dir(
    directory: Path,
    subject: Subject,
    prompts: PromptLibrary,
    chapter_id: str | None = None,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> LessonChapter:
    content = load_chapter_files(directory, subject, prompts, chapter_id, language=language)
    return LessonChapter(
        id=content.curriculum.id,
        subject=subject,
        language=language,
        title=content.title,
        pack=content.pack,
        curriculum=content.curriculum,
    )
