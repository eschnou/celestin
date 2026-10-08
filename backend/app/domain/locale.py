"""The interface languages (spec 010 §3.2). Imports nothing, so errors can use it.

The twin of `frontend/src/lib/locale.ts`: `tests/fixtures/accept_language_cases.json`
is the case table both read, so the page the browser renders and the messages the API
sends agree on the same header.
"""

from __future__ import annotations

import re
from typing import Literal, TypeGuard, get_args

Locale = Literal["fr", "en", "nl"]
LOCALES: tuple[Locale, ...] = get_args(Locale)
DEFAULT_LOCALE: Locale = "fr"

_QUALITY = re.compile(r"^\d+(\.\d+)?$")


def is_locale(value: object) -> TypeGuard[Locale]:
    return isinstance(value, str) and value in LOCALES


def parse_accept_language(header: str | None) -> Locale:
    """The first supported language of an `Accept-Language` header, by quality order
    and then by position, matched on the primary subtag (`fr-BE` is `fr`). An
    unsupported or malformed entry is skipped, never an error; no match is French."""
    if not header:
        return DEFAULT_LOCALE
    ranked: list[tuple[float, int, Locale]] = []
    for position, entry in enumerate(header.split(",")):
        tag, *params = entry.split(";")
        tag = tag.strip().lower()
        if not tag or tag == "*":
            continue
        quality: float | None = 1.0
        for param in params:
            key, _, value = param.partition("=")
            if key.strip().lower() != "q":
                continue
            text = value.strip()
            quality = float(text) if _QUALITY.match(text) else None
            if quality is None or quality > 1:
                quality = None
                break
        if quality is None or quality == 0:
            continue
        primary = tag.split("-")[0]
        if is_locale(primary):
            ranked.append((quality, position, primary))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][2] if ranked else DEFAULT_LOCALE
