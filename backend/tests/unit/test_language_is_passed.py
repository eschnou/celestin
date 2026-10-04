"""Spec 011 R1.6: no code path reads a language-keyed resource without the language.

Every function below defaults to French so that a French caller reads as it always did; that
default is also how a forgotten argument would pass unnoticed. This walks the application's
(and the scripts') call sites and fails on one that does not name the language.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

# name -> (receiver names it is called on, or None for a bare name; number of positional
# arguments that includes the language). A call passes the language by position or by
# keyword `language=`.
PROMPT_ACCESSORS = {
    "tutor": 1,
    "subject": 2,
    "mode": 2,
    "mode_opening": 2,
    "template": 2,
    "other_templates": 2,
    "authoring_pack": 1,
    "authoring_curriculum": 1,
    "transcribe": 1,
    "verify": 1,
    "work": 1,
}
PROMPT_RECEIVERS = {"prompts", "_prompts", "library"}
RENDER = {"overview": 3, "brief": 4, "completion": 3, "state_message": 5, "moment": 2}
PATH = {"can_start": 4, "can_complete": 4}
REGISTRY = {"declarations": 2, "realtime_declarations": 2}
TRANSCRIPTION = {"count_markers": 2, "validate_batch": 3, "handwritten_numbers": 2, "apply_uncertain": 3}
HISTORY = {"estimate_tokens": 2, "trim": 3}
RULES = {"plot_refusal": 4, "gives_away": 2, "figure_refusal": 3, "flowchart_refusal": 3}
ISSUES = {"issue_text": 2}
DOMAIN = {"chapter_title": 2, "curriculum_from_json": 2, "check_curriculum": 2, "parse_curriculum": 3, "validate_curriculum": 3}


def _receiver(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        value = func.value
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            return value.attr
    return None


def _name(call: ast.Call) -> str | None:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None


def _passes(call: ast.Call, positional: int) -> bool:
    if any(kw.arg == "language" for kw in call.keywords):
        return True
    return len(call.args) >= positional and not any(isinstance(a, ast.Starred) for a in call.args)


def missing(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name, receiver = _name(node), _receiver(node)
        required: int | None = None
        if receiver in PROMPT_RECEIVERS and name in PROMPT_ACCESSORS:
            required = PROMPT_ACCESSORS[name]
        elif receiver in {"curriculum_render", "render"} and name in RENDER:
            required = RENDER[name]
        elif receiver == "path" and name in PATH:
            required = PATH[name]
        elif receiver == "registry" and name in REGISTRY:
            required = REGISTRY[name]
        elif name in TRANSCRIPTION and receiver is None or name in TRANSCRIPTION and receiver == "transcription":
            required = TRANSCRIPTION[name]
        elif name in DOMAIN and receiver is None:
            required = DOMAIN[name]
        elif name in HISTORY | RULES | ISSUES and receiver in {None, "history", "plots", "figures", "flowcharts"}:
            required = (HISTORY | RULES | ISSUES)[name]
        if required is not None and not _passes(node, required):
            found.append(f"{path.relative_to(BACKEND)}:{node.lineno} {receiver}.{name}")
    return found


APP_FILES = sorted([*(BACKEND / "app").rglob("*.py"), *(BACKEND / "scripts").glob("*.py")])
# The modules that define the functions, and the tests of the defaults themselves.
DEFINITIONS = {
    "app/services/prompts.py",
    "app/services/curriculum_render.py",
    "app/services/path.py",
    "app/domain/transcription.py",
    "app/domain/pack.py",
    "app/domain/curriculum.py",
    "app/domain/content.py",
    "app/services/history.py",
    "app/services/tools/plots.py",
    "app/services/tools/figures.py",
    "app/services/tools/flowcharts.py",
    "app/domain/messages/issues.py",
}


@pytest.mark.parametrize("path", APP_FILES, ids=lambda p: str(p.relative_to(BACKEND)))
def test_the_application_names_the_language(path: Path) -> None:
    if str(path.relative_to(BACKEND)) in DEFINITIONS:
        pytest.skip("defines the function")
    assert missing(path) == []


def test_the_walk_sees_a_forgotten_language(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def f(prompts, ctx):\n"
        "    prompts.tutor()\n"
        "    prompts.tutor(ctx.language)\n"
        "    prompts.subject('mathematics')\n"
        "    prompts.subject('mathematics', language='en')\n"
    )
    BACKENDLESS = missing.__globals__["BACKEND"]
    missing.__globals__["BACKEND"] = tmp_path
    try:
        assert missing(sample) == ["sample.py:2 prompts.tutor", "sample.py:4 prompts.subject"]
    finally:
        missing.__globals__["BACKEND"] = BACKENDLESS
