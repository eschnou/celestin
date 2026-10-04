"""How Célestin works on a chapter (007 design 3.1).

`parcours` follows the chapter's locked path with the section tools; `discussion`
is a free conversation about the same chapter, with the board and no path tools.
A third mode (révision) is a value here, a pair of prompt files and a row in the
tool table — never a second turn loop.
"""

from __future__ import annotations

from typing import Literal, get_args

Mode = Literal["parcours", "discussion"]

MODES: tuple[Mode, ...] = get_args(Mode)

DEFAULT_MODE: Mode = "parcours"
