"""Spec 015 R2: no call to a model is made outside a usage scope. A new call site fails here until it is
attributed to a user (and is in the table below with the reason)."""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
CALLS = {"complete", "stream", "transcribe"}

# Every file outside `app/providers/` that calls a provider client, and who opens its scope.
CALL_SITES = {
    "services/tutor_service.py": "TutorService.run_turn opens the scope for the whole turn",
    "services/authoring/agent.py": "AuthoringRunner._start opens it before creating the run's task",
    "services/work_reading.py": "WorkReader.read opens it around its call",
    "services/dictation.py": "DictationService.dictate opens it around its call",
    "services/ai_test.py": "routes/admin.py test_ai opens it around the whole test",
}
# The files that open them.
OPENERS = [
    "services/tutor_service.py",
    "services/authoring/runner.py",
    "services/work_reading.py",
    "services/dictation.py",
    "api/routes/admin.py",
]


def _calling_files() -> set[str]:
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        relative = path.relative_to(APP).as_posix()
        if relative.startswith("providers/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CALLS:
                # Only calls on a provider client: `x.complete(`, `…llm.stream(`, `…transcriber.transcribe(`.
                target = ast.unparse(node.func.value)
                if any(word in target for word in ("llm", "tutor", "authoring", "transcription", "transcriber", "_caller", "caller")):
                    found.add(relative)
    return found


def test_every_file_that_calls_a_provider_is_in_the_table() -> None:
    found = _calling_files()
    missing = sorted(found - set(CALL_SITES))
    assert not missing, f"{missing} call a provider client: open a usage scope for them and list them here"
    stale = sorted(set(CALL_SITES) - found)
    assert not stale, f"{stale} no longer call a provider: remove them from the table"


def test_the_scopes_are_opened_where_the_table_says() -> None:
    for relative in OPENERS:
        source = (APP / relative).read_text(encoding="utf-8")
        assert "usage_scope(" in source, f"{relative} must open a usage scope"
