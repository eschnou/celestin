"""Spec 010 R4.3, R5.7, §4.7 and spec 011 R2.3/R2.6: the model reads the course's language,
never the interface's.

Two kinds of proof: a structural one (the modules that build the model's input do not
import the message catalog, nor read the account's `locale`) and a behavioural one (the same
scripted turn, for a French and an English account on the same course, hands the provider
byte-identical input; a French course and an English one hand it different input, each
equal to its own pinned rendering).
"""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.providers.base import Completed, TextDelta
from tests.conftest import CARD
from tests.conftest import tool_call as call
from tests.fixtures.fake_llm import FakeLLM

APP = Path(__file__).resolve().parents[2] / "app"
MODEL_FACING = [
    APP / "services" / "prompts.py",
    APP / "services" / "prompt_service.py",
    APP / "services" / "curriculum_render.py",
    APP / "services" / "history.py",
    APP / "services" / "path.py",
    APP / "services" / "tutor_service.py",
    *sorted((APP / "services" / "tools").glob("*.py")),
]
FORBIDDEN = {"app.domain.messages", "app.domain.messages.fr", "app.domain.messages.en"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("path", MODEL_FACING, ids=lambda p: str(p.relative_to(APP)))
def test_the_model_path_does_not_import_the_catalog(path: Path) -> None:
    assert not _imports(path) & FORBIDDEN, f"{path.relative_to(APP)} imports the message catalog"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The state message carries the time; two runs must not straddle a minute."""
    monkeypatch.setattr(Settings, "local_now", lambda self: datetime(2026, 10, 2, 10, 30))


async def _run(make_client, locale: str, language: str = "fr") -> list:
    llm = FakeLLM(
        [
            [TextDelta("Regarde."), call("display_board", {"card": CARD}), Completed()],
            [TextDelta("Tu suis ?"), Completed()],
        ]
    )
    client, _ = make_client(llm, email=f"{locale}-{language}@example.be", locale=locale, language=language)
    async with client:
        lesson = {"course_id": client.course_id, "chapter_id": client.chapter_id}  # type: ignore[attr-defined]
        r = await client.post("/api/chat", json={**lesson, "history": []})
        assert r.status_code == 200
    return llm.calls


async def test_the_provider_gets_the_same_input_whatever_the_interface_language(make_client) -> None:
    french = await _run(make_client, "fr")
    english = await _run(make_client, "en")
    assert len(french) == len(english) == 2  # the tool round and the closing one
    # Same developer message, same declarations, same tool output, round by round. (The
    # chapter ids differ per account, so compare what the model reads, not the ids.)
    assert json.dumps(french, ensure_ascii=False, sort_keys=True) == json.dumps(
        english, ensure_ascii=False, sort_keys=True
    )


def test_the_tool_declarations_take_the_course_language_and_not_the_interface_one() -> None:
    import inspect

    from app.services.tools import registry

    assert registry.declarations("parcours", "en") is registry.declarations("parcours", "en")
    for function in (registry.declarations, registry.realtime_declarations):
        parameters = inspect.signature(function).parameters
        assert "locale" not in parameters and "language" in parameters


# The only places on the model path that may name the account's `locale`: the context that
# carries it for the events it emits, and the call that renders those events.
LOCALE_HOLDERS = {"tools/context.py"}


def _mentions_locale(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "locale":
            lines.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id in {"locale", "Locale", "DEFAULT_LOCALE"}:
            lines.append(node.lineno)
        elif isinstance(node, ast.arg) and node.arg == "locale":
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("path", MODEL_FACING, ids=lambda p: str(p.relative_to(APP)))
def test_the_model_path_does_not_read_the_interface_language(path: Path) -> None:
    relative = str(path.relative_to(APP / "services"))
    lines = _mentions_locale(path)
    if relative in LOCALE_HOLDERS:
        return
    if relative == "tutor_service.py":
        # `event_of(outcome, ctx.locale)`: the student-facing marker, never the model's input.
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = {
            arg.lineno
            for call in ast.walk(tree)
            if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "event_of"
            for arg in call.args
            if isinstance(arg, ast.Attribute) and arg.attr == "locale"
        }
        assert set(lines) == allowed, f"{relative} reads the interface language outside event_of: {lines}"
        return
    assert not lines, f"{relative} names the interface language on lines {lines}"


def test_the_turn_context_carries_the_course_language_beside_the_interface_one() -> None:
    from app.services.tools.context import TurnContext
    from tests.fixtures.curricula import curriculum

    ctx = TurnContext.from_progress(curriculum(), [], None, locale="en", language="fr")
    assert (ctx.locale, ctx.language) == ("en", "fr")


async def test_the_provider_gets_the_same_input_whatever_the_interface_language_of_an_english_course(
    make_client
) -> None:
    french = await _run(make_client, "fr", language="en")
    english = await _run(make_client, "en", language="en")
    assert json.dumps(french, ensure_ascii=False, sort_keys=True) == json.dumps(
        english, ensure_ascii=False, sort_keys=True
    )


def _developer_text(calls: list) -> str:
    return calls[0]["input"][0]["content"][0]["text"]


async def test_a_french_course_and_an_english_course_hand_the_provider_different_input(
    make_client
) -> None:
    import hashlib

    french = await _run(make_client, "fr", language="fr")
    english = await _run(make_client, "fr", language="en")  # a French interface on an English course
    assert json.dumps(french, ensure_ascii=False, sort_keys=True) != json.dumps(
        english, ensure_ascii=False, sort_keys=True
    )
    fixtures = Path(__file__).parents[1] / "fixtures" / "render"
    sha = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()  # noqa: E731
    assert sha(_developer_text(french)) == (fixtures / "system_text_sha.txt").read_text().strip()
    assert sha(_developer_text(english)) == (fixtures / "system_text_sha_en.txt").read_text().strip()
    assert "Chapter path" in _developer_text(english) and "Parcours du chapitre" in _developer_text(french)
    # The state message and the tool declarations follow the course too.
    assert "Path status" in english[0]["input"][-1]["content"][0]["text"]
    assert "État du parcours" in french[0]["input"][-1]["content"][0]["text"]
