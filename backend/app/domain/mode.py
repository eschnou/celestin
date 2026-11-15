"""How Célestin works (007 design 3.1, spec 020).

`parcours` follows the chapter's path (open since spec 019) with the section tools; `discussion`
is a free conversation about the same chapter, with the board and no path tools; `revision`
(spec 020) rehearses several chapters of one course, with the board and `record_result`, the
student's own self-assessment, and nothing that moves the path.
A mode is a value here, a pair of prompt files and a row in the tool table — never a second
turn loop.

The first two work on one chapter (`ChapterMode`): the routes that take a chapter and a mode
from the browser (voice) take one of those, so a révision can never be asked for there.
"""

from __future__ import annotations

from typing import Literal, get_args

Mode = Literal["parcours", "discussion", "revision"]
ChapterMode = Literal["parcours", "discussion"]

MODES: tuple[Mode, ...] = get_args(Mode)

DEFAULT_MODE: ChapterMode = "parcours"
