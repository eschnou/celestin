"""The curriculum: an ordered path of sections through a chapter (design 4.1).

`pack.md` says what the teacher teaches; `curriculum.yaml` says in which order
Célestin teaches it. Cross-field rules live here so a bad file fails at startup with
the section named (R2.6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.domain.errors import CurriculumInvalid, format_validation_errors
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.pack import ContentIssue, chapter_title

Kind = Literal["teach", "practise", "synthesis"]
KIND_LABEL_FR: dict[str, str] = {"teach": "cours", "practise": "exercices", "synthesis": "synthèse"}
# What the model reads for a section's kind, per course language (spec 011 §4.1). The wire
# values `teach`, `practise`, `synthesis` do not change.
KIND_LABELS = by_language(
    fr=KIND_LABEL_FR,
    en={"teach": "lesson", "practise": "practice", "synthesis": "summary"},
    nl={"teach": "les", "practise": "oefeningen", "synthesis": "samenvatting"},
)

Text = Annotated[str, Field(min_length=1, max_length=600)]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")]


class RuleViolation(ValueError):
    """A curriculum rule of ours that a section or the path breaks. The message is the
    French sentence the repair prompt reads; `code` and `params` let the student's
    editor say it in the interface language (`ContentIssue`, spec 010 §4.9)."""

    def __init__(self, message: str, code: str, **params: object) -> None:
        super().__init__(message)
        self.code = code
        self.params = params


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Section(_Model):
    """One step of the path. `index` is its 1-based position, assigned by the
    curriculum once validated; `label` is the « 5. Title » form the model and the
    learner both see."""

    _index: int = PrivateAttr(default=0)
    id: Slug
    kind: Kind
    title: Text
    goal: Text
    done_when: Text
    pack: list[Text] = []
    beats: Annotated[list[Text], Field(max_length=12)] = []
    exercises: Annotated[list[Text], Field(max_length=12)] = []
    count: Annotated[int, Field(ge=1, le=10)] | None = None

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> Section:
        if self.kind == "teach":
            if not self.beats:
                raise RuleViolation("une section « teach » doit avoir des beats", "curriculum.teach_beats")
            if self.exercises or self.count is not None:
                raise RuleViolation(
                    "une section « teach » n'a ni exercises ni count", "curriculum.teach_extras"
                )
        else:
            if not self.exercises:
                raise RuleViolation(
                    f"une section « {self.kind} » doit lister des exercises",
                    "curriculum.exercises_required",
                    kind=self.kind,
                )
            if self.count is None:
                raise RuleViolation(
                    f"une section « {self.kind} » doit avoir un count",
                    "curriculum.count_required",
                    kind=self.kind,
                )
            if self.beats:
                raise RuleViolation(
                    f"une section « {self.kind} » n'a pas de beats",
                    "curriculum.beats_forbidden",
                    kind=self.kind,
                )
        return self

    @property
    def index(self) -> int:
        return self._index

    @property
    def label(self) -> str:
        return f"{self._index}. {self.title}"


class Curriculum(_Model):
    id: Slug
    title: Text
    sections: Annotated[list[Section], Field(min_length=1, max_length=40)]

    @field_validator("title")
    @classmethod
    def _without_numbering(cls, value: str, info: ValidationInfo) -> str:
        """The course numbers its chapters by position; a « Chapitre 1 » the material
        carried is dropped here too, so an older stored path is cleaned on read. The
        numbering words are the course language's, read from the validation context."""
        return chapter_title(value, (info.context or {}).get("language", DEFAULT_COURSE_LANGUAGE))

    @model_validator(mode="after")
    def _ids_unique_and_indexed(self) -> Curriculum:
        seen: set[str] = set()
        for index, section in enumerate(self.sections, start=1):
            if section.id in seen:
                raise RuleViolation(
                    f"identifiant de section en double : {section.id}",
                    "curriculum.duplicate_id",
                    id=section.id,
                )
            seen.add(section.id)
            section._index = index
        return self

    def get(self, section_id: str) -> Section | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None


def parse_curriculum(
    text: str, path: Path | str = "curriculum.yaml", language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Curriculum:
    """`safe_load` then validate; every failure becomes `CurriculumInvalid` naming the
    file and, when known, the section."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise CurriculumInvalid(str(path), f"YAML illisible : {exc}") from exc
    if not isinstance(data, dict):
        raise CurriculumInvalid(str(path), "le document doit être un objet YAML")
    try:
        return Curriculum.model_validate(data, context={"language": language})
    except ValidationError as exc:
        raise CurriculumInvalid(str(path), _describe(exc, data)) from exc


def curriculum_from_json(data: object, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> Curriculum:
    """A curriculum stored or edited as JSON (005 design 3.6). Raises `ValidationError`."""
    return Curriculum.model_validate(data, context={"language": language})


def check_curriculum(
    data: object, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> tuple[Curriculum | None, list[ContentIssue]]:
    """The curriculum, or why `data` is not one: one issue per error, naming the section."""
    try:
        return Curriculum.model_validate(data, context={"language": language}), []
    except ValidationError as exc:
        locate = _locator(data if isinstance(data, dict) else {})
        issues = []
        for err in exc.errors()[:20]:
            loc = tuple(err["loc"])
            where = locate(loc)
            field = ".".join(str(p) for p in loc[2:]) if where.startswith("section") else ""
            msg = str(err["msg"]).removeprefix("Value error, ")
            message = msg if not field else f"{field} : {msg}"
            rule = (err.get("ctx") or {}).get("error")
            if isinstance(rule, RuleViolation):
                # A rule of ours: the student's editor says it from its code (spec 010 §4.9).
                issues.append(ContentIssue(where, message, rule.code, rule.params))
            elif field:
                issues.append(ContentIssue(where, message, "curriculum.field", {"field": field, "msg": msg}))
            else:
                issues.append(ContentIssue(where, message, "curriculum.error", {"msg": msg}))
        return None, issues


def _locator(data: dict):  # noqa: ANN202
    sections = data.get("sections") if isinstance(data.get("sections"), list) else []

    def locate(loc: tuple) -> str:
        where = ".".join(str(p) for p in loc) or "parcours"
        if len(loc) >= 2 and loc[0] == "sections" and isinstance(loc[1], int) and loc[1] < len(sections):
            entry = sections[loc[1]]
            if isinstance(entry, dict) and entry.get("id"):
                return f"section « {entry['id']} »"
            return f"section n°{loc[1] + 1}"
        return where

    return locate


def _describe(exc: ValidationError, data: dict) -> str:
    locate = _locator(data)

    def with_path(loc: tuple) -> str:
        where = locate(loc)
        dotted = ".".join(str(p) for p in loc) or "(racine)"
        return f"{where} ({dotted})" if where.startswith("section") else where

    return format_validation_errors(exc, with_path)
