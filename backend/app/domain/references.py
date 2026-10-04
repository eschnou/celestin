"""Curriculum references into the pack (005 design 3.6).

A section's `pack` entries start with a section id (`§4` or `§4.2`); its
`exercises` entries start with an exercise id (`6.1.3`) or, for a pool drawn from a
whole part of the pack (a table of applications, the definitions to recite), with a
section id. What follows is free text for the tutor (« 6.1.1 (uniquement u₁ et r) »).
Every id must exist in the pack.
"""

from __future__ import annotations

import re

from app.domain.curriculum import Curriculum
from app.domain.pack import ContentIssue, PackIndex

_SECTION_REF = re.compile(r"^\s*§\s?(\d+(?:\.\d+)?)")
_EXERCISE_REF = re.compile(r"^\s*(\d+\.\d+\.\d+)")


def _missing_section(where: str, number: str) -> ContentIssue:
    return ContentIssue(
        where,
        f"la section §{number} n'existe pas dans le contenu",
        "references.section_missing",
        {"id": number},
    )


def reference_issues(curriculum: Curriculum, index: PackIndex) -> list[ContentIssue]:
    issues: list[ContentIssue] = []
    for section in curriculum.sections:
        where = f"section « {section.id} »"
        for entry in section.pack:
            match = _SECTION_REF.match(entry)
            if match is None:
                issues.append(
                    ContentIssue(
                        where,
                        f"« {entry} » doit commencer par un numéro de section du contenu, comme « §4.2 »",
                        "references.section_ref",
                        {"entry": entry},
                    )
                )
            elif f"§{match.group(1)}" not in index.sections:
                issues.append(_missing_section(where, match.group(1)))
        for entry in section.exercises:
            match = _EXERCISE_REF.match(entry)
            by_section = _SECTION_REF.match(entry)
            if match is not None:
                if match.group(1) not in index.exercises:
                    issues.append(
                        ContentIssue(
                            where,
                            f"l'exercice {match.group(1)} n'existe pas dans le contenu",
                            "references.exercise_missing",
                            {"id": match.group(1)},
                        )
                    )
            elif by_section is not None:
                if f"§{by_section.group(1)}" not in index.sections:
                    issues.append(_missing_section(where, by_section.group(1)))
            else:
                issues.append(
                    ContentIssue(
                        where,
                        f"« {entry} » doit commencer par un numéro d'exercice (« 6.1.3 ») ou de section (« §4.2 ») du contenu",
                        "references.exercise_ref",
                        {"entry": entry},
                    )
                )
    return issues[:20]
