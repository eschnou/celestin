from __future__ import annotations

from app.domain.mode import DEFAULT_MODE, MODES


def test_the_modes_are_the_literal_members() -> None:
    assert MODES == ("parcours", "discussion")
    assert DEFAULT_MODE == "parcours"


def test_every_mode_has_a_tool_set_and_prompt_files() -> None:
    """A third mode is a value here plus two prompt files and a row in the tool
    table — never a second turn loop (007 §3.1)."""
    from pathlib import Path

    from app.config import get_settings
    from app.services.tools.registry import _MODE_TOOLS

    root = Path(get_settings().prompts_dir)
    for mode in MODES:
        assert mode in _MODE_TOOLS, mode
        assert _MODE_TOOLS[mode], mode
        assert (root / "modes" / f"{mode}.fr.md").is_file(), mode
        assert (root / "modes" / f"{mode}.opening.fr.md").is_file(), mode
