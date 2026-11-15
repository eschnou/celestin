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
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.pack import ContentIssue
from app.domain.revision import RevisionChapter, RevisionScope
from app.domain.subject import Subject
from app.services.prompts import PromptLibrary

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Chapter 1 on sequences, in French, English and Dutch (spec 011 R9.1, spec 017): fixtures written for the tests,
# so the scripts and the suite run without a real course (a student's material is not in the repository).
DEFAULT_CHAPTER_DIR = BACKEND_DIR / "tests" / "fixtures" / "chapters" / "suites"
DEFAULT_ENGLISH_CHAPTER_DIR = BACKEND_DIR / "tests" / "fixtures" / "chapters" / "sequences_en"
DEFAULT_DUTCH_CHAPTER_DIR = BACKEND_DIR / "tests" / "fixtures" / "chapters" / "rijen_nl"


DEFAULT_CHAPTER_DIRS = by_language(
    fr=DEFAULT_CHAPTER_DIR, en=DEFAULT_ENGLISH_CHAPTER_DIR, nl=DEFAULT_DUTCH_CHAPTER_DIR
)


def default_chapter_dir(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> Path:
    return DEFAULT_CHAPTER_DIRS[language]


_FIXTURES = BACKEND_DIR / "tests" / "fixtures" / "chapters"
# A révision of two chapters (spec 020): sequences then statistics, in each course language. What the révision
# pins, the smoke and the révision probes run on. They are mathematics chapters, whatever subject a script was given.
REVISION_SUBJECT: Subject = "mathematics"
REVISION_CHAPTER_DIRS = by_language(
    fr=(_FIXTURES / "suites", _FIXTURES / "statistique"),
    en=(_FIXTURES / "sequences_en", _FIXTURES / "statistics_en"),
    nl=(_FIXTURES / "rijen_nl", _FIXTURES / "statistiek_nl"),
)


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


def revision_scope(
    chapters: list[LessonChapter], revision_id: str = "revision", course_id: str = "course"
) -> RevisionScope:
    """Chapters loaded from files as a révision's scope, numbered 1, 2, … in the order given; no progress, nothing
    noted before (spec 020)."""
    return RevisionScope(
        id=revision_id,
        course_id=course_id,
        chapters=tuple(
            RevisionChapter(
                number=number,
                id=chapter.id,
                title=chapter.title,
                version=chapter.version,
                pack=chapter.pack,
                curriculum=chapter.curriculum,
            )
            for number, chapter in enumerate(chapters, start=1)
        ),
    )


def load_revision(
    subject: Subject,
    prompts: PromptLibrary,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    directories: tuple[Path, ...] | None = None,
) -> RevisionScope:
    """The fixture révision of `language` (or the chapters of `directories`) as a scope."""
    chosen = directories or REVISION_CHAPTER_DIRS[language]
    return revision_scope([load_chapter_dir(d, subject, prompts, language=language) for d in chosen])
