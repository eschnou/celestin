"""Text the model reads about the path (design 3.5). Pure functions.

`overview` sits in the cached prefix, so it must be byte-stable per file.
`brief` goes through a tool result, and so does `reprise`, the note that ends it
when a section left unfinished is taken up again (spec 018 D5). `state_message`
is appended after the transcript on every turn.

Every sentence is looked up by the course's language (spec 011 §4.5): the French row is
the text this module always said, byte for byte; the English one is its counterpart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.curriculum import KIND_LABELS, Curriculum, Section
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.mode import DEFAULT_MODE, Mode
from app.domain.progress import Progress
from app.domain.revision import OUTCOMES, Outcome, Results, RevisionChapter, Tally
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
    completed: str
    skipped_head: str
    following_last: str
    finished_all: str
    following_next: str  # {label} {kind} {id}
    following_active: str  # {label} {kind} {id}
    now: str  # {moment}
    status: str  # {done} {total}
    status_skipped: str  # {done} {skipped} {total}
    skipped_list: str  # {labels}
    skipped_label: str  # {label}
    active: str  # {label} {kind}
    active_hint: str  # {id}
    finished: str
    finished_skipped_offer: str
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
        lead_parcours="Sections dans l'ordre que tu proposes.",
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
        completed="Section terminée.",
        skipped_head="Section passée.",
        following_last="Chapitre terminé.",
        finished_all="Chapitre terminé : toutes les sections sont faites ou passées.",
        following_next="Prochaine section : « {label} » ({kind}), id : {id}.",
        following_active="Section toujours en cours : « {label} » ({kind}), id : {id}.",
        now="Nous sommes {moment}.",
        status="État du parcours : {done} section(s) faite(s) sur {total}.",
        status_skipped="État du parcours : {done} section(s) faite(s) et {skipped} passée(s) sur {total}.",
        skipped_list="Sections passées : {labels}.",
        skipped_label="« {label} »",
        active="Section en cours : « {label} » ({kind}).",
        active_hint=(
            "Si tu n'as pas encore son plan dans cette conversation, appelle "
            'start_section("{id}").'
        ),
        finished="Chapitre terminé. Propose une révision d'une section au choix.",
        finished_skipped_offer="Propose de faire une section passée ou de revoir une section faite.",
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
        lead_parcours="Sections in the order you propose.",
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
        completed="Section finished.",
        skipped_head="Section skipped.",
        following_last="Chapter finished.",
        finished_all="Chapter finished: every section is done or skipped.",
        following_next="Next section: “{label}” ({kind}), id: {id}.",
        following_active="Section still in progress: “{label}” ({kind}), id: {id}.",
        now="It is {moment}.",
        status="Path status: {done} section(s) done out of {total}.",
        status_skipped="Path status: {done} section(s) done and {skipped} skipped out of {total}.",
        skipped_list="Skipped sections: {labels}.",
        skipped_label="“{label}”",
        active="Current section: “{label}” ({kind}).",
        active_hint=(
            "If you do not have its plan in this conversation yet, call "
            'start_section("{id}").'
        ),
        finished="Chapter finished. Offer a review of any section.",
        finished_skipped_offer="Offer to do a skipped section or to review a finished one.",
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
    nl=Words(
        overview_heading="## Traject van het hoofdstuk “{title}”",
        lead_parcours="Secties in de volgorde die jij voorstelt.",
        lead_discussion=(
            "Secties in volgorde. Dit is het traject van het hoofdstuk: het wordt gevolgd in de "
            "trajectmodus, niet hier. Je kunt je leerling zeggen waar een begrip behandeld wordt en "
            "voorstellen er naartoe te gaan; je kunt geen sectie openen of afronden."
        ),
        overview_line="{index}. `{id}` ({kind}) — {title}. {goal}",
        brief_head="Sectie “{label}” ({kind}), {index}/{total}.",
        review="Herhaling: deze sectie is al afgerond. Rond ze niet opnieuw af.",
        goal="Doel: {goal}",
        beats_head="Verloop:",
        beat="{index}. {beat}",
        exercises="Typische oefeningen: {exercises}.",
        exercises_separator="; ",
        to_do="Te doen: {count} oefening(en), één per keer.",
        done_when="Afgerond wanneer: {done_when}",
        completed="Sectie afgerond.",
        skipped_head="Sectie overgeslagen.",
        following_last="Hoofdstuk afgerond.",
        finished_all="Hoofdstuk afgerond: alle secties zijn afgerond of overgeslagen.",
        following_next="Volgende sectie: “{label}” ({kind}), id: {id}.",
        following_active="Sectie nog bezig: “{label}” ({kind}), id: {id}.",
        now="Het is {moment}.",
        status="Stand van het traject: {done} van de {total} sectie(s) afgerond.",
        status_skipped=(
            "Stand van het traject: {done} van de {total} sectie(s) afgerond en {skipped} overgeslagen."
        ),
        skipped_list="Overgeslagen secties: {labels}.",
        skipped_label="“{label}”",
        active="Huidige sectie: “{label}” ({kind}).",
        active_hint=(
            "Als je het plan nog niet in dit gesprek hebt, roep dan "
            'start_section("{id}") aan.'
        ),
        finished="Hoofdstuk afgerond. Stel een herhaling van een sectie naar keuze voor.",
        finished_skipped_offer="Stel voor om een overgeslagen sectie te doen of een afgeronde te herhalen.",
        none_active="Geen sectie bezig. Volgende: “{label}” ({kind}).",
        start_hint='Begin eraan met start_section("{id}").',
        discussion_active=(
            "Huidige sectie in het traject: “{label}” ({kind}), daar verder te zetten."
        ),
        discussion_finished="Hoofdstuk afgerond: het hele traject is gedaan.",
        discussion_none_active=(
            "Geen sectie bezig. De volgende zou “{label}” ({kind}) zijn, te doen in het traject."
        ),
        moment="{weekday} {day} {month}, {hour}:{minute:02d} ({part})",
        days=("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"),
        months=(
            "januari", "februari", "maart", "april", "mei", "juni",
            "juli", "augustus", "september", "oktober", "november", "december",
        ),
        parts=("voormiddag", "namiddag", "avond"),
    ),
)


@dataclass(frozen=True)
class RepriseWords:
    """The reprise note (spec 018 D5), for one language."""

    head: str
    older: str  # {count}
    line: str  # {kind} {title}
    line_untitled: str  # {kind}
    tail: str
    kinds: dict[str, str]  # card kind -> what the note calls it


REPRISE = by_language(
    fr=RepriseWords(
        head=(
            "Reprise : cette section a déjà été travaillée lors d'une séance précédente. "
            "Cartes déjà montrées, dans l'ordre :"
        ),
        older="(et {count} carte(s) plus ancienne(s))",
        line="- {kind} : {title}",
        line_untitled="- {kind}",
        tail=(
            "Dis en une phrase à ton élève où vous en étiez, puis continue après la dernière carte, "
            "sans reprendre la section depuis le début."
        ),
        kinds={
            "title": "titre",
            "explanation": "explication",
            "worked_example": "exemple guidé",
            "exercise": "exercice",
            "check_question": "question de compréhension",
            "recap": "bilan",
        },
    ),
    en=RepriseWords(
        head=(
            "Resuming: this section was already worked on in an earlier session. "
            "Cards already shown, in order:"
        ),
        older="(and {count} older card(s))",
        line="- {kind}: {title}",
        line_untitled="- {kind}",
        tail=(
            "Tell your student in one sentence where you had got to, then continue after the last card, "
            "without starting the section over."
        ),
        kinds={
            "title": "title",
            "explanation": "explanation",
            "worked_example": "worked example",
            "exercise": "exercise",
            "check_question": "check question",
            "recap": "recap",
        },
    ),
    nl=RepriseWords(
        head=(
            "Hervatting: aan deze sectie werd al gewerkt in een vorige sessie. "
            "Kaarten die al getoond werden, in volgorde:"
        ),
        older="(en {count} oudere kaart(en))",
        line="- {kind}: {title}",
        line_untitled="- {kind}",
        tail=(
            "Zeg je leerling in één zin waar jullie gebleven waren en ga dan verder na de laatste kaart, "
            "zonder de sectie van voren af aan te herbeginnen."
        ),
        kinds={
            "title": "titel",
            "explanation": "uitleg",
            "worked_example": "uitgewerkt voorbeeld",
            "exercise": "oefening",
            "check_question": "begripsvraag",
            "recap": "samenvatting",
        },
    ),
)

# The note lists the most recent cards only: enough to say where they were, never the whole history.
REPRISE_MAX_CARDS = 20


def _card_title(card: dict[str, Any]) -> str | None:
    """What a card is called in the note: its title, or the question of a check question; a recap has neither."""
    value = card.get("question") if card.get("kind") == "check_question" else card.get("title")
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def reprise(cards: list[dict[str, Any]], language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str | None:
    """The note that ends a section's brief when it is taken up again after a séance that
    left it unfinished (spec 018 D5): the cards already shown, in order, and what to do
    with them. None without cards. Pure, so a replayed call says it byte for byte again."""
    if not cards:
        return None
    w = REPRISE[language]
    lines = [w.head]
    shown = cards[-REPRISE_MAX_CARDS:]
    if len(cards) > len(shown):
        lines.append(w.older.format(count=len(cards) - len(shown)))
    for card in shown:
        kind = w.kinds.get(str(card.get("kind")), str(card.get("kind")))
        title = _card_title(card)
        lines.append(w.line.format(kind=kind, title=title) if title else w.line_untitled.format(kind=kind))
    lines.append(w.tail)
    return "\n".join(lines)


def overview(
    curriculum: Curriculum, mode: Mode = DEFAULT_MODE, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> str:
    w = WORDS[language]
    lines = [w.overview_heading.format(title=curriculum.title), ""]
    lines.append(w.lead_parcours if mode == "parcours" else w.lead_discussion)
    lines.append("")
    lines += _section_lines(curriculum, language)
    return "\n".join(lines)


def _section_lines(curriculum: Curriculum, language: CourseLanguage) -> list[str]:
    """One line per section of the path: its number, id, kind, title and goal (an overview's body)."""
    w, kinds = WORDS[language], KIND_LABELS[language]
    return [
        w.overview_line.format(index=index, id=s.id, kind=kinds[s.kind], title=s.title, goal=s.goal)
        for index, s in enumerate(curriculum.sections, start=1)
    ]


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
    active: Section | None, following: Section | None, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> str:
    """What a `complete_section` answers: the section is finished, and what comes next
    (`following`, None: the chapter is finished). Built from sections, not from a progress,
    so a stored call replays from what it recorded (spec 019). `active` is only ever set
    for a call stored before spec 019, replayed from the progress now."""
    w = WORDS[language]
    return _following(w.completed, active, following, w.following_last, language)


def skipped(
    active: Section | None, following: Section | None, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> str:
    """What a `skip_section` answers (spec 019): the section is passed, and what comes next,
    said as a completion says it: the section still being worked (`active`), else the next
    one of the path (`following`), else the end of the chapter."""
    w = WORDS[language]
    return _following(w.skipped_head, active, following, w.finished_all, language)


def _following(
    head: str, active: Section | None, following: Section | None, last: str, language: CourseLanguage
) -> str:
    w, kinds = WORDS[language], KIND_LABELS[language]
    if active is not None:
        return f"{head} {w.following_active.format(label=active.label, kind=kinds[active.kind], id=active.id)}"
    if following is not None:
        return f"{head} {w.following_next.format(label=following.label, kind=kinds[following.kind], id=following.id)}"
    return f"{head} {last}"


def _status(curriculum: Curriculum, progress: Progress, language: CourseLanguage) -> list[str]:
    """Done and skipped counted apart, and the skipped sections named (spec 019)."""
    w, total = WORDS[language], len(curriculum.sections)
    if not progress.skipped:
        return [w.status.format(done=len(progress.done), total=total)]
    return [
        w.status_skipped.format(done=len(progress.done), skipped=len(progress.skipped), total=total),
        _skipped_list(curriculum, progress, language),
    ]


# Between two skipped sections' labels, in every course language.
_SEPARATOR = ", "


def _skipped_list(curriculum: Curriculum, progress: Progress, language: CourseLanguage) -> str:
    """« Sections passées : « 2. … », « 4. … ». », in path order."""
    skipped = [s for s in curriculum.sections if s.id in progress.skipped]
    return WORDS[language].skipped_list.format(labels=_labels(skipped, language))


def _labels(sections: list[Section], language: CourseLanguage) -> str:
    """Sections' labels, quoted in the course language and joined: « « 2. … », « 4. … » »."""
    w = WORDS[language]
    return _SEPARATOR.join(w.skipped_label.format(label=s.label) for s in sections)


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
    lines.extend(_status(curriculum, progress, language))
    if mode == "discussion":
        return "\n".join(lines + _discussion_state(curriculum, progress, language))
    if progress.active is not None:
        active = curriculum.get(progress.active)
        assert active is not None
        lines.append(w.active.format(label=active.label, kind=kinds[active.kind]))
        lines.append(w.active_hint.format(id=active.id))
        return "\n".join(lines)
    if path.finished(curriculum, progress):
        lines.append(f"{w.finished_all} {w.finished_skipped_offer}" if progress.skipped else w.finished)
        return "\n".join(lines)
    following = path.next_section(curriculum, progress)
    assert following is not None
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
    if path.finished(curriculum, progress):
        return [w.finished_all if progress.skipped else w.discussion_finished]
    following = path.next_section(curriculum, progress)
    assert following is not None
    return [w.discussion_none_active.format(label=following.label, kind=kinds[following.kind])]


# --- révision (spec 020) -----------------------------------------------------------------------------------------
# A révision reads several chapters: their packs under one header each (`revision_packs`, at `<!-- COURSE_PACK -->`),
# one read-only overview per chapter (`revision_overview`, at `<!-- CURRICULUM -->`), both in the cached prefix and so
# byte-stable for a selection; and a trailing state message (`revision_state`) that may change every turn. Nothing
# here names a tool: the révision's only tool is described by its declaration and by the mode file.


@dataclass(frozen=True)
class RevisionWords:
    """The phrases of a révision's rendering for one language."""

    pack_head: str  # {number} {title}
    overview_heading: str
    overview_lead: str
    overview_chapter: str  # {number} {title}
    chapter_status: str  # {number} {title} {done} {skipped} {todo} {total}
    done_list: str  # {labels}
    skipped_list: str  # {labels}
    todo_list: str  # {labels}
    earlier: str  # {items}
    earlier_item: str  # {label} {outcome} {date}
    earlier_separator: str
    none_noted: str
    noted: str  # {count} {solid} {shaky} {todo}
    tally: str  # {count} {solid} {shaky} {todo}
    outcomes: dict[Outcome, str]  # outcome -> its word


# A self-assessment's date in the state message, in every course language: « 15 novembre ».
_DATE = "{day} {month}"


REVISION = by_language(
    fr=RevisionWords(
        pack_head="# Chapitre {number} — {title}",
        overview_heading="## Les chapitres de cette révision",
        overview_lead=(
            "Les sections de chaque chapitre, dans l'ordre. Ce sont les parcours des chapitres : ils se suivent "
            "dans le mode parcours, pas ici, et tu ne peux ni ouvrir ni terminer une section. Un chapitre se "
            "désigne par son numéro, une section par son identifiant."
        ),
        overview_chapter="### Chapitre {number} — « {title} »",
        chapter_status=(
            "Chapitre {number} — « {title} » : {done} section(s) faite(s), {skipped} passée(s) et {todo} "
            "jamais faite(s) sur {total}."
        ),
        done_list="- Faites : {labels}.",
        skipped_list="- Passées, jamais travaillées avec toi : {labels}.",
        todo_list="- Jamais faites : {labels}.",
        earlier="- Derniers bilans : {items}.",
        earlier_item="« {label} » : {outcome} ({date})",
        earlier_separator=" ; ",
        none_noted="Cette révision : rien de noté pour l'instant.",
        noted=(
            "Cette révision : {count} section(s) notée(s) — {solid} acquis, {shaky} fragile(s), {todo} à revoir."
        ),
        tally="Bilan noté. Cette révision : {solid} acquis, {shaky} fragile(s), {todo} à revoir ({count} section(s) notée(s)).",
        outcomes={"solid": "acquis", "shaky": "fragile", "todo": "à revoir"},
    ),
    en=RevisionWords(
        pack_head="# Chapter {number} — {title}",
        overview_heading="## The chapters of this revision",
        overview_lead=(
            "The sections of each chapter, in order. These are the chapters' paths: they are followed in path "
            "mode, not here, and you can neither open nor finish a section. A chapter is named by its number, a "
            "section by its id."
        ),
        overview_chapter="### Chapter {number} — “{title}”",
        chapter_status=(
            "Chapter {number} — “{title}”: {done} section(s) done, {skipped} skipped and {todo} never done out "
            "of {total}."
        ),
        done_list="- Done: {labels}.",
        skipped_list="- Skipped, never worked on with you: {labels}.",
        todo_list="- Never done: {labels}.",
        earlier="- Latest self-assessments: {items}.",
        earlier_item="“{label}”: {outcome} ({date})",
        earlier_separator="; ",
        none_noted="This revision: nothing noted yet.",
        noted="This revision: {count} section(s) noted — {solid} solid, {shaky} shaky, {todo} to review.",
        tally="Self-assessment noted. This revision: {solid} solid, {shaky} shaky, {todo} to review ({count} section(s) noted).",
        outcomes={"solid": "solid", "shaky": "shaky", "todo": "to review"},
    ),
    nl=RevisionWords(
        pack_head="# Hoofdstuk {number} — {title}",
        overview_heading="## De hoofdstukken van deze herhaling",
        overview_lead=(
            "De secties van elk hoofdstuk, in volgorde. Dit zijn de trajecten van de hoofdstukken: ze worden "
            "gevolgd in de trajectmodus, niet hier, en je kunt geen sectie openen of afronden. Een hoofdstuk "
            "duid je aan met zijn nummer, een sectie met haar id."
        ),
        overview_chapter="### Hoofdstuk {number} — “{title}”",
        chapter_status=(
            "Hoofdstuk {number} — “{title}”: {done} sectie(s) afgerond, {skipped} overgeslagen en {todo} nooit "
            "gedaan, van de {total}."
        ),
        done_list="- Afgerond: {labels}.",
        skipped_list="- Overgeslagen, nooit met jou behandeld: {labels}.",
        todo_list="- Nooit gedaan: {labels}.",
        earlier="- Laatste zelfbeoordelingen: {items}.",
        earlier_item="“{label}”: {outcome} ({date})",
        earlier_separator="; ",
        none_noted="Deze herhaling: nog niets genoteerd.",
        noted=(
            "Deze herhaling: {count} sectie(s) genoteerd — {solid} gekend, {shaky} wankel, {todo} te herhalen."
        ),
        tally="Zelfbeoordeling genoteerd. Deze herhaling: {solid} gekend, {shaky} wankel, {todo} te herhalen ({count} sectie(s) genoteerd).",
        outcomes={"solid": "gekend", "shaky": "wankel", "todo": "te herhalen"},
    ),
)


def revision_packs(chapters: tuple[RevisionChapter, ...], language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    """The chosen chapters' packs, in course order, each under a one-line header with its number and title, so
    Célestin can say where a notion lives. Each pack is the stored one with its surrounding blank lines trimmed:
    the rendering adds only the headers and one blank line between the parts."""
    w = REVISION[language]
    return "\n\n".join(
        f"{w.pack_head.format(number=c.number, title=c.title)}\n\n{c.pack.strip()}" for c in chapters
    )


def revision_overview(
    chapters: tuple[RevisionChapter, ...], language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> str:
    """One overview per chapter (its number, title and sections with id, kind, title and goal), read-only: no tool
    is named. In the cached prefix, so it depends on the selection only."""
    w = REVISION[language]
    lines = [w.overview_heading, "", w.overview_lead]
    for chapter in chapters:
        lines += ["", w.overview_chapter.format(number=chapter.number, title=chapter.title), ""]
        lines += _section_lines(chapter.curriculum, language)
    return "\n".join(lines)


def _counts(tally: Tally) -> dict[str, int]:
    counts = {outcome: int(tally.get(outcome, 0)) for outcome in OUTCOMES}
    return {**counts, "count": sum(counts.values())}


def revision_tally(tally: Tally, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    """What `record_result` answers: this révision's tally, from the counts alone, so a stored call replays it
    byte for byte from what it recorded."""
    return REVISION[language].tally.format(**_counts(tally))


def _date(at: datetime, now: datetime | None, language: CourseLanguage) -> str:
    if now is not None and now.tzinfo is not None:
        at = at.astimezone(now.tzinfo)
    return _DATE.format(day=at.day, month=WORDS[language].months[at.month - 1])


def revision_state(
    chapters: tuple[RevisionChapter, ...],
    earlier: Results,
    tally: Tally,
    now: datetime | None = None,
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str:
    """Appended after the transcript on every révision turn, so it may change freely: the time; per chapter, the
    sections done, skipped (never worked on with Célestin) and never done; the latest self-assessment per section
    with its date; this révision's tally. An active section that is not done counts as never done."""
    w, words = REVISION[language], WORDS[language]
    lines = []
    if now is not None:
        lines.append(words.now.format(moment=moment(now, language)))
    for chapter in chapters:
        sections = chapter.curriculum.sections
        states = {s.id: chapter.progress.state_of(s.id) for s in sections}
        done, skipped, todo = ([s for s in sections if states[s.id] == state] for state in ("done", "skipped", "todo"))
        lines.append(
            w.chapter_status.format(
                number=chapter.number,
                title=chapter.title,
                done=len(done),
                skipped=len(skipped),
                todo=len(todo),
                total=len(sections),
            )
        )
        for template, group in ((w.done_list, done), (w.skipped_list, skipped), (w.todo_list, todo)):
            if group:
                lines.append(template.format(labels=_labels(group, language)))
        items = [
            w.earlier_item.format(
                label=s.label,
                outcome=w.outcomes[noted.outcome],
                date=_date(noted.at, now, language),
            )
            for s in sections
            if (noted := earlier.get((chapter.id, s.id))) is not None
        ]
        if items:
            lines.append(w.earlier.format(items=w.earlier_separator.join(items)))
    counts = _counts(tally)
    lines.append(w.noted.format(**counts) if counts["count"] else w.none_noted)
    return "\n".join(lines)
