"""Spec 011 R5.4, R8, tasks 6.1/6.2: a turn and a voice session in the course's language.

The French behaviour is pinned by `test_registry`, `test_tutor_service`-style tests and
`test_voice_service` (untouched). This pins that the language reaches the prompt files, the
state text, the tool declarations and the Realtime session, from the chapter and the turn.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from tests.fixtures.fake_clients import FixedAiConfig
from app.services.ai_settings import load_ai_config
from app.api.schemas.chat import ProgressDTO
from app.config import Settings
from app.services import prompt_service
from app.services.tools import registry
from app.services.tools.context import TurnContext
from app.services.voice_service import VoiceService
from tests.fixtures.curricula import lesson_chapter
from tests.fixtures.fake_realtime import FakeRealtime

NOW = datetime(2026, 9, 11, 10, 5)
SHELL = (
    "Célestin.\n<!-- VOICE -->\nSpoken.\n<!-- /VOICE -->\n\n"
    "<!-- SUBJECT -->\n<!-- COURSE_PACK -->\n<!-- CURRICULUM -->\n<!-- MODE -->\n<!-- MODE_OPENING -->\n"
)


class RecordingPrompts:
    """A prompt library that answers `<kind>:<language>` and remembers what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    def _text(self, kind: str, language: str) -> str:
        self.asked.append((kind, language))
        return SHELL if kind == "tutor" else f"[{kind}:{language}]\n"

    def tutor(self, language: str = "fr") -> str:
        return self._text("tutor", language)

    def subject(self, subject: str, language: str = "fr") -> str:
        return self._text("subject", language)

    def mode(self, mode: str, language: str = "fr") -> str:
        return self._text("mode", language)

    def mode_opening(self, mode: str, language: str = "fr") -> str:
        return self._text("opening", language)


def _service(prompts: RecordingPrompts) -> tuple[VoiceService, FakeRealtime]:
    realtime = FakeRealtime()
    settings = Settings(openai_api_key="k", _env_file=None)
    return VoiceService(realtime, prompts, settings, FixedAiConfig(load_ai_config(settings))), realtime  # type: ignore[arg-type]


def _ctx(chapter, progress: ProgressDTO | None = None) -> TurnContext:
    progress = progress or ProgressDTO()
    return TurnContext.from_progress(
        chapter.curriculum, progress.done, progress.active, language=chapter.language
    )


# --- the tool declarations ----------------------------------------------------------


def test_the_french_declarations_are_the_snapshot(snapshot_declarations) -> None:
    current = registry.declarations("parcours", "fr")[:2]
    assert json.dumps(current, ensure_ascii=False, sort_keys=True) == snapshot_declarations


def test_the_english_declarations_equal_the_french_ones_while_the_overlay_is_empty() -> None:
    assert registry.TOOL_TEXT["en"] == {} and registry.TOOL_TEXT["fr"] == {}
    for mode in ("parcours", "discussion"):
        assert registry.declarations(mode, "en") == registry.declarations(mode, "fr")  # type: ignore[arg-type]
        assert registry.realtime_declarations(mode, "en") == registry.realtime_declarations(mode, "fr")  # type: ignore[arg-type]


def test_the_declarations_are_built_once_per_mode_and_language() -> None:
    assert registry.declarations("parcours", "en") is registry.declarations("parcours", "en")
    # An empty overlay shares the French list; a filled one gets its own (see the overlay tests).
    assert registry.declarations("parcours", "en") is registry.declarations("parcours", "fr")
    assert registry.declarations() is registry.declarations("parcours", "fr")


def test_an_overlay_replaces_a_text_in_one_language_only(monkeypatch: pytest.MonkeyPatch) -> None:
    overlay = {"en": {"clear_board": {"/description": "Clears the board."}}, "fr": {}}
    monkeypatch.setattr(registry, "TOOL_TEXT", overlay)
    english = registry._declare("parcours", "en")
    french = registry._declare("parcours", "fr")
    by_name = {t["name"]: t for t in english}
    assert by_name["clear_board"]["description"] == "Clears the board."
    assert {t["name"]: t for t in french}["clear_board"]["description"] != "Clears the board."
    # Everything else is the declaration as built.
    assert [t for t in english if t["name"] != "clear_board"] == [t for t in french if t["name"] != "clear_board"]


def test_an_overlay_reaches_a_nested_schema_description(monkeypatch: pytest.MonkeyPatch) -> None:
    declared = registry.declarations("parcours", "fr")[0]
    pointer = "/parameters/properties/card/description"
    node: Any = declared
    try:
        for key in pointer.split("/")[1:]:
            node = node[key]
        exists = True
    except KeyError:
        exists = False
    if not exists:
        pointer = "/description"
    monkeypatch.setattr(registry, "TOOL_TEXT", {"en": {"display_board": {pointer: "Shows a card."}}, "fr": {}})
    assert registry._declare("parcours", "en")[0] != declared
    assert registry._declare("parcours", "fr")[0] == declared


def test_a_stale_pointer_fails_when_the_declarations_are_built(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "TOOL_TEXT", {"en": {"clear_board": {"/parameters/nope/description": "x"}}, "fr": {}})
    with pytest.raises(ValueError, match="does not resolve"):
        registry._declare("parcours", "en")


# --- the voice session ---------------------------------------------------------------


@pytest.mark.parametrize("language", ["fr", "en"])
def test_the_voice_session_is_built_from_the_chapters_language(language: str) -> None:
    prompts = RecordingPrompts()
    service, _ = _service(prompts)
    chapter = lesson_chapter(language=language)
    config = service.session_config(chapter)
    assert config["audio"]["input"]["transcription"]["language"] == language
    assert config["tools"] == registry.realtime_declarations("parcours", language)  # type: ignore[arg-type]
    assert f"[subject:{language}]" in config["instructions"] and f"[mode:{language}]" in config["instructions"]
    assert {lang for _, lang in prompts.asked} == {language}


def test_the_french_session_config_does_not_move_with_the_language_parameter() -> None:
    service, _ = _service(RecordingPrompts())
    default = service.session_config(lesson_chapter())
    assert default == service.session_config(lesson_chapter(language="fr"))
    assert default["audio"]["input"]["transcription"] == {"model": "gpt-4o-mini-transcribe", "language": "fr"}


def test_the_instructions_of_the_two_languages_differ_only_by_their_files() -> None:
    service, _ = _service(RecordingPrompts())
    french = service.instructions(lesson_chapter(language="fr"))
    english = service.instructions(lesson_chapter(name="valid_en.yaml", language="en"))
    assert french != english and "Chapter path" in english and "Parcours du chapitre" in french


def test_the_voice_state_text_is_in_the_courses_language() -> None:
    service, _ = _service(RecordingPrompts())
    chapter = lesson_chapter(name="valid_en.yaml", language="en")
    seed = service.seed([], _ctx(chapter), now=NOW)
    text = seed[-1]["content"][0]["text"]
    assert text.startswith("It is Friday 11 September, 10:05 (morning).") and "Path status" in text
    started = service.execute_tool("start_section", '{"section_id":"intro"}', _ctx(chapter))
    assert started.state_text and "Current section" in started.state_text
    assert started.state_text.startswith("It is ")  # the time comes from the settings' clock
    refused = service.execute_tool("complete_section", '{"section_id":"intro","summary":"x"}', _ctx(chapter))
    assert json.loads(refused.output)["error"] == "No section is in progress. Start one with start_section."


# --- the text turn -------------------------------------------------------------------


def test_build_input_reads_the_chapters_language() -> None:
    from app.services.tutor_service import TutorService
    from tests.fixtures.fake_llm import FakeLLM

    for language, name in (("fr", "valid.yaml"), ("en", "valid_en.yaml")):
        prompts = RecordingPrompts()
        service = TutorService(FakeLLM([]), prompts, Settings(openai_api_key="k", _env_file=None))  # type: ignore[arg-type]
        chapter = lesson_chapter(name=name, language=language)
        items = service.build_input(chapter, [], _ctx(chapter))
        assert {lang for _, lang in prompts.asked} == {language}
        developer = items[0]["content"][0]["text"]
        assert f"[subject:{language}]" in developer
        assert ("Chapter path" in developer) == (language == "en")
        assert ("Path status" in items[-1]["content"][0]["text"]) == (language == "en")


def test_prompt_service_defaults_to_french() -> None:
    chapter = lesson_chapter()
    items = prompt_service.build(
        SHELL, "s", "P", chapter.curriculum, _ctx(chapter).progress, [], "m", "o"
    )
    assert "Parcours du chapitre" in items[0]["content"][0]["text"]


# --- observability (§11) -------------------------------------------------------------


@pytest.mark.parametrize("language", ["fr", "en"])
async def test_a_voice_session_is_logged_with_its_language(
    language: str, caplog: pytest.LogCaptureFixture
) -> None:
    service, _ = _service(RecordingPrompts())
    chapter = lesson_chapter(language=language)
    with caplog.at_level("INFO"):
        await service.create_session(chapter, [], _ctx(chapter))
    record = next(r for r in caplog.records if r.getMessage() == "voice_session_created")
    assert record.language == language  # type: ignore[attr-defined]


@pytest.mark.parametrize("language", ["fr", "en"])
async def test_a_turn_is_logged_with_its_language(language: str, caplog: pytest.LogCaptureFixture) -> None:
    from app.providers.base import Completed, TextDelta
    from app.services.tutor_service import TutorService
    from tests.fixtures.fake_llm import FakeLLM

    service = TutorService(
        FakeLLM([[TextDelta("Hi."), Completed()]]),
        RecordingPrompts(),  # type: ignore[arg-type]
        Settings(openai_api_key="k", _env_file=None),
    )
    chapter = lesson_chapter(language=language)
    ctx = _ctx(chapter)
    with caplog.at_level("INFO"):
        async for _ in service.run_turn(service.build_input(chapter, [], ctx), ctx):
            pass
    record = next(r for r in caplog.records if r.getMessage() == "turn_complete")
    assert record.language == language  # type: ignore[attr-defined]
