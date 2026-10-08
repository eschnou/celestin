"""A transcription as text with page markers (006 design 3.6, 4.2). Pure.

The vision model answers per batch of pages; each page starts with `--- page N ---`.
These helpers check a batch has exactly its pages, join batches in page order,
count the conventions the authoring stages rely on, and rewrite the handwritten
lines the verification pass found uncertain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.domain.pack import ContentIssue

PAGE_MARKER = "--- page {n} ---"


@dataclass(frozen=True)
class Markers:
    """What a transcription writes for what it could not read, per course language (spec 011
    R4.3). Opening forms only: `[manuscrit` starts both `[manuscrit]` and `[manuscrit: …]`.
    The page marker above is language-free."""

    handwritten: str
    uncertain: str
    illegible: str
    empty_page: str
    # The one thing a photo of work is read as when it holds no writing (`services/work_reading.py`).
    nothing: str
    # The sentences about a batch of pages, as the model reads them when it must redo it.
    missing: str  # + page numbers
    unexpected: str  # + page numbers
    disordered: str
    empty_without_marker: str  # {page}


MARKERS = by_language(
    fr=Markers(
        handwritten="[manuscrit",
        uncertain="[incertain",
        illegible="[illisible]",
        empty_page="[page vide]",
        nothing="[rien de lisible]",
        missing="repère manquant pour la page ",
        unexpected="page inattendue ",
        disordered="repères de page en double ou dans le désordre",
        empty_without_marker="page vide sans « [page vide] »",
    ),
    en=Markers(
        handwritten="[handwritten",
        uncertain="[uncertain",
        illegible="[illegible]",
        empty_page="[empty page]",
        nothing="[nothing legible]",
        missing="missing marker for page ",
        unexpected="unexpected page ",
        disordered="page markers duplicated or out of order",
        empty_without_marker="empty page without “[empty page]”",
    ),
    nl=Markers(
        handwritten="[handgeschreven",
        uncertain="[onzeker",
        illegible="[onleesbaar]",
        empty_page="[lege pagina]",
        nothing="[niets leesbaar]",
        missing="ontbrekende markering voor pagina ",
        unexpected="onverwachte pagina ",
        disordered="paginamarkeringen dubbel of in de verkeerde volgorde",
        empty_without_marker="lege pagina zonder “[lege pagina]”",
    ),
)
_MARKER = re.compile(r"^\s*-{3}\s*page\s+(\d+)\s*-{3}\s*$", re.IGNORECASE | re.MULTILINE)
_DIGIT = re.compile(r"\d")


def validate_batch(
    text: str, numbers: list[int], language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> tuple[str | None, list[ContentIssue]]:
    """The batch normalised (anything before the first marker dropped, markers in
    canonical form), or why it is not exactly `numbers`, in order, each non-empty."""
    words = MARKERS[language]
    found = [(int(m.group(1)), m.start(), m.end()) for m in _MARKER.finditer(text)]
    seen = [n for n, _, _ in found]
    issues: list[ContentIssue] = []
    if seen != numbers:
        missing = [n for n in numbers if n not in seen]
        extra = [n for n in seen if n not in numbers]
        if missing:
            issues.append(ContentIssue("pages", words.missing + ", ".join(map(str, missing))))
        if extra:
            issues.append(ContentIssue("pages", words.unexpected + ", ".join(map(str, extra))))
        if not missing and not extra:
            issues.append(ContentIssue("pages", words.disordered))
        return None, issues
    parts = []
    for i, (number, _, end) in enumerate(found):
        body = text[end : found[i + 1][1] if i + 1 < len(found) else len(text)].strip()
        if not body:
            issues.append(ContentIssue(f"page {number}", words.empty_without_marker))
        parts.append(PAGE_MARKER.format(n=number) + "\n\n" + body)
    return (None, issues) if issues else ("\n\n".join(parts), [])


def join_batches(batches: dict[int, str]) -> str:
    """Batches keyed by their first page number, joined in page order."""
    return "\n\n".join(batches[first] for first in sorted(batches)).strip() + "\n"


@dataclass(frozen=True)
class MarkerCounts:
    handwritten: int
    uncertain: int
    illegible: int


def count_markers(text: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> MarkerCounts:
    markers = MARKERS[language]
    return MarkerCounts(
        handwritten=text.count(markers.handwritten),
        uncertain=text.count(markers.uncertain),
        illegible=text.count(markers.illegible),
    )


def handwritten_numbers(
    page_text: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> list[tuple[int, str]]:
    """(line index, line) of the handwritten lines with digits and no doubt marked
    yet: what the verification pass re-reads."""
    markers = MARKERS[language]
    return [
        (i, line)
        for i, line in enumerate(page_text.split("\n"))
        if markers.handwritten in line and _DIGIT.search(line) and markers.uncertain not in line
    ]


def apply_uncertain(
    page_text: str,
    rewrites: list[tuple[int, str, str]],
    language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
) -> str:
    """Replace line `index` by `new` when it still reads `original` and `new` marks a
    doubt; anything else is ignored, so a confused answer cannot rewrite the page."""
    uncertain = MARKERS[language].uncertain
    lines = page_text.split("\n")
    for index, original, new in rewrites:
        if 0 <= index < len(lines) and lines[index] == original and uncertain in new:
            lines[index] = new
    return "\n".join(lines)


def split_pages(text: str) -> dict[int, str]:
    """A joined transcription back into its pages, marker line included."""
    found = list(_MARKER.finditer(text))
    return {
        int(m.group(1)): text[m.start() : found[i + 1].start() if i + 1 < len(found) else len(text)].strip()
        for i, m in enumerate(found)
    }
