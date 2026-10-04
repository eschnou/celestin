"""Prompt and template files (005 design 3.4, spec 011 §4.3).

Everything we write for the model lives under `backend/prompts/`: the tutor prompt
(subject-neutral), one pair of mode files per mode, one subject prompt and one pack
template per available subject, the two authoring prompts and the two transcription
prompts, each in one file per course language (`tutor.fr.md`, `tutor.en.md`). Files are
cached by modification time, so an edit is picked up on the next request; `check()` at
startup refuses to run without them.

Every accessor takes the course's language beside the subject (French by default, so a
French caller reads as before); a language no available subject is offered in has no
required file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.domain.errors import PromptInvalid, PromptUnavailable
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.mode import MODES, Mode
from app.domain.pack import PackTemplate, parse_template
from app.domain.subject import SUBJECTS, Subject, offered, offered_languages

log = logging.getLogger(__name__)


def file_name(base: str, language: CourseLanguage) -> str:
    """`tutor` and `en` give `tutor.en.md`: the one place a language becomes a file name."""
    return f"{base}.{language}.md"


def tutor_file(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name("tutor", language)


def authoring_pack_file(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name("authoring/pack", language)


def authoring_curriculum_file(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name("authoring/curriculum", language)


def transcribe_file(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name("transcription/transcribe", language)


def verify_file(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name("transcription/verify", language)


def work_file(language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name("transcription/work", language)


def mode_file(mode: Mode, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name(f"modes/{mode}", language)


def mode_opening_file(mode: Mode, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name(f"modes/{mode}.opening", language)


def subject_file(subject: Subject, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name(f"subjects/{subject}", language)


def template_file(subject: Subject, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return file_name(f"templates/{subject}.pack", language)


class _MtimeCachedFile:
    """Reads a file at most once per modification (001 NFR 4.2.3)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._mtime: float | None = None
        self._text: str | None = None

    def read(self) -> str:
        try:
            mtime = self._path.stat().st_mtime
        except OSError as exc:
            log.error("file_unavailable", extra={"path": str(self._path)})
            raise PromptUnavailable() from exc
        if self._text is None or mtime != self._mtime:
            self._text = self._path.read_text(encoding="utf-8")
            self._mtime = mtime
        return self._text


class PromptLibrary:
    def __init__(self, root: Path) -> None:
        self._root = root
        # Keyed by file name, which carries the language: `tutor.fr.md` and `tutor.en.md`
        # never share an entry.
        self._files: dict[str, _MtimeCachedFile] = {}
        self._templates: dict[tuple[Subject, CourseLanguage], tuple[str, PackTemplate]] = {}

    def _read(self, name: str) -> str:
        cached = self._files.get(name)
        if cached is None:
            cached = self._files[name] = _MtimeCachedFile(self._root / name)
        return cached.read()

    def tutor(self, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        return self._read(tutor_file(language))

    def subject(self, subject: Subject, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        return self._read(subject_file(subject, language))

    def mode(self, mode: Mode, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        """How Célestin works in this mode: substituted at `<!-- MODE -->` (007 §3.2)."""
        return self._read(mode_file(mode, language))

    def mode_opening(self, mode: Mode, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        """How a session opens in this mode: substituted at `<!-- MODE_OPENING -->`."""
        return self._read(mode_opening_file(mode, language))

    def template(self, subject: Subject, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> PackTemplate:
        """Parsed once per file change. A template broken while running is a
        `PromptUnavailable` for the request, like a missing file."""
        name = template_file(subject, language)
        text = self._read(name)
        cached = self._templates.get((subject, language))
        if cached is None or cached[0] is not text:
            try:
                cached = (text, parse_template(text, self._root / name, language))
            except PromptInvalid as exc:
                log.error("template_invalid", extra={"subject": subject, "detail": str(exc)})
                raise PromptUnavailable() from exc
            self._templates[(subject, language)] = cached
        return cached[1]

    def other_templates(self, subject: Subject, language: CourseLanguage) -> list[PackTemplate]:
        """The subject's templates in the other languages it is offered in: what a pack
        written for the wrong language is recognised by (spec 011 R4.4)."""
        return [self.template(subject, other) for other in SUBJECTS[subject].languages if other != language]

    def authoring_pack(self, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        return self._read(authoring_pack_file(language))

    def authoring_curriculum(self, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        return self._read(authoring_curriculum_file(language))

    def transcribe(self, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        return self._read(transcribe_file(language))

    def verify(self, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        return self._read(verify_file(language))

    def work(self, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
        return self._read(work_file(language))

    def required(self) -> list[str]:
        """The files of every language some available subject is offered in, and the
        subject and template files of every offered (subject, language)."""
        names: list[str] = []
        for language in offered_languages():
            names.append(tutor_file(language))
            for mode in MODES:
                names += [mode_file(mode, language), mode_opening_file(mode, language)]
        names += [
            name
            for subject, language in offered()
            for name in (subject_file(subject, language), template_file(subject, language))
        ]
        for language in offered_languages():
            names += [
                authoring_pack_file(language),
                authoring_curriculum_file(language),
                transcribe_file(language),
                verify_file(language),
                work_file(language),
            ]
        return names

    def _broken(self) -> list[tuple[str, str]]:
        """(file, reason) for every required file that cannot be read or parsed,
        through the mtime cache: unchanged files cost a stat."""
        broken = []
        templates = {template_file(subject, language): language for subject, language in offered()}
        for name in self.required():
            try:
                if name in templates:
                    parse_template(self._read(name), self._root / name, templates[name])
                else:
                    self._read(name)
            except PromptUnavailable:
                broken.append((name, "fichier introuvable"))
            except PromptInvalid as exc:
                broken.append((name, str(exc)))
        return broken

    def check(self) -> None:
        """Startup: every required file loads and every template parses, or the
        process stops naming the file."""
        broken = self._broken()
        if broken:
            name, reason = broken[0]
            raise PromptInvalid(self._root / name, reason)

    def unavailable(self) -> list[str]:
        """Required files that cannot be read or parsed right now, for /health."""
        return [name for name, _ in self._broken()]

