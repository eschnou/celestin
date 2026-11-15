"""Spec 020 with specs 010 and 011: a révision's model input takes the course language only. The same scripted
révision turn, for a French, an English and a Dutch account on the same course, hands the provider identical input;
a French, an English and a Dutch course hand it different input."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.config import Settings
from app.providers.base import Completed, TextDelta
from tests.conftest import CARD
from tests.conftest import tool_call as call
from tests.fixtures.fake_llm import FakeLLM
from tests.integration.test_revision_endpoint import add_chapter

FIRST_SECTION = {"fr": "suites", "en": "sequences", "nl": "rijen"}


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Settings, "local_now", lambda self: datetime(2026, 11, 15, 18, 5))


async def _run(make_client, locale: str, language: str = "fr") -> list:
    llm = FakeLLM(
        [
            [
                TextDelta("Regarde."),
                call("display_board", {"card": CARD}, "c1"),
                call("record_result", {"chapter": 1, "section_id": FIRST_SECTION[language], "outcome": "shaky"}, "c2"),
                Completed(),
            ],
            [TextDelta("Tu suis ?"), Completed()],
            [TextDelta("Encore."), Completed()],
        ]
    )
    client, _ = make_client(llm, email=f"{locale}-{language}-r@example.be", locale=locale, language=language)
    async with client:
        add_chapter(client, language=language)
        chapters = [c["id"] for c in (await client.get(f"/api/courses/{client.course_id}/revision")).json()["chapters"]]
        revision = (await client.post(f"/api/courses/{client.course_id}/revision", json={"chapter_ids": chapters})).json()
        for message in (None, "fragile"):
            r = await client.post(
                "/api/revision/turn",
                json={"course_id": client.course_id, "revision_id": revision["revision"]["id"], "message": message},
            )
            assert r.status_code == 200
    return llm.calls


def _dumped(calls: list) -> str:
    return json.dumps(calls, ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize("language", ["fr", "en", "nl"])
async def test_the_provider_gets_the_same_revision_input_whatever_the_interface_language(make_client, language) -> None:
    french, english, dutch = [await _run(make_client, locale, language) for locale in ("fr", "en", "nl")]
    assert len(french) == 3
    assert _dumped(french) == _dumped(english) == _dumped(dutch)


async def test_a_french_an_english_and_a_dutch_course_hand_the_provider_different_revision_input(make_client) -> None:
    runs = {language: await _run(make_client, "fr", language) for language in ("fr", "en", "nl")}
    assert len({_dumped(calls) for calls in runs.values()}) == 3
    developer = {language: calls[0]["input"][0]["content"][0]["text"] for language, calls in runs.items()}
    assert "## La révision" in developer["fr"] and "# Chapitre 2 — " in developer["fr"]
    assert "## The revision" in developer["en"] and "# Chapter 2 — " in developer["en"]
    assert "## De herhaling" in developer["nl"] and "# Hoofdstuk 2 — " in developer["nl"]
    state = {language: calls[-1]["input"][-1]["content"][0]["text"] for language, calls in runs.items()}
    assert state["fr"].startswith("Nous sommes dimanche 15 novembre")
    assert state["en"].startswith("It is Sunday 15 November")
    assert state["nl"].startswith("Het is zondag 15 november")
    # The tool output follows the course too.
    outputs = {
        language: [i["output"] for i in calls[1]["input"] if i.get("type") == "function_call_output"][-1]
        for language, calls in runs.items()
    }
    assert "Bilan noté" in outputs["fr"] and "Self-assessment noted" in outputs["en"] and "Zelfbeoordeling" in outputs["nl"]
