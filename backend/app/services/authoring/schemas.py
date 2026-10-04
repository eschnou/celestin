"""What the curriculum stage asks the model for (005 design 3.7).

Strict-output compatible: every field required, no defaults, no length limits.
Limits and kind rules are the domain's (`Curriculum`), applied after
`draft_to_data`, so their messages can go back to the model for a repair.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.curriculum import Kind


class SectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Kind
    title: str
    goal: str
    done_when: str
    pack: list[str]
    beats: list[str]
    exercises: list[str]
    count: int | None


class CurriculumDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    sections: list[SectionDraft]


def draft_to_data(data: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    """The model's JSON as curriculum data: the id is ours, and empty lists or a
    null count are dropped so a kind mismatch reads as such, not as a shape error."""
    sections = []
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            sections.append(section)
            continue
        cleaned = {k: v for k, v in section.items() if not (k in ("pack", "beats", "exercises") and v == [])}
        if cleaned.get("count") is None:
            cleaned.pop("count", None)
        sections.append(cleaned)
    return {"id": chapter_id, "title": data.get("title"), "sections": sections}
