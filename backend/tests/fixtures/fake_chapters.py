"""A stand-in for the chapter repository's progress write, and the run attribution it logs under (spec 016)."""

from __future__ import annotations

import threading
import time

EXTRA = {"run_id": "r1", "user_id": "u1", "course_id": "c1", "chapter_id": "ch1"}


class Chapters:
    """Records what is written to a chapter's progress, can be slow, can fail."""

    def __init__(self, delay_s: float = 0.0, fail: Exception | None = None) -> None:
        self.writes: list[tuple[str, int | None]] = []
        self.delay_s, self.fail = delay_s, fail
        self._active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def set_received(self, chapter_id: str, chars: int | None) -> None:
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
        try:
            if self.delay_s:
                time.sleep(self.delay_s)
            if self.fail:
                raise self.fail
            self.writes.append((chapter_id, chars))
        finally:
            with self._lock:
                self._active -= 1
