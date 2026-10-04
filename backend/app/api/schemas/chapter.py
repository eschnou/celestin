"""Chapter overview DTO (design 3.1). Titles and goals only: built from the
domain `Curriculum` by attribute, so any field not named here never leaves."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SectionOverviewDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    index: int
    kind: str
    title: str
    goal: str


class ChapterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    sections: list[SectionOverviewDTO]
