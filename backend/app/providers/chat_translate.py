"""Pure translation between the application's Responses-shaped items and Chat Completions (spec 014 §3.5).

No SDK import: everything here is a function of dicts and strings, so it is tested without a network. The
adapters (`openai_responses.py`, `openai_chat.py`) call it; nothing above `app/providers/` does.
"""

from __future__ import annotations

import json
import re
from typing import Any

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```\s*$", re.DOTALL)


# ------------------------------------------------------------------ reasoning text and JSON


def strip_think(text: str) -> str:
    """Remove `<think>…</think>` blocks (a reasoning model's visible thinking). An unclosed block drops
    the rest; a lone closing tag drops everything before it (templates that open the block themselves)."""
    out = _THINK.sub("", text)
    if THINK_OPEN in out:
        out = out.split(THINK_OPEN, 1)[0]
    if THINK_CLOSE in out:
        out = out.split(THINK_CLOSE, 1)[1]
    return out.strip() if out != text else out


class ThinkStripper:
    """The streaming form of `strip_think`: feed chunks, get the visible text. A tag split across chunks
    is held back until it is known to be one."""

    def __init__(self) -> None:
        self._inside = False
        self._carry = ""
        self._trim = False  # drop the whitespace a model leaves after a closing tag

    def feed(self, chunk: str) -> str:
        text, self._carry, out = self._carry + chunk, "", []
        while text:
            tag = THINK_CLOSE if self._inside else THINK_OPEN
            at = text.find(tag)
            if at >= 0:
                if not self._inside:
                    out.append(text[:at])
                else:
                    self._trim = True
                text = text[at + len(tag):]
                self._inside = not self._inside
                continue
            keep = next((n for n in range(min(len(tag) - 1, len(text)), 0, -1) if tag.startswith(text[-n:])), 0)
            if not self._inside:
                out.append(text[: len(text) - keep])
            self._carry, text = text[len(text) - keep:], ""
        visible = "".join(out)
        if self._trim and visible:
            visible, self._trim = visible.lstrip(), visible.strip() == ""
        return visible

    def flush(self) -> str:
        rest, self._carry = ("" if self._inside else self._carry), ""
        return rest


def extract_json(text: str) -> str:
    """The JSON object in a model's answer: thinking, a code fence and prose around it removed."""
    body = strip_think(text).strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    return body[start : end + 1] if 0 <= start < end else body


def json_instruction(schema: dict[str, Any]) -> str:
    """What a model that cannot be constrained to a schema is told instead (structured mode `json`).
    Language-neutral on purpose: it is a format, not teaching."""
    return (
        "Output exactly one JSON object and nothing else. It must validate against this JSON Schema:\n"
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    )


# ------------------------------------------------------------------ items → chat messages

_TEXT_PARTS = ("input_text", "output_text", "text")


def _texts(content: Any) -> str:
    """The text of a message's content: a string, or the text parts of a list joined."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n\n".join(
        str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("type") in _TEXT_PARTS
    )


def _user_content(content: Any) -> str | list[dict[str, Any]]:
    """A user message's content: a plain string, or parts when an image comes with the text."""
    if not isinstance(content, list) or not any(
        isinstance(p, dict) and p.get("type") == "input_image" for p in content
    ):
        return _texts(content)
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") in _TEXT_PARTS:
            parts.append({"type": "text", "text": str(part.get("text", ""))})
        elif part.get("type") == "input_image":
            image: dict[str, Any] = {"url": part.get("image_url", "")}
            if part.get("detail"):
                image["detail"] = part["detail"]
            parts.append({"type": "image_url", "image_url": image})
    return parts


def to_messages(input: list[dict[str, Any]], system: str | None = None) -> list[dict[str, Any]]:
    """The application's Responses-shaped items as Chat Completions messages.

    The first `developer` (or `system`) message becomes the one `system` message, at the head, and any
    later one a `user` message: the chat templates of open models know a single system message, and the
    tutor's opening turn is the prompt and the path state, with no learner message at all. `system` is a
    text that goes first (the instructions of a one-shot call). A `function_call` becomes an assistant
    message with `tool_calls` (merged into a directly preceding assistant text, and with the calls that
    follow it), a `function_call_output` a `tool` message.
    """
    messages: list[dict[str, Any]] = []
    has_system = system is not None
    if system is not None:
        messages.append({"role": "system", "content": system})
    for item in input:
        kind = item.get("type")
        role = item.get("role")
        if kind == "function_call":
            call = {
                "id": str(item.get("call_id", "")),
                "type": "function",
                "function": {"name": str(item.get("name", "")), "arguments": str(item.get("arguments", "") or "{}")},
            }
            last = messages[-1] if messages else None
            if last is not None and last["role"] == "assistant" and "tool_calls" in last:
                last["tool_calls"].append(call)  # a call straight after another: one assistant message
            elif last is not None and last["role"] == "assistant":
                last["tool_calls"] = [call]  # the text the model said before calling
            else:
                messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        elif kind == "function_call_output":
            messages.append(
                {"role": "tool", "tool_call_id": str(item.get("call_id", "")), "content": str(item.get("output", ""))}
            )
        elif role in ("developer", "system"):
            text = _texts(item.get("content"))
            if not has_system:
                messages.insert(0, {"role": "system", "content": text})
                has_system = True
            else:
                messages.append({"role": "user", "content": text})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": _texts(item.get("content"))})
        elif role == "user":
            messages.append({"role": "user", "content": _user_content(item.get("content"))})
    return messages


def to_tools(tools: list[dict[str, Any]], *, openai: bool) -> list[dict[str, Any]]:
    """Responses tool declarations as Chat Completions ones. `strict` only for OpenAI, as in the Responses
    adapter: Pydantic validates the arguments either way."""
    out = []
    for tool in tools:
        function: dict[str, Any] = {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters", {"type": "object"}),
        }
        if openai and "strict" in tool:
            function["strict"] = tool["strict"]
        out.append({"type": "function", "function": function})
    return out


def usage_dict(usage: Any) -> dict[str, Any]:
    """Chat usage in the Responses shape the rest of the application reads; absent fields count as zero."""
    if usage is None:
        return {}

    def get(obj: Any, name: str) -> Any:
        return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)

    prompt, completion = get(usage, "prompt_tokens"), get(usage, "completion_tokens")
    cached = get(get(usage, "prompt_tokens_details"), "cached_tokens")
    reasoning = get(get(usage, "completion_tokens_details"), "reasoning_tokens")
    return {
        "input_tokens": int(prompt or 0),
        "output_tokens": int(completion or 0),
        "input_tokens_details": {"cached_tokens": int(cached or 0)},
        "output_tokens_details": {"reasoning_tokens": int(reasoning or 0)},
    }
