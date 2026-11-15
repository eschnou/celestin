"""The open path (design 3.4, spec 019). Pure: curriculum + progress in, states out.

No section is locked: the path order is the order Célestin proposes. Shared by the
tools, the state message and the tests. The frontend keeps a display-only mirror in
`lib/tutor/path.ts`, tested against the same cases (`tests/fixtures/path_cases.json`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domain.curriculum import Curriculum, Section
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.progress import Progress

State = Literal["done", "active", "skipped", "available", "open"]


def section_states(curriculum: Curriculum, progress: Progress) -> dict[str, State]:
    """`available` is the section Célestin proposes, only while nothing is active; every
    section that is neither done, active, skipped nor that one is `open`."""
    states: dict[str, State] = {}
    proposed = next_section(curriculum, progress) if progress.active is None else None
    for section in curriculum.sections:
        if section.id in progress.done:
            states[section.id] = "done"
        elif section.id == progress.active:
            states[section.id] = "active"
        elif section.id in progress.skipped:
            states[section.id] = "skipped"
        elif proposed is not None and section.id == proposed.id:
            states[section.id] = "available"
        else:
            states[section.id] = "open"
    return states


def next_section(curriculum: Curriculum, progress: Progress) -> Section | None:
    """The first section that is neither done, skipped nor active, in chapter order."""
    for section in curriculum.sections:
        if (
            section.id not in progress.done
            and section.id not in progress.skipped
            and section.id != progress.active
        ):
            return section
    return None


def page_turn(curriculum: Curriculum, progress: Progress) -> Section | None:
    """The section the page-turn button proposes: None while a section is active (passing
    another section does not turn the page of the one being worked), else the next one of
    the path, None once every section is done or skipped. The one rule for the live
    `section.done` and `section.skipped` events and for what a stored `complete_section` or
    `skip_section` shows when a séance is read back (specs 018, 019)."""
    return None if progress.active is not None else next_section(curriculum, progress)


def finished(curriculum: Curriculum, progress: Progress) -> bool:
    """Every section done or skipped (019 D5)."""
    return all(s.id in progress.done or s.id in progress.skipped for s in curriculum.sections)


@dataclass(frozen=True)
class Words:
    """The refusals the model reads, for one course language (spec 011 §4.1)."""

    unknown: str  # {section_id} {ids}
    none_active: str
    only_active: str  # {label} {id}
    skip_done: str  # {label}


WORDS = by_language(
    fr=Words(
        unknown="La section « {section_id} » n'existe pas. Sections du chapitre : {ids}.",
        none_active="Aucune section n'est en cours. Commence-en une avec start_section.",
        only_active="Seule la section en cours peut être terminée : « {label} » (id : {id}).",
        skip_done="La section « {label} » est déjà faite : elle ne peut pas être passée.",
    ),
    en=Words(
        unknown="Section “{section_id}” does not exist. Sections of the chapter: {ids}.",
        none_active="No section is in progress. Start one with start_section.",
        only_active="Only the current section can be finished: “{label}” (id: {id}).",
        skip_done="Section “{label}” is already done: it cannot be skipped.",
    ),
    nl=Words(
        unknown="Sectie “{section_id}” bestaat niet. Secties van het hoofdstuk: {ids}.",
        none_active="Geen sectie is bezig. Begin er een met start_section.",
        only_active="Alleen de huidige sectie kan worden afgerond: “{label}” (id: {id}).",
        skip_done="Sectie “{label}” is al afgerond: ze kan niet overgeslagen worden.",
    ),
)


def _unknown(curriculum: Curriculum, section_id: str, language: CourseLanguage) -> str:
    ids = ", ".join(s.id for s in curriculum.sections)
    return WORDS[language].unknown.format(section_id=section_id, ids=ids)


def can_start(
    curriculum: Curriculum,
    section_id: str,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str | None:
    """The refusal in the course's language, or None: any section of the chapter may be
    started (019 D1), only an unknown id is refused."""
    if curriculum.get(section_id) is None:
        return _unknown(curriculum, section_id, language)
    return None


def can_skip(
    curriculum: Curriculum,
    progress: Progress,
    section_id: str,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str | None:
    """The refusal in the course's language, or None: a section already done cannot be
    passed (019 D3); an already skipped one may be skipped again, which changes nothing."""
    section = curriculum.get(section_id)
    if section is None:
        return _unknown(curriculum, section_id, language)
    if section_id in progress.done:
        return WORDS[language].skip_done.format(label=section.label)
    return None


def can_complete(
    curriculum: Curriculum,
    progress: Progress,
    section_id: str,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str | None:
    """The refusal in the course's language, or None when the section is the active one."""
    w = WORDS[language]
    if curriculum.get(section_id) is None:
        return _unknown(curriculum, section_id, language)
    if progress.active == section_id:
        return None
    if progress.active is None:
        return w.none_active
    active = curriculum.get(progress.active)
    assert active is not None
    return w.only_active.format(label=active.label, id=active.id)
