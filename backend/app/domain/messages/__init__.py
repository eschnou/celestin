"""The messages the application writes for the student, per interface language
(spec 010 §3.3).

Domain code builds a key and parameters; `render` turns them into text at the edge
(the HTTP handler, the middleware, the SSE stream, the route DTOs) with the language of
the request. The French catalog is the text the code always said; the English one
sits next to it, with the same keys and the same `str.format` fields (a test pins both).

Nothing here is for the model. What the model reads (prompts, tool outputs, history,
the curriculum rendering) never takes a locale.
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.messages.en import MESSAGES as EN
from app.domain.messages.fr import MESSAGES as FR

log = logging.getLogger(__name__)

CATALOGS: dict[Locale, dict[str, str]] = {"fr": FR, "en": EN}

_fallbacks_logged: set[str] = set()


def has_message(key: str) -> bool:
    """Whether the catalog says anything for `key` (French is the complete one)."""
    return key in CATALOGS[DEFAULT_LOCALE]


def _log_once(level: int, event: str, key: str) -> None:
    if key not in _fallbacks_logged:
        _fallbacks_logged.add(key)
        log.log(level, event, extra={"key": key})


def plural_category(locale: Locale, count: int) -> str:
    """`one` or `other`. French counts 0 and 1 as singular; English only 1."""
    if locale == "fr":
        return "one" if count in (0, 1) else "other"
    return "one" if count == 1 else "other"


def _find(locale: Locale, key: str, count: object) -> str | None:
    catalog = CATALOGS[locale]
    if isinstance(count, int) and not isinstance(count, bool):
        plural = catalog.get(f"{key}.{plural_category(locale, count)}")
        if plural is not None:
            return plural
    return catalog.get(key)


def render(key: str, locale: Locale = DEFAULT_LOCALE, **params: Any) -> str:
    """The message for `key` in `locale`. When a `count` is given, the plural form
    (`key.one` / `key.other`) is preferred. A key the language lacks falls back to
    French and is logged once (the key only); a key nobody has renders the generic
    error rather than raising, because this runs while another error is being
    reported."""
    count = params.get("count")
    template = _find(locale, key, count)
    if template is None and locale != DEFAULT_LOCALE:
        template = _find(DEFAULT_LOCALE, key, count)
        if template is not None:
            _log_once(logging.WARNING, "i18n_fallback", key)
    if template is None:
        _log_once(logging.ERROR, "i18n_missing", key)
        template = CATALOGS[locale]["internal"]  # the generic error, in the request's language
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        log.error("i18n_bad_params", extra={"key": key})
        return template
