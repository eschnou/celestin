"""Spec 011 §4.1/§9.1: a third language cannot be forgotten by a table.

Every per-language table is declared with `by_language`, which raises at import unless it
covers `COURSE_LANGUAGES`. This adds a language to the list in a fresh interpreter and
imports each module that declares a table: every one of them must refuse.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).parent.parent.parent / "app"
BACKEND = APP.parent


def modules_with_tables() -> list[str]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        if path.name == "language.py":
            continue
        if "by_language(" in path.read_text(encoding="utf-8"):
            found.append(".".join(path.relative_to(BACKEND).with_suffix("").parts))
    return found


MODULES = modules_with_tables()


def test_the_tables_are_found() -> None:
    expected = {
        "app.domain.curriculum",
        "app.services.curriculum_render",
        "app.services.path",
        "app.services.history",
        "app.services.tools.context",
        "app.services.tools.pace",
        "app.services.tools.registry",
        "app.services.tools.section",
    }
    assert expected <= set(MODULES), sorted(expected - set(MODULES))


@pytest.mark.parametrize("module", MODULES)
def test_a_table_missing_a_language_fails_at_import(module: str) -> None:
    code = (
        "import app.domain.language as l\n"
        "l.COURSE_LANGUAGES = l.COURSE_LANGUAGES + ('de',)\n"
        f"import {module}\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True)
    assert result.returncode != 0 and "by_language: missing ['de']" in result.stderr, result.stderr[-400:]
