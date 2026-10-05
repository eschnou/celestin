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


@pytest.mark.parametrize("path", sorted((APP / "providers").glob("*.py")), ids=lambda p: p.name)
def test_providers_do_not_reach_the_database(path: Path) -> None:
    """Spec 015 §3.2: the recorder is handed a sink; `app/providers/` never imports `app.db` (nor `app.services`)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.level == 0}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    offenders = sorted(m for m in modules if m.startswith(("app.db", "app.services", "app.api")))
    assert offenders == [], f"{path.name} imports {offenders}"
