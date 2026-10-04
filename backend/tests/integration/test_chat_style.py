"""Spec 014 R5: a lesson turn through the real Chat Completions adapter, over a scripted SDK double.

Everything between the route and the SDK is the real thing (the hub, the adapter, the translators, the tool
layer); only the network call is replaced."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

from app.main import create_app
from tests.conftest import CARD, LESSON, _client_for, sse_frames


def chunk(content: str | None = None, *, calls: list | None = None, finish: str | None = None, usage: Any = None) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=calls)
    choices = [SimpleNamespace(delta=delta, finish_reason=finish)] if (content is not None or calls or finish) else []
    return SimpleNamespace(choices=choices, usage=usage)


def fragment(index: int, *, id: str | None = None, name: str | None = None, args: str | None = None) -> Any:
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=args))


class Raw:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    async def __aenter__(self) -> Raw:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for c in self._chunks:
                yield c

        return gen()


def chat_app(settings, db_engine, rounds: list[list[Any]], **env: Any):
    """An app whose tutor is a real chat-style client on a keyless local server, fed `rounds` of chunks."""
    local = settings.model_copy(update={
        "openai_api_key": "", "openai_base_url": "http://localhost:11434/v1", "ai_api_style": "chat",
        "openai_model": "qwen3:8b", **env,
    })
    app = create_app(local, engine=db_engine)
    requests: list[dict[str, Any]] = []
    queue = list(rounds)

    async def create(**kwargs: Any) -> Raw:
        requests.append(kwargs)
        return Raw(queue.pop(0))

    app.state.hub.current().tutor._client.chat.completions.create = create
    return app, requests


async def test_a_turn_with_a_tool_call_streams_text_and_a_board(settings, db_engine) -> None:
    rounds = [
        [
            chunk("Regarde le tableau."),
            chunk(calls=[fragment(0, id="call_1", name="display_board", args='{"card": ')]),
            chunk(calls=[fragment(0, args=json.dumps(CARD) + "}")]),
            chunk(finish="tool_calls"),
        ],
        [chunk("<think>suite</think>Tu suis ?"), chunk(finish="stop"), chunk(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2))],
    ]
    app, requests = chat_app(settings, db_engine, rounds)
    assert app.state.hub.config.tutor.connection.api_style == "chat"
    async with _client_for(app, anonymous=False) as client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    assert r.status_code == 200
    frames = sse_frames(r.text)
    assert [name for name, _ in frames] == ["turn.start", "text.delta", "board.set", "text.delta", "turn.end"]
    assert frames[1][1]["text"] == "Regarde le tableau." and frames[3][1]["text"] == "Tu suis ?"  # no visible thinking
    assert frames[2][1]["card"]["title"] == "Somme d'une SG"
    assert frames[-1][1]["usage"]["input_tokens"] == 5

    first, second = requests
    assert first["model"] == "qwen3:8b" and first["stream"] is True and "tools" in first
    assert [m["role"] for m in first["messages"]][:2] == ["system", "user"]  # the opening turn has a user message
    assert first["tools"][0]["function"]["name"] == "display_board" and "strict" not in first["tools"][0]["function"]
    # The second round carries the call and the tool's answer, as Chat Completions wants them.
    roles = [m["role"] for m in second["messages"]]
    assert roles[-2:] == ["assistant", "tool"] or roles[-3:-1] == ["assistant", "tool"]
    call = next(m for m in second["messages"] if m.get("tool_calls"))
    answer = next(m for m in second["messages"] if m["role"] == "tool")
    assert call["tool_calls"][0]["id"] == answer["tool_call_id"] == "call_1"
    assert json.loads(answer["content"])["ok"] is True


async def test_a_refused_tool_call_is_handed_back_to_the_model(settings, db_engine) -> None:
    rounds = [
        [chunk(calls=[fragment(0, id="c1", name="display_board", args='{"card": {"type": "title"}}')]), chunk(finish="tool_calls")],
        [chunk("Je corrige."), chunk(finish="stop")],
    ]
    app, requests = chat_app(settings, db_engine, rounds)
    async with _client_for(app, anonymous=False) as client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    assert r.status_code == 200 and "Je corrige." in r.text
    answer = next(m for m in requests[1]["messages"] if m["role"] == "tool")
    assert json.loads(answer["content"])["ok"] is False  # the validation error went back as the tool result


async def test_a_provider_failure_is_the_usual_error(settings, db_engine) -> None:
    app, _ = chat_app(settings, db_engine, [[chunk("début"), chunk(finish="length")]])
    async with _client_for(app, anonymous=False) as client:
        r = await client.post("/api/chat", json={**LESSON, "history": []})
    frames = sse_frames(r.text)
    assert [name for name, _ in frames][-2:] == ["error", "turn.end"]
    assert frames[-2][1]["code"] == "provider_unavailable" and frames[-1][1]["reason"] == "end"
