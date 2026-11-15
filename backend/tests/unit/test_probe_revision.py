"""Spec 020: the révision probe set (`scripts/probe.py --revision`) — its dry run, its flags, and one turn driven
offline through the same service the API uses."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.providers.base import Completed, TextDelta
from app.services.prompts import PromptLibrary
from app.services.tutor_service import TutorService
from scripts import probe
from scripts.chapter_files import load_revision
from tests.conftest import tool_call as call
from tests.fixtures.fake_llm import FakeLLM

PROMPTS = PromptLibrary(get_settings().prompts_dir)


@pytest.mark.parametrize("language", ["fr", "en", "nl"])
def test_the_dry_run_names_the_revisions_chapters_and_every_probe(language: str) -> None:
    scope = load_revision("mathematics", PROMPTS, language)  # type: ignore[arg-type]
    probes = probe.REVISION_PROBES[language]
    target = probe.REVISION_OUT[language]
    lines = probe.describe_revision(target, scope, probes, language)  # type: ignore[arg-type]
    assert "aucun appel" in lines[0] and target.name in lines[0]
    assert len(lines) == 2 + len(probes)
    assert {p.label for p in probes if p.secrets} and {p.label for p in probes if p.no_record}
    assert {p.label for p in probes if p.to_path}
    suffix = "" if language == "fr" else f"-{language}"
    assert target.name == f"probe-transcript-revision{suffix}.md"


def test_the_flags_of_a_revision_turn() -> None:
    by_label = {p.label: p for p in probe.REVISION_PROBES["fr"]}
    unasked = by_label["Pas de bilan sans l'élève"]
    turn = probe.Turn("", [], "On continue ?", [])
    assert probe.revision_flags(unasked, ["noté : acquis · 1. Suites numériques"], "fr", turn) == [
        "bilan noté sans que l'élève l'ait donné : noté : acquis · 1. Suites numériques"
    ]
    assert probe.revision_flags(unasked, [], "fr", turn) == []
    section = by_label["Demande d'ouvrir une section"]
    assert probe.revision_flags(section, [], "fr", turn) == [probe.NOT_SENT_TO_PATH]
    assert probe.revision_flags(section, [], "fr", probe.Turn("", [], "Ça se fait dans le parcours.", [])) == []


async def test_a_revision_probe_turn_runs_offline_and_reports_what_was_noted() -> None:
    llm = FakeLLM(
        [
            [TextDelta("Noté."), call("record_result", {"chapter": 1, "section_id": "suites", "outcome": "solid"}), Completed()],
            [TextDelta(" Suivante ?"), Completed()],
        ]
    )
    tutor = TutorService(llm=llm, prompts=PROMPTS, settings=get_settings())  # type: ignore[arg-type]
    scope = load_revision("mathematics", PROMPTS, "fr")
    answer, cards, spoken, noted = await probe.run_revision_probe(tutor, scope, [], "ok", "fr")
    assert noted == ["noté : acquis · 1. Suites numériques"]
    assert "`[révision : noté : acquis · 1. Suites numériques]`" in answer and spoken == "Noté. Suivante ?"
    assert [t["name"] for t in llm.tools] == ["display_board", "clear_board", "record_result"]
