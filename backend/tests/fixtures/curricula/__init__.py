"""Curriculum fixtures shared by the unit tests."""

from __future__ import annotations

from pathlib import Path

from app.domain.curriculum import Curriculum, parse_curriculum
from app.domain.progress import Progress
from app.services.tools.context import TurnContext

HERE = Path(__file__).parent


def curriculum(name: str = "valid.yaml") -> Curriculum:
    return parse_curriculum((HERE / name).read_text(encoding="utf-8"), name)


def ctx_for(
    progress: Progress | None = None,
    name: str = "valid.yaml",
    mode: str = "parcours",
    language: str = "fr",
) -> TurnContext:
    return TurnContext(
        curriculum=curriculum(name),
        progress=progress or Progress(),
        mode=mode,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
    )


class StubPrompts:
    """Just enough of PromptLibrary for the tutor and voice services."""

    def __init__(
        self,
        tutor: str,
        subject: str = "Matière.\n",
        mode: str = "Mode.\n",
        opening: str = "Ouverture.\n",
    ) -> None:
        self._tutor = tutor
        self._subject = subject
        self._mode = mode
        self._opening = opening

    def tutor(self, language: str = "fr") -> str:
        return self._tutor

    def subject(self, subject: str, language: str = "fr") -> str:
        return self._subject

    def mode(self, mode: str, language: str = "fr") -> str:
        return self._mode

    def mode_opening(self, mode: str, language: str = "fr") -> str:
        return self._opening


def lesson_chapter(pack: str = "# Pack\n\nSuites.", name: str = "valid.yaml", language: str = "fr"):
    from app.domain.chapter import LessonChapter

    cur = curriculum(name)
    return LessonChapter(
        id=cur.id,
        subject="mathematics",
        title=cur.title,
        pack=pack,
        curriculum=cur,
        language=language,  # type: ignore[arg-type]
    )
