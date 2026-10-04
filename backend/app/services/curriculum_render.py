"""Text the model reads about the path (design 3.5). Pure functions.

`overview` sits in the cached prefix, so it must be byte-stable per file.
`brief` goes through a tool result. `state_message` is appended after the
transcript on every turn.

Every sentence is looked up by the course's language (spec 011 §4.5): the French row is
the text this module always said, byte for byte; the English one is its counterpart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.curriculum import KIND_LABELS, Curriculum, Section
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.mode import DEFAULT_MODE, Mode
from app.domain.progress import Progress
from app.services import path


@dataclass(frozen=True)
class Words:
    """The phrases of this module for one language. `{fields}` are `str.format` fields."""

    overview_heading: str  # {title}
    lead_parcours: str
    lead_discussion: str
    overview_line: str  # {index} {id} {kind} {title} {goal}
    brief_head: str  # {label} {kind} {index} {total}
    review: str
    goal: str  # {goal}
    beats_head: str
    beat: str  # {index} {beat}
    exercises: str  # {exercises}
    exercises_separator: str
    to_do: str  # {count}
    done_when: str  # {done_when}
    completion_last: str
    completion_next: str  # {label} {kind} {id}
    now: str  # {moment}
    status: str  # {done} {total}
    active: str  # {label} {kind}
    active_hint: str  # {id}
    finished: str
    none_active: str  # {label} {kind}
    start_hint: str  # {id}
    discussion_active: str  # {label} {kind}
    discussion_finished: str
    discussion_none_active: str  # {label} {kind}
    moment: str  # {weekday} {day} {month} {hour} {minute} {part}
    days: tuple[str, ...]
    months: tuple[str, ...]
    parts: tuple[str, str, str]  # morning, afternoon, evening


WORDS = by_language(
    fr=Words(
        overview_heading="## Parcours du chapitre « {title} »",
        lead_parcours=(
            "Sections dans l'ordre, verrouillées : une section ne s'ouvre que lorsque la "
            "précédente est terminée. `start_section(id)` te donne le plan d'une section, "
            "`complete_section(id, résumé)` la termine."
        ),
        lead_discussion=(
            "Sections dans l'ordre. C'est le parcours du chapitre : il se suit dans le "
            "mode parcours, pas ici. Tu peux dire à ton élève où se travaille une notion "
            "et lui proposer d'y aller ; tu ne peux ni ouvrir ni terminer une section."
        ),
        overview_line="{index}. `{id}` ({kind}) — {title}. {goal}",
        brief_head="Section « {label} » ({kind}), {index}/{total}.",
        review="Révision : cette section est déjà faite. Ne la termine pas à nouveau.",
        goal="Objectif : {goal}",
        beats_head="Déroulé :",
        beat="{index}. {beat}",
        exercises="Exercices types : {exercises}.",
        exercises_separator=" ; ",
        to_do="À faire : {count} exercice(s), un à la fois.",
        done_when="Terminée quand : {done_when}",
        completion_last="Section terminée. Chapitre terminé.",
        completion_next="Section terminée. Prochaine section : « {label} » ({kind}), id : {id}.",
        now="Nous sommes {moment}.",
        status="État du parcours : {done} section(s) faite(s) sur {total}.",
        active="Section en cours : « {label} » ({kind}).",
        active_hint=(
            "Si tu n'as pas encore son plan dans cette conversation, appelle "
            'start_section("{id}").'
        ),
        finished="Chapitre terminé. Propose une révision d'une section au choix.",
        none_active="Aucune section en cours. Prochaine : « {label} » ({kind}).",
        start_hint='Commence-la avec start_section("{id}").',
        discussion_active=(
            "Section en cours dans le parcours : « {label} » ({kind}), à reprendre là-bas."
        ),
        discussion_finished="Chapitre terminé : tout le parcours est fait.",
        discussion_none_active=(
            "Aucune section en cours. La prochaine serait « {label} » ({kind}), à faire dans le parcours."
        ),
        moment="{weekday} {day} {month}, {hour} h {minute:02d} ({part})",
        days=("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
        months=(
            "janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre",
        ),
        parts=("le matin", "l'après-midi", "le soir"),
    ),
    en=Words(
        overview_heading="## Chapter path “{title}”",
        lead_parcours=(
            "Sections in order, locked: a section opens only when the previous one is "
            "finished. `start_section(id)` gives you a section's plan, "
            "`complete_section(id, summary)` finishes it."
        ),
        lead_discussion=(
            "Sections in order. This is the chapter's path: it is followed in path mode, "
            "not here. You can tell your student where a notion is worked and offer to go "
            "there; you can neither open nor finish a section."
        ),
        overview_line="{index}. `{id}` ({kind}) — {title}. {goal}",
        brief_head="Section “{label}” ({kind}), {index}/{total}.",
        review="Review: this section is already done. Do not finish it again.",
        goal="Goal: {goal}",
        beats_head="Outline:",
        beat="{index}. {beat}",
        exercises="Typical exercises: {exercises}.",
        exercises_separator="; ",
        to_do="To do: {count} exercise(s), one at a time.",
        done_when="Finished when: {done_when}",
        completion_last="Section finished. Chapter finished.",
        completion_next="Section finished. Next section: “{label}” ({kind}), id: {id}.",
        now="It is {moment}.",
        status="Path status: {done} section(s) done out of {total}.",
        active="Current section: “{label}” ({kind}).",
        active_hint=(
            "If you do not have its plan in this conversation yet, call "
            'start_section("{id}").'
        ),
        finished="Chapter finished. Offer a review of any section.",
        none_active="No section in progress. Next: “{label}” ({kind}).",
        start_hint='Start it with start_section("{id}").',
        discussion_active=(
            "Current section in the path: “{label}” ({kind}), to be resumed there."
        ),
        discussion_finished="Chapter finished: the whole path is done.",
        discussion_none_active=(
            "No section in progress. The next would be “{label}” ({kind}), to do in the path."
        ),
        moment="{weekday} {day} {month}, {hour}:{minute:02d} ({part})",
        days=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        months=(
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ),
        parts=("morning", "afternoon", "evening"),
    ),
)


def overview(
    curriculum: Curriculum, mode: Mode = DEFAULT_MODE, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> str:
    w, kinds = WORDS[language], KIND_LABELS[language]
    lines = [w.overview_heading.format(title=curriculum.title), ""]
    lines.append(w.lead_parcours if mode == "parcours" else w.lead_discussion)
    lines.append("")
    for index, section in enumerate(curriculum.sections, start=1):
        lines.append(
            w.overview_line.format(
                index=index, id=section.id, kind=kinds[section.kind], title=section.title, goal=section.goal
            )
        )
    return "\n".join(lines)


def brief(
    curriculum: Curriculum,
    section: Section,
    review: bool,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str:
    w = WORDS[language]
    lines = [
        w.brief_head.format(
            label=section.label,
            kind=KIND_LABELS[language][section.kind],
            index=section.index,
            total=len(curriculum.sections),
        )
    ]
    if review:
        lines.append(w.review)
    lines.append(w.goal.format(goal=section.goal))
    if section.kind == "teach":
        lines.append(w.beats_head)
        for i, beat in enumerate(section.beats, start=1):
            lines.append(w.beat.format(index=i, beat=beat))
    else:
        lines.append(w.exercises.format(exercises=w.exercises_separator.join(section.exercises)))
        lines.append(w.to_do.format(count=section.count))
    lines.append(w.done_when.format(done_when=section.done_when))
    return "\n".join(lines)


def completion(
    curriculum: Curriculum, progress: Progress, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> str:
    w = WORDS[language]
    following = path.next_section(curriculum, progress)
    if following is None:
        return w.completion_last
    return w.completion_next.format(
        label=following.label, kind=KIND_LABELS[language][following.kind], id=following.id
    )


def moment(now: datetime, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    """« jeudi 11 septembre, 10 h 05 (le matin) » — the greeting depends on it."""
    w = WORDS[language]
    hour = now.hour
    part = w.parts[0] if hour < 12 else w.parts[1] if hour < 18 else w.parts[2]
    return w.moment.format(
        weekday=w.days[now.weekday()],
        day=now.day,
        month=w.months[now.month - 1],
        hour=hour,
        minute=now.minute,
        part=part,
    )


def state_message(
    curriculum: Curriculum,
    progress: Progress,
    now: datetime | None = None,
    mode: Mode = DEFAULT_MODE,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str:
    """Appended after the transcript on every turn, so it may change freely."""
    w, kinds = WORDS[language], KIND_LABELS[language]
    lines = []
    if now is not None:
        lines.append(w.now.format(moment=moment(now, language)))
    lines.append(w.status.format(done=len(progress.done), total=len(curriculum.sections)))
    if mode == "discussion":
        return "\n".join(lines + _discussion_state(curriculum, progress, language))
    if progress.active is not None:
        active = curriculum.get(progress.active)
        assert active is not None
        lines.append(w.active.format(label=active.label, kind=kinds[active.kind]))
        lines.append(w.active_hint.format(id=active.id))
        return "\n".join(lines)
    following = path.next_section(curriculum, progress)
    if following is None:
        lines.append(w.finished)
        return "\n".join(lines)
    lines.append(w.none_active.format(label=following.label, kind=kinds[following.kind]))
    lines.append(w.start_hint.format(id=following.id))
    return "\n".join(lines)


def _discussion_state(curriculum: Curriculum, progress: Progress, language: CourseLanguage) -> list[str]:
    """Where she stands, read-only: a discussion never opens or closes a section
    (007 §3.4). No tool is named, because none of them is declared here."""
    w, kinds = WORDS[language], KIND_LABELS[language]
    if progress.active is not None:
        active = curriculum.get(progress.active)
        assert active is not None
        return [w.discussion_active.format(label=active.label, kind=kinds[active.kind])]
    following = path.next_section(curriculum, progress)
    if following is None:
        return [w.discussion_finished]
    return [w.discussion_none_active.format(label=following.label, kind=kinds[following.kind])]
