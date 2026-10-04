"""Course and chapter wire DTOs (005 design 4.3)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.schemas.chapter import ChapterResponse
from app.api.schemas.chat import ProgressDTO
from app.domain.chapter import AuthoringState, SourceKind, Stage
from app.domain.curriculum import Kind
from app.domain.language import CourseLanguage
from app.domain.subject import Subject


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


ChapterState = Literal["not_started", "in_progress", "done"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Limits(_Model):
    chapter_text_min_chars: int
    chapter_text_max_chars: int
    pack_max_chars: int
    document_max_bytes: int
    document_max_pages: int
    document_min_pixels: int
    document_types: list[str]


class SubjectDTO(_Model):
    id: Subject
    label: str
    languages: list[CourseLanguage]


class SubjectsResponse(_Model):
    subjects: list[SubjectDTO]
    limits: Limits


class CreateCourseRequest(_Model):
    name: Name
    subject: Annotated[str, Field(max_length=40)]
    # Missing means French: clients written before spec 011 keep working.
    language: Annotated[str, Field(max_length=8)] = "fr"


class RenameCourseRequest(_Model):
    name: Name


class ChapterRefDTO(_Model):
    id: str
    title: str


class ChapterRow(_Model):
    id: str
    position: int
    title: str | None
    ready: bool
    section_count: int
    done_count: int
    state: ChapterState
    last: bool
    authoring_state: AuthoringState
    authoring_message: str | None
    authoring_stage: Stage | None
    pages_done: int
    page_count: int


class CourseSummary(_Model):
    id: str
    name: str
    subject: Subject
    subject_label: str
    language: CourseLanguage
    chapters_total: int
    chapters_done: int
    last_chapter: ChapterRefDTO | None
    generating: int


class CoursesResponse(_Model):
    courses: list[CourseSummary]


class CourseDetail(CourseSummary):
    chapters: list[ChapterRow]


class SourceRequest(_Model):
    """A corrected transcription (`PUT …/source`). Length is checked against the
    settings in the route (SourceLength, 422)."""

    source_text: str


class SectionIn(_Model):
    """A section as the curriculum editor sends it; the domain validates it again."""

    id: str
    kind: Kind
    title: str
    goal: str
    done_when: str
    pack: list[str] = []
    beats: list[str] = []
    exercises: list[str] = []
    count: int | None = None


class CurriculumIn(_Model):
    title: str
    sections: Annotated[list[SectionIn], Field(max_length=60)]


class SavePackRequest(_Model):
    version: int
    pack: Annotated[str, Field(max_length=200_000)]


class SaveCurriculumRequest(_Model):
    version: int
    curriculum: CurriculumIn


class SectionFullDTO(SectionIn):
    index: int


class CurriculumFullDTO(_Model):
    title: str
    sections: list[SectionFullDTO]


class ChapterContent(_Model):
    """The student's own view of a chapter: everything, including what the lesson
    view never sends (beats, pools, done-when)."""

    id: str
    course_id: str
    subject: Subject
    language: CourseLanguage
    position: int
    version: int
    ready: bool
    title: str | None
    pack: str | None
    curriculum: CurriculumFullDTO | None
    source_text: str
    source_kind: SourceKind
    page_count: int
    authoring_state: AuthoringState
    authoring_message: str | None
    has_progress: bool


class ChapterView(ChapterResponse):
    """`title` is the displayed name: « Chapitre <position> — <titre> » (006)."""

    position: int
    course_id: str
    course_name: str
    subject: Subject
    language: CourseLanguage
    progress: ProgressDTO
