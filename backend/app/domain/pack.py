"""The course pack as a structured Markdown document (005 design 3.5).

A subject's pack template fixes the numbered level-2 headings; `index_pack` checks a
pack against it and extracts the identifiers the curriculum may reference: `§N` and
`§N.M` for sections, `N.M.K` for exercises. Pure, no I/O, so the editors, the
authoring agent and the seed all validate the same way.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.domain.errors import PromptInvalid
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.subject import SUBJECT_IDS, Subject

MAX_ISSUES = 20
TITLE_MAX = 200

_H1 = re.compile(r"^#\s+(.+?)\s*$")
_H2 = re.compile(r"^##\s+(.*?)\s*$")
_H2_NUMBERED = re.compile(r"^(\d+)\.\s+(.+)$")
_H3 = re.compile(r"^###\s+(.*?)\s*$")
_H3_NUMBERED = re.compile(r"^(\d+)\.(\d+)\b\.?\s*(.*)$")
_H4 = re.compile(r"^####\s+(.*?)\s*$")
_H4_NUMBERED = re.compile(r"^(\d+)\.(\d+)\.(\d+)\b\.?\s*(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_NUMBERED_ITEM = re.compile(r"^\d+\.\s")


@dataclass(frozen=True)
class ContentIssue:
    """One reason a pack or a curriculum is refused.

    `message` is the French sentence the authoring model reads to repair its own output
    (`agent._repair_message`) and what an issue without a code shows the student. `code`
    and `params` let the student's editor say the same thing in the interface language:
    `messages.render_issue` looks up `issue.<code>` (spec 010 §4.9). `where` is structural
    and unchanged: the curriculum editor parses its `section « id »` form."""

    where: str
    message: str
    code: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PackTemplate:
    subject: Subject
    headings: tuple[tuple[int, str], ...]
    exercises_section: int
    text: str
    # The course language the template is written in: it comes from the file's name, not from
    # the front matter, so the French templates keep their bytes (spec 011 §4.8).
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE


@dataclass(frozen=True)
class PackIndex:
    title: str
    sections: frozenset[str]
    exercises: frozenset[str]
    # Numbered items under the template's last section, « Points à vérifier ».
    to_verify: int = 0


# « Chapitre 3 : les suites », « Chap. II - … », « 4) … »: the student's material numbers
# its own chapters; ours are numbered by their position in the course (006).
_KEYWORD = r"(?:chapitre|chap\.?|ch\.?|leçon|lecon|unité|unite|module|séquence|sequence|partie|thème|theme)"
# The same words for an English course (spec 011 R4.5): « Chapter 3: … », « Lesson 2 – … », « Unit 4) … ».
# A keyword is followed by its number after a space or its own dot, never glued to a word
# (« Chi-squared » is not « Ch. i »).
_KEYWORD_EN = r"(?:(?:chapter|chap\.?|ch\.|lesson|unit|module|section|part|topic|session)(?:\s+|(?<=\.)))"
# The same words for a Dutch course (spec 017 R4.4): « Hoofdstuk 3: … », « Les 2 – … », « Thema 4) … ».
_KEYWORD_NL = r"(?:(?:hoofdstuk|hfdst\.?|hfst\.?|les|eenheid|module|thema|deel|sectie|paragraaf|onderwerp|sessie|week)(?:\s+|(?<=\.)))"
_NUMBER = r"(?:n[°o]\s*)?[0-9IVXivx]+"
_SEPARATOR = r"\s*[):.\-–—]+\s*|\s+"


def _numbering(keyword: str) -> re.Pattern[str]:
    # « Chapitre 3 : … », « Chap. II - … » (a keyword needs no separator), or a bare
    # « 4) … » (a number alone must be followed by one, so « 1000 façons … » is kept).
    return re.compile(
        rf"^(?:{keyword}\s*{_NUMBER}(?:{_SEPARATOR})|{_NUMBER}\s*[):.\-–—]+\s*)", re.IGNORECASE
    )


_NUMBERING = _numbering(_KEYWORD)
# English: after a keyword any number; on its own a number (« 4) … ») or a Roman numeral with a
# closing mark (« IV. … »), never a letter before a hyphen (« X-ray », « V-shaped »).
def _numbering_roman(keyword: str, number: str = _NUMBER) -> re.Pattern[str]:
    return re.compile(
        rf"^(?:{keyword}{number}(?:{_SEPARATOR})|(?:\d+\s*[):.\-–—]+|[IVXivx]+[):.])\s*)", re.IGNORECASE
    )


_NUMBERING_EN = _numbering_roman(_KEYWORD_EN)
# Dutch: as English, with the Dutch keywords (a bare « IV. » or « 4) » is a number alone).
# A Dutch heading also numbers with « nr. » (« Hoofdstuk nr. 3 »).
_NUMBERING_NL = _numbering_roman(_KEYWORD_NL, r"(?:(?:nr|no)\.?\s*|n°\s*)?[0-9IVXivx]+")
_NUMBERING_BY_LANGUAGE = by_language(fr=_NUMBERING, en=_NUMBERING_EN, nl=_NUMBERING_NL)


def chapter_title(heading: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    """The chapter's own title, without the numbering the material gives it: the
    course numbers its chapters by position, so « Chapitre 1 : les suites » in two
    different courses would otherwise read the same (006)."""
    stripped = _NUMBERING_BY_LANGUAGE[language].sub("", heading.strip(), count=1).strip(" :-–—")
    if not stripped:
        return heading.strip()  # a heading that is only a number keeps it
    return stripped[0].upper() + stripped[1:]


def _norm(title: str) -> str:
    return " ".join(title.split()).casefold()


def parse_template(
    text: str, path: Path | str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> PackTemplate:
    """Front matter (`subject`, `exercises_section`) then the skeleton. The numbered
    level-2 headings of the skeleton are the required ones."""
    if not text.startswith("---\n"):
        raise PromptInvalid(path, "le modèle doit commencer par un en-tête YAML (---)")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise PromptInvalid(path, "en-tête YAML non fermé")
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise PromptInvalid(path, f"en-tête YAML illisible : {exc}") from exc
    subject = meta.get("subject")
    if subject not in SUBJECT_IDS:
        raise PromptInvalid(path, f"matière inconnue : {subject!r}")
    body = text[end + len("\n---\n") :]
    headings: list[tuple[int, str]] = []
    for line in body.splitlines():
        match = _H2.match(line)
        numbered = _H2_NUMBERED.match(match.group(1)) if match else None
        if numbered:
            headings.append((int(numbered.group(1)), numbered.group(2).strip()))
    if not headings:
        raise PromptInvalid(path, "aucun titre « ## N. … » dans le modèle")
    exercises = meta.get("exercises_section")
    if exercises not in {number for number, _ in headings}:
        raise PromptInvalid(path, f"exercises_section {exercises!r} ne désigne aucun titre du modèle")
    return PackTemplate(
        subject=subject,
        headings=tuple(headings),
        exercises_section=exercises,
        text=body,
        language=language,
    )




_LANGUAGE_NAMES_FR = by_language(fr="français", en="anglais", nl="néerlandais")


def _wrong_language(expected: CourseLanguage, found: CourseLanguage) -> ContentIssue:
    """The headings are those of the other language's template: the document was written for
    a course in `found`, not in `expected` (spec 011 R4.4). The params hold the codes; the
    catalog names the languages in whichever language the reader reads (`*_language` params)."""
    # The French `message` is what the French reason has always been: a literal, so this module
    # does not read the interface catalog (the catalog's own entry is the student's and the
    # English model's reading, `issue_text`).
    message = (
        f"le document suit le modèle en {_LANGUAGE_NAMES_FR[found]}, "
        f"mais ce cours est en {_LANGUAGE_NAMES_FR[expected]}"
    )
    return ContentIssue(
        "document",
        message,
        "pack.wrong_language",
        {"found_language": found, "expected_language": expected},
    )


def index_pack(
    markdown: str,
    template: PackTemplate,
    max_chars: int = 60_000,
    alternatives: Sequence[PackTemplate] = (),
) -> tuple[PackIndex | None, list[ContentIssue]]:
    """The pack's identifiers, or the reasons it does not follow the template. The
    index is returned only when there is no issue. `alternatives` are the subject's
    templates in the other languages: a pack whose headings are theirs is reported as
    written for the wrong language, before anything else."""
    issues: list[ContentIssue] = []

    def issue(where: str, message: str, code: str, **params: Any) -> None:
        issues.append(ContentIssue(where, message, code, params))

    if len(markdown) > max_chars:
        issue(
            "document",
            f"le document dépasse {max_chars} caractères ({len(markdown)})",
            "pack.too_long",
            max_chars=max_chars,
            length=len(markdown),
        )

    lines = markdown.splitlines()
    first = next((line for line in lines if line.strip()), "")
    title_match = _H1.match(first) if not first.startswith("##") else None
    title = chapter_title(title_match.group(1), template.language) if title_match else ""
    if not title_match:
        issue("titre", "le document doit commencer par un titre « # Titre du chapitre »", "pack.title_missing")
    elif len(title) > TITLE_MAX:
        issue("titre", f"le titre dépasse {TITLE_MAX} caractères", "pack.title_too_long", max=TITLE_MAX)

    h2: list[tuple[int | None, str]] = []
    sections: set[str] = set()
    exercises: set[str] = set()
    current_h2: int | None = None
    current_h3: tuple[int, int] | None = None
    in_fence = False
    h1_count = 0
    to_verify = 0
    last_section = template.headings[-1][0]

    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if (m := _H4.match(line)) is not None:
            numbered = _H4_NUMBERED.match(m.group(1))
            if numbered is None:
                continue
            n, s, k = (int(numbered.group(i)) for i in (1, 2, 3))
            ident = f"{n}.{s}.{k}"
            if current_h2 != template.exercises_section:
                issue(
                    f"exercice {ident}",
                    f"les exercices numérotés vont uniquement sous « ## {template.exercises_section}. »",
                    "pack.exercise_section",
                    section=template.exercises_section,
                )
            elif current_h3 != (n, s):
                issue(f"exercice {ident}", f"doit se trouver sous « ### {n}.{s} »", "pack.exercise_parent", n=n, s=s)
            elif ident in exercises:
                issue(f"exercice {ident}", "identifiant d'exercice en double", "pack.exercise_duplicate")
            else:
                exercises.add(ident)
            continue
        if (m := _H3.match(line)) is not None:
            numbered = _H3_NUMBERED.match(m.group(1))
            if numbered is None:
                current_h3 = None
                continue
            n, s = int(numbered.group(1)), int(numbered.group(2))
            ident = f"§{n}.{s}"
            if current_h2 != n:
                issue(f"§ {n}.{s}", f"doit se trouver sous « ## {n}. »", "pack.subsection_parent", n=n)
                current_h3 = None
            elif ident in sections:
                issue(f"§ {n}.{s}", "numéro de sous-section en double", "pack.subsection_duplicate")
            else:
                sections.add(ident)
                current_h3 = (n, s)
            continue
        if (m := _H2.match(line)) is not None:
            numbered = _H2_NUMBERED.match(m.group(1))
            current_h3 = None
            if numbered is None:
                h2.append((None, m.group(1)))
                current_h2 = None
            else:
                current_h2 = int(numbered.group(1))
                h2.append((current_h2, numbered.group(2)))
                sections.add(f"§{current_h2}")
            continue
        if _H1.match(line) and not line.startswith("##"):
            h1_count += 1
        elif current_h2 == last_section and _NUMBERED_ITEM.match(line):
            to_verify += 1

    if h1_count > 1:
        issue("titre", "le document ne peut avoir qu'un seul titre de niveau 1", "pack.title_multiple")

    expected = [(number, _norm(text)) for number, text in template.headings]
    found = [(number, _norm(text)) for number, text in h2]
    wrong = next(
        (
            other
            for other in alternatives
            if other.language != template.language
            and found == [(number, _norm(text)) for number, text in other.headings]
        ),
        None,
    )
    if wrong is not None:
        issues.insert(0, _wrong_language(template.language, wrong.language))
        return None, issues
    if found != expected:
        for number, text in template.headings:
            if (number, _norm(text)) not in found:
                issue(
                    f"§ {number}",
                    f"section « ## {number}. {text} » manquante ou mal intitulée",
                    "pack.section_missing",
                    number=number,
                    text=text,
                )
        for number, text in h2:
            if (number, _norm(text)) not in expected:
                label = f"{number}. {text}" if number is not None else text
                issue(
                    "document",
                    f"section « ## {label} » inattendue : le modèle ne la prévoit pas",
                    "pack.section_unexpected",
                    label=label,
                )
        if set(found) == set(expected) and len(found) == len(expected):
            issue("document", "les sections ne sont pas dans l'ordre du modèle", "pack.sections_order")

    if not exercises and not any(i.where.startswith("exercice") for i in issues):
        issue(
            f"§ {template.exercises_section}",
            "il faut au moins un exercice « #### N.M.K »",
            "pack.exercise_required",
        )

    if issues:
        return None, issues[:MAX_ISSUES]
    return (
        PackIndex(title=title, sections=frozenset(sections), exercises=frozenset(exercises), to_verify=to_verify),
        [],
    )
