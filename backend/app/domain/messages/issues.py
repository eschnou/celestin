"""Content issues for the student's editor (spec 010 §4.9).

A `ContentIssue` has two audiences. The authoring model reads its French `message` to
repair its own output, and that text never changes. The student reads it in the editor
after a refused save, in the interface language: `render_issue` looks up `issue.<code>`
and falls back to `message` for an issue nobody has coded yet.
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.messages import has_message, render

# What `where` names, in the interface language: its words and its patterns. `section « id »` is not
# here on purpose: the curriculum editor parses it to find the section, so it keeps its one form.
# French is what the code writes, so its entry is empty. A locale with no entry fails at import of
# `test_issue_messages`, not in front of a user.
WHERE_WORDS: dict[Locale, tuple[dict[str, str], list[tuple[re.Pattern[str], str]]]] = {
    "fr": ({}, []),
    "en": (
        {"titre": "title", "chapitre": "chapter", "parcours": "path"},
        [
            (re.compile(r"^exercice (\S+)$"), r"exercise \1"),
            (re.compile(r"^section n°(\d+)$"), r"section no. \1"),
        ],
    ),
    "nl": (
        {"titre": "titel", "chapitre": "hoofdstuk", "parcours": "traject"},
        [
            (re.compile(r"^exercice (\S+)$"), r"oefening \1"),
            (re.compile(r"^section n°(\d+)$"), r"sectie nr. \1"),
        ],
    ),
}


def render_where(where: str, locale: Locale = DEFAULT_LOCALE) -> str:
    words, patterns = WHERE_WORDS[locale]
    if where in words:
        return words[where]
    for pattern, replacement in patterns:
        if pattern.match(where):
            return pattern.sub(replacement, where)
    return where


def _params(issue: Any, locale: Locale) -> dict[str, Any]:
    """The issue's params for the catalog. A param named `*_language` holds a language code and
    is replaced by that language's name in the reader's language (`language.<code>`)."""
    params = dict(getattr(issue, "params", {}) or {})
    return {
        key: render(f"language.{value}", locale) if key.endswith("_language") else value
        for key, value in params.items()
    }


def render_issue(issue: Any, locale: Locale = DEFAULT_LOCALE) -> dict[str, str]:
    """`{where, message}` for the student. Works on anything shaped like a ContentIssue."""
    code = getattr(issue, "code", "") or ""
    key = f"issue.{code}"
    message = issue.message
    if code and has_message(key):
        message = render(key, locale, **_params(issue, locale))
    return {"where": render_where(issue.where, locale), "message": message}


def issue_text(issue: Any, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    """The reason as the authoring model reads it to repair its output: in the course's
    language (spec 011 R4.6). French is the `message` the code always wrote, byte for byte;
    another language is the catalog's sentence for the issue's code when there is one, else the
    French `message`. The student's editor does not use this: it keeps `render_issue`, in the
    interface language. One issue, two audiences, chosen by who reads."""
    if language == DEFAULT_COURSE_LANGUAGE:
        return str(issue.message)
    return render_issue(issue, language)["message"]  # the course codes are the interface codes
