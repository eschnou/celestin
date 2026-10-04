"""The label the transcript shows for a tool call (spec 010 §4.6).

A `Marker` is a string, the French one, so everything that compares or serialises it
keeps working; it also remembers its catalog key and parameters, so the edge can render
it in the language of the request (`tool_events.event_of`, `marker_for`). Markers never
reach the model: the outcome keeps `marker` and `output` apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.messages import render


class Marker(str):
    key: str
    params: Mapping[str, Any]

    def __new__(cls, key: str, **params: Any) -> Marker:
        marker = super().__new__(cls, render(key, DEFAULT_LOCALE, **params))
        marker.key = key
        marker.params = params
        return marker

    def __getnewargs_ex__(self) -> tuple[tuple[str], dict[str, Any]]:
        """copy and pickle rebuild a str subclass from its text; rebuild it from its key."""
        return (self.key,), dict(self.params)

    def render(self, locale: Locale = DEFAULT_LOCALE) -> str:
        return render(self.key, locale, **self.params)
