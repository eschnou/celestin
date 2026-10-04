"""Every script imports.

The scripts that call the real API never run in `pytest`, so a refactor that
renames what they import breaks them silently until someone pays to run one
(`authoring_eval` sat broken on `main` that way, 008 D9). Importing them is free.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

SCRIPTS = sorted(p.stem for p in (Path(__file__).resolve().parents[2] / "scripts").glob("*.py") if p.stem != "__init__")


@pytest.mark.parametrize("name", SCRIPTS)
def test_script_imports(name: str) -> None:
    importlib.import_module(f"scripts.{name}")
