from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {
    APP / "providers" / "_client.py",  # spec 014: the one place a client is built
    APP / "providers" / "openai_responses.py",
    APP / "providers" / "openai_chat.py",  # spec 014: Chat Completions
    APP / "providers" / "openai_realtime.py",
    APP / "providers" / "openai_probe.py",  # spec 013: asks whether a connection works
    APP / "providers" / "_errors.py",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize(
    "path", sorted(p for p in APP.rglob("*.py") if p not in ALLOWED), ids=lambda p: str(p.name)
)
def test_only_the_adapter_imports_openai(path: Path) -> None:
    """Design 3.3: nothing above app/providers/ may import openai."""
    assert "openai" not in _imports(path), f"{path.relative_to(APP)} imports openai"


def test_message_fr_is_gone() -> None:
    """Spec 010 §4.2: an error renders through the catalog, in the request's language.
    A `message_fr` attribute would be French text kept outside it."""
    offenders = [
        str(p.relative_to(APP)) for p in APP.rglob("*.py") if "message_fr" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], offenders
