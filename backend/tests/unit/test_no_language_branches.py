"""Spec 017 §4.3: adding a language is rows and files, never a branch.

A comparison of a language or a locale with a literal (`language == "en"`) is a branch a third language would
silently take the wrong side of. This scans the application and the scripts for them; what a language *is*
goes in a `by_language` table, what the baseline is goes through `DEFAULT_COURSE_LANGUAGE`/`DEFAULT_LOCALE`.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
CODES = {"fr", "en", "nl"}
NAMES = ("language", "locale")

# file (relative to backend/) -> why a comparison is right there.
ALLOWED = {
    "app/domain/messages/__init__.py": "French counts 0 and 1 as singular (plural_category)",
    "app/domain/locale.py": "the locale module itself",
    "app/domain/language.py": "the language module itself",
}


def _named(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def branches(path: Path) -> list[int]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Compare):
            continue
        sides = [node.left, *node.comparators]
        names = [_named(side) for side in sides]
        literals = [side.value for side in sides if isinstance(side, ast.Constant) and side.value in CODES]
        if literals and any(name and any(word in name.lower() for word in NAMES) for name in names):
            found.append(node.lineno)
    return found


def test_no_code_branches_on_a_language_literal() -> None:
    files = [*sorted((BACKEND / "app").rglob("*.py")), *sorted((BACKEND / "scripts").rglob("*.py"))]
    offenders = [
        f"{path.relative_to(BACKEND)}:{line}"
        for path in files
        if str(path.relative_to(BACKEND)) not in ALLOWED
        for line in branches(path)
    ]
    assert not offenders, "branch on a language literal (use a by_language table): " + ", ".join(offenders)


def test_the_scan_finds_a_branch(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text('def f(language):\n    return 1 if language == "en" else 2\n', encoding="utf-8")
    assert branches(sample) == [2]
    sample.write_text("def f(language):\n    return language == DEFAULT\n", encoding="utf-8")
    assert branches(sample) == []
