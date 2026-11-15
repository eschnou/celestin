"""Séance and notebook DTOs (spec 018).

A parcours séance is read back as a discussion is, with the same `StoredEntry`: each
tool says what a stored call of it shows (`registry.shown`, asked by `app/api/stored.py`),
the parcours tools' markers and their extra fields (`review`, `next_section_id`) included.
The notebook is the service's own shape (`services/seance.py`'s dataclasses), read here by
attribute.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_serializer

from app.api.schemas.chat import Id, ProgressDTO
from app.api.schemas.discussion import ReportedTurn, StoredEntry


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeanceDTO(_Model):
    id: Id
    section_id: str | None
    entries: list[StoredEntry]


class SeanceSummary(_Model):
    """What the lesson's map says of a section's séances: how many cards they hold."""

    cards: int


class SeanceResponse(_Model):
    """The live séance, and what the lesson starts from, read in the same handler: the
    progress, and per section with a séance at the current content version its cards."""

    seance: SeanceDTO | None
    progress: ProgressDTO
    seances: dict[str, SeanceSummary]


class SeanceReportRequest(ReportedTurn):
    """A parcours turn the browser reports (spec 018 D7): a spoken one (same deviation as
    007 D1), or one the learner stopped. Stored with the split rule; a `start_section`
    entry may carry `review`."""


class NotebookItem(_Model):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    kind: Literal["card", "tutor", "learner"]
    card: dict[str, Any] | None = None
    text: str | None = None

    @model_serializer(mode="wrap")
    def _shape(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        data.pop("text" if self.kind == "card" else "card", None)
        return data


class NotebookSection(_Model):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    section_id: str
    items: list[NotebookItem]


class NotebookResponse(_Model):
    """Built from the service's notebook (dataclasses) in one step, by attribute."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    sections: list[NotebookSection]
