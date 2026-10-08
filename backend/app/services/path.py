"""The locked path (design 3.4). Pure: curriculum + progress in, states out.

Shared by the tools, the state message and the tests. The frontend keeps a
display-only mirror in `lib/tutor/path.ts`, tested against the same cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domain.curriculum import Curriculum, Section
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.progress import Progress

State = Literal["done", "active", "available", "locked"]


def section_states(curriculum: Curriculum, progress: Progress) -> dict[str, State]:
    states: dict[str, State] = {}
    available_taken = progress.active is not None
    for section in curriculum.sections:
        if section.id in progress.done:
            states[section.id] = "done"
        elif section.id == progress.active:
            states[section.id] = "active"
        elif not available_taken:
            states[section.id] = "available"
            available_taken = True
        else:
            states[section.id] = "locked"
    return states


def next_section(curriculum: Curriculum, progress: Progress) -> Section | None:
    """The first section that is neither done nor active, in chapter order."""
    for section in curriculum.sections:
        if section.id not in progress.done and section.id != progress.active:
            return section
    return None


def _startable(curriculum: Curriculum, progress: Progress) -> Section | None:
    if progress.active is not None:
        return curriculum.get(progress.active)
    return next_section(curriculum, progress)


@dataclass(frozen=True)
class Words:
    """The refusals the model reads, for one course language (spec 011 §4.1)."""

    unknown: str  # {section_id} {ids}
    locked: str  # {label} {hint}
    hint: str  # {label} {id}
    none_active: str
    only_active: str  # {label} {id}


WORDS = by_language(
    fr=Words(
        unknown="La section « {section_id} » n'existe pas. Sections du chapitre : {ids}.",
        locked="La section « {label} » n'est pas encore ouverte.{hint}",
        hint=" Tu peux commencer « {label} » (id : {id}).",
        none_active="Aucune section n'est en cours. Commence-en une avec start_section.",
        only_active="Seule la section en cours peut être terminée : « {label} » (id : {id}).",
    ),
    en=Words(
        unknown="Section “{section_id}” does not exist. Sections of the chapter: {ids}.",
        locked="Section “{label}” is not open yet.{hint}",
        hint=" You can start “{label}” (id: {id}).",
        none_active="No section is in progress. Start one with start_section.",
        only_active="Only the current section can be finished: “{label}” (id: {id}).",
    ),
    nl=Words(
        unknown="Sectie “{section_id}” bestaat niet. Secties van het hoofdstuk: {ids}.",
        locked="Sectie “{label}” is nog niet open.{hint}",
        hint=" Je kunt “{label}” beginnen (id: {id}).",
        none_active="Geen sectie is bezig. Begin er een met start_section.",
        only_active="Alleen de huidige sectie kan worden afgerond: “{label}” (id: {id}).",
    ),
)


def _unknown(curriculum: Curriculum, section_id: str, language: CourseLanguage) -> str:
    ids = ", ".join(s.id for s in curriculum.sections)
    return WORDS[language].unknown.format(section_id=section_id, ids=ids)


def can_start(
    curriculum: Curriculum,
    progress: Progress,
    section_id: str,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str | None:
    """The refusal in the course's language, or None when the section may be started."""
    w = WORDS[language]
    section = curriculum.get(section_id)
    if section is None:
        return _unknown(curriculum, section_id, language)
    if section_states(curriculum, progress)[section_id] != "locked":
        return None
    startable = _startable(curriculum, progress)
    hint = w.hint.format(label=startable.label, id=startable.id) if startable else ""
    return w.locked.format(label=section.label, hint=hint)


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
