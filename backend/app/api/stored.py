"""Stored entries as the browser reads them back (007 design 4.3, spec 018).

The one place that asks each tool what a stored call of it shows (`registry.shown`)
and hands the answer to the `StoredEntry` DTO, so the wire schemas never import the
services (`backend/CLAUDE.md`, layering). Both modes read their transcripts through it.
"""

from __future__ import annotations

from app.api.schemas.chat import Entry, ToolEntry
from app.api.schemas.discussion import StoredEntry
from app.domain.locale import DEFAULT_LOCALE, Locale
from app.domain.mode import Mode
from app.services.tools import registry
from app.services.tools.context import StoredView


def stored_entry(
    entry: Entry, locale: Locale = DEFAULT_LOCALE, mode: Mode = "discussion", view: StoredView = StoredView()
) -> StoredEntry:
    """`view` is what a parcours entry is read against: the current curriculum (a
    section's label) and progress (where the page turns now, and whether a start
    recorded without its `review` was one); for a révision, its chapters' curricula."""
    if isinstance(entry, ToolEntry):
        shown = registry.shown(entry, mode, view)
        return StoredEntry.of(entry, locale, shown.marker, shown.fields)
    return StoredEntry.of(entry, locale)
