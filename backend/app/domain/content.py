"""A chapter's content as one valid whole (005 design 3.5, 3.6).

Every writer of chapter content (the editors, the authoring agent, the seed) goes
through these checks, and adoption only accepts their result, so stored content is
valid by construction rather than by each caller remembering every rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.curriculum import Curriculum, check_curriculum
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.pack import ContentIssue, PackIndex, PackTemplate, index_pack
from app.domain.references import reference_issues


@dataclass(frozen=True)
class ValidContent:
    pack: str
    index: PackIndex
    curriculum: Curriculum

    @property
    def title(self) -> str:
        return self.index.title


def validate_curriculum(
    data: object, index: PackIndex, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> tuple[Curriculum | None, list[ContentIssue]]:
    """The curriculum's own rules, then its references into the indexed pack."""
    curriculum, issues = check_curriculum(data, language)
    if curriculum is None:
        return None, issues
    issues = reference_issues(curriculum, index)
    return (None, issues) if issues else (curriculum, [])


def validate_content(
    pack: str,
    curriculum_data: object,
    template: PackTemplate,
    max_chars: int,
    alternatives: Sequence[PackTemplate] = (),
) -> tuple[ValidContent | None, list[ContentIssue]]:
    """The template carries the course language (`template.language`); `alternatives` are the
    subject's templates in the other languages, to recognise a pack written for another."""
    index, issues = index_pack(pack, template, max_chars, alternatives)
    if index is None:
        return None, issues
    curriculum, issues = validate_curriculum(curriculum_data, index, template.language)
    if curriculum is None:
        return None, issues
    return ValidContent(pack=pack, index=index, curriculum=curriculum), []
