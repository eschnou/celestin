"""Spec 014 §3.5: the pure translation between Responses-shaped items and Chat Completions."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.api.schemas.chat import LearnerEntry, ToolEntry, TutorEntry
from app.config import Settings
from app.providers.chat_translate import (
    ThinkStripper,
    extract_json,
    json_instruction,
    strip_think,
    to_messages,
    to_tools,
    usage_dict,
)
from app.services import history
from app.services.prompts import PromptLibrary
from app.services.tools import registry
from app.services.tutor_service import TutorService
from tests.fixtures.curricula import ctx_for, lesson_chapter
from tests.fixtures.fake_llm import FakeLLM


def dev(text: str, breakpoint: bool = False) -> dict:
    part: dict = {"type": "input_text", "text": text}
    if breakpoint:
        part["prompt_cache_breakpoint"] = {"mode": "explicit"}
    return {"role": "developer", "content": [part]}


# ------------------------------------------------------------------ messages


def test_the_first_developer_message_is_the_system_message_and_later_ones_are_user_messages() -> None:
    messages = to_messages([dev("rules", True), {"role": "user", "content": "salut"}, dev("state")])
    assert messages == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "salut"},
        {"role": "user", "content": "state"},
    ]


def test_an_opening_turn_has_a_user_message() -> None:
    """The prompt and the path state, nothing else: chat templates that want a user query still get one."""
    assert [m["role"] for m in to_messages([dev("rules"), dev("state")])] == ["system", "user"]


def test_a_system_text_goes_first_and_every_developer_message_after_it_is_a_user_message() -> None:
    messages = to_messages([{"role": "user", "content": "x"}, dev("late")], system="instructions")
    assert [m["role"] for m in messages] == ["system", "user", "user"] and messages[0]["content"] == "instructions"


def test_a_system_message_in_the_items_counts_as_the_system_message() -> None:
    messages = to_messages([{"role": "system", "content": "rules"}, {"role": "user", "content": "x"}])
    assert [m["role"] for m in messages] == ["system", "user"]


def test_text_parts_are_joined_and_assistant_content_is_a_string() -> None:
    parts = [{"type": "output_text", "text": "a"}, {"type": "output_text", "text": "b"}]
    assert to_messages([{"role": "assistant", "content": parts}]) == [{"role": "assistant", "content": "a\n\nb"}]


def test_an_image_makes_the_user_content_a_list_of_parts() -> None:
    content = [
        {"type": "input_text", "text": "Page 1"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64,AAAA", "detail": "high"},
    ]
    (message,) = to_messages([{"role": "user", "content": content}])
    assert message["content"] == [
        {"type": "text", "text": "Page 1"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA", "detail": "high"}},
    ]
    (plain,) = to_messages([{"role": "user", "content": [{"type": "input_text", "text": "x"}]}])
    assert plain["content"] == "x"
    (no_detail,) = to_messages([{"role": "user", "content": [{"type": "input_image", "image_url": "u"}]}])
    assert no_detail["content"] == [{"type": "image_url", "image_url": {"url": "u"}}]


def test_a_call_and_its_output_become_an_assistant_message_and_a_tool_message() -> None:
    items = [
        {"role": "user", "content": "go"},
        {"type": "function_call", "call_id": "c1", "name": "clear_board", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": '{"ok":true}'},
    ]
    assert to_messages(items) == [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "clear_board", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
    ]


def test_the_text_before_a_call_and_the_calls_after_it_share_one_assistant_message() -> None:
    items = [
        {"role": "assistant", "content": "Je regarde."},
        {"type": "function_call", "call_id": "c1", "name": "a", "arguments": '{"x":1}'},
        {"type": "function_call", "call_id": "c2", "name": "b", "arguments": ""},
        {"type": "function_call_output", "call_id": "c1", "output": "1"},
        {"type": "function_call_output", "call_id": "c2", "output": "2"},
    ]
    messages = to_messages(items)
    assert [m["role"] for m in messages] == ["assistant", "tool", "tool"]
    assert messages[0]["content"] == "Je regarde."
    assert [c["id"] for c in messages[0]["tool_calls"]] == ["c1", "c2"]
    assert messages[0]["tool_calls"][1]["function"]["arguments"] == "{}"  # an empty argument string is an empty object


def test_calls_separated_by_their_outputs_stay_in_their_own_messages() -> None:
    items = [
        {"type": "function_call", "call_id": "c1", "name": "a", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": "1"},
        {"type": "function_call", "call_id": "c2", "name": "b", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c2", "output": "2"},
    ]
    assert [m["role"] for m in to_messages(items)] == ["assistant", "tool", "assistant", "tool"]


def test_the_items_are_not_modified() -> None:
    items = [dev("rules", True), {"type": "function_call", "call_id": "c", "name": "a", "arguments": "{}"}]
    before = json.dumps(items)
    to_messages(items)
    assert json.dumps(items) == before


def test_the_applications_own_turn_input_translates_to_a_valid_conversation() -> None:
    """The input a real turn builds (prompt, history with a replayed tool call, state), through the translator."""
    settings = Settings(openai_api_key="k", _env_file=None)
    chapter = lesson_chapter()
    service = TutorService(llm=FakeLLM([]), prompts=PromptLibrary(settings.prompts_dir), settings=settings)
    entries = [
        LearnerEntry(kind="learner", text="Bonjour"),
        TutorEntry(kind="tutor", text="Salut !"),
        ToolEntry(kind="tool", name="clear_board", arguments={}, ok=True, error=None),
        LearnerEntry(kind="learner", text="Et ensuite ?"),
    ]
    messages = to_messages(service.build_input(chapter, entries, ctx_for()))
    # The tutor's words and the call it made right after are one assistant message; the state is a user message.
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "user", "user"]
    assert "prompt_cache_breakpoint" not in json.dumps(messages)
    assert messages[2]["content"] == "Salut !" and messages[2]["tool_calls"][0]["function"]["name"] == "clear_board"
    assert messages[2]["tool_calls"][0]["id"] == messages[3]["tool_call_id"]
    # Every tool message answers a call that came just before it, as the API requires.
    answered = {c["id"] for m in messages if m["role"] == "assistant" for c in m.get("tool_calls", [])}
    assert {m["tool_call_id"] for m in messages if m["role"] == "tool"} <= answered


def test_the_translated_history_matches_what_history_produces() -> None:
    items = history.to_provider_input([LearnerEntry(kind="learner", text="x")], 10_000, ctx_for())
    assert to_messages(items) == [{"role": "user", "content": "x"}]


# ------------------------------------------------------------------ tools


def test_tools_keep_their_name_description_and_parameters() -> None:
    declared = registry.declarations("parcours", "fr")
    chat = to_tools(declared, openai=False)
    assert [t["function"]["name"] for t in chat] == [d["name"] for d in declared]
    assert all(t["type"] == "function" and "strict" not in t["function"] for t in chat)
    assert chat[0]["function"]["parameters"] == declared[0]["parameters"]


def test_strict_is_kept_for_openai_only() -> None:
    declared = [{"type": "function", "name": "t", "description": "d", "parameters": {"type": "object"}, "strict": True}]
    assert to_tools(declared, openai=True)[0]["function"]["strict"] is True
    assert "strict" not in to_tools(declared, openai=False)[0]["function"]


# ------------------------------------------------------------------ usage


def test_usage_in_the_responses_shape() -> None:
    usage = SimpleNamespace(
        prompt_tokens=100,
        completion_tokens=40,
        prompt_tokens_details=SimpleNamespace(cached_tokens=30),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=12),
    )
    assert usage_dict(usage) == {
        "input_tokens": 100,
        "output_tokens": 40,
        "input_tokens_details": {"cached_tokens": 30},
        "output_tokens_details": {"reasoning_tokens": 12},
    }


@pytest.mark.parametrize(
    "usage",
    [None, {}, SimpleNamespace(prompt_tokens=None, completion_tokens=None, prompt_tokens_details=None)],
)
def test_missing_usage_fields_count_as_zero(usage) -> None:
    result = usage_dict(usage)
    if usage is None:
        assert result == {}
    else:
        assert (result["input_tokens"], result["output_tokens"]) == (0, 0)
        assert result["input_tokens_details"]["cached_tokens"] == 0


def test_usage_as_a_plain_dict() -> None:
    assert usage_dict({"prompt_tokens": 5, "completion_tokens": 2})["input_tokens"] == 5


# ------------------------------------------------------------------ thinking and JSON


def test_strip_think() -> None:
    assert strip_think("<think>hmm</think>\nRéponse") == "Réponse"
    assert strip_think("a <think>x</think>b<think>y</think>c") == "a bc"
    assert strip_think("<think>never closed") == ""
    assert strip_think("reasoning</think>\n\nRéponse") == "Réponse"
    assert strip_think("Rien à retirer ") == "Rien à retirer "


def feed_all(chunks: list[str]) -> str:
    stripper = ThinkStripper()
    return "".join(stripper.feed(c) for c in chunks) + stripper.flush()


def test_a_think_block_is_stripped_across_chunk_boundaries() -> None:
    assert feed_all(["Bon", "jour <thi", "nk>hmm</th", "ink>\n\nsuite"]) == "Bonjour suite"
    assert feed_all(["<think>", "x", "</think>", "\n", "ok"]) == "ok"
    assert feed_all(["a<", "b"]) == "a<b"  # a bracket that is not a tag comes through
    assert feed_all(["fin <thi"]) == "fin <thi"  # held back, then flushed when the stream ends
    assert feed_all(["<think>cut off"]) == ""
    assert feed_all(["texte", " normal"]) == "texte normal"


def test_whitespace_after_a_closing_tag_is_trimmed_once() -> None:
    assert feed_all(["<think>x</think>\n\n  ", "Salut\n"]) == "Salut\n"


def test_extract_json() -> None:
    assert extract_json('{"a": 1}') == '{"a": 1}'
    assert extract_json('Voici :\n```json\n{"a": 1}\n```\nVoilà.') == '{"a": 1}'
    assert extract_json('<think>{x}</think>{"a": 2}') == '{"a": 2}'
    assert extract_json('Intro {"a": {"b": 3}} fin') == '{"a": {"b": 3}}'
    assert extract_json("pas de json") == "pas de json"


def test_json_instruction_carries_the_schema() -> None:
    text = json_instruction({"type": "object", "properties": {"n": {"type": "integer"}}})
    assert text.startswith("Output exactly one JSON object") and '"n":{"type":"integer"}' in text
