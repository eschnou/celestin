"""The authoring agent (005 design 3.8, 006 design 3.6): document → transcription →
pack → curriculum.

Stateless over one run and blind to the database. A document is first read page by
page by a vision model (batches in parallel, each checked for its page markers);
the text then goes through the stages of spec 005, each validating what the model
returned and, on issues, sending them back for another attempt, up to
`authoring_max_repairs`. The pack comes back as plain Markdown; the curriculum as
strict JSON.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.domain.ai_config import AiConfig, priced
from app.domain.chapter import RunUsage, Stage, token_counts
from app.domain.content import ValidContent, validate_curriculum
from app.domain.curriculum import Curriculum
from app.domain.errors import (
    AiNotConfigured,
    ProviderOutputInvalid,
    ProviderOutputTruncated,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.messages.issues import issue_text
from app.domain.pack import ContentIssue, PackIndex, index_pack
from app.domain.subject import Subject
from app.domain.transcription import (
    MarkerCounts,
    apply_uncertain,
    count_markers,
    handwritten_numbers,
    join_batches,
    split_pages,
    validate_batch,
)
from app.providers.base import AiConfigSource, CompletionClient, CompletionResult
from app.services.authoring.schemas import CurriculumDraft, draft_to_data
from app.services.authoring.words import AGENT_WORDS
from app.services.documents import Document, PageImage
from app.services.prompts import PromptLibrary

log = logging.getLogger(__name__)

FailureCode = Literal["unstructured", "provider", "truncated", "transcription_failed", "too_long"]
OnProgress = Callable[[Stage, int | None], Awaitable[None]]  # stage, pages read so far
OnTranscribed = Callable[[str, MarkerCounts], Awaitable[None]]


class _VerifiedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    sure: bool
    line: str


class VerifyDraft(BaseModel):
    """What the handwriting check answers for one page."""

    model_config = ConfigDict(extra="forbid")

    items: list[_VerifiedLine]
# AiNotConfigured: the key was removed while the run was under way. A failure the student can retry.
PROVIDER_ERRORS = (ProviderUnavailable, ProviderRateLimited, ProviderTimeout, AiNotConfigured, TimeoutError)


@dataclass(frozen=True)
class AuthoringOutput:
    content: ValidContent
    usage: RunUsage


class AuthoringFailed(Exception):
    def __init__(self, code: FailureCode, stage: Stage, usage: RunUsage, detail: str) -> None:
        super().__init__(f"{code} at {stage}: {detail}")
        self.code = code
        self.stage = stage
        self.usage = usage
        self.detail = detail


def wrap(tag: str, text: str) -> str:
    """`text` between `<tag>` markers it cannot close itself."""
    body = re.sub(rf"</\s*{tag}\s*>", f"</ {tag}>", text, flags=re.IGNORECASE)
    return f"<{tag}>\n{body}\n</{tag}>"


def wrap_source(text: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    return AGENT_WORDS[language].material_intro + wrap("materiel", text)


_WHOLE_FENCE = re.compile(r"^(```|~~~)[\w-]*\n(.*)\n\1\s*$", re.DOTALL)
_H1_LINE = re.compile(r"^#\s")


def normalise_pack(text: str) -> str:
    """Tolerate the usual wrapping: one fence around the whole document, a sentence
    before the title, Windows line endings."""
    body = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    fenced = _WHOLE_FENCE.match(body)
    if fenced:
        body = fenced.group(2).strip()
    lines = body.split("\n")
    start = next((i for i, line in enumerate(lines) if _H1_LINE.match(line)), 0)
    return "\n".join(lines[start:]).rstrip() + "\n"


def _repair_message(what: str, issues: list[ContentIssue], language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> str:
    """The request to redo a stage, in the course's language: each reason as the model reads it
    (`issue_text`), not as the student's editor shows it. `what` is `the_document` / `the_path`
    of that language."""
    words = AGENT_WORDS[language]
    listed = "\n".join(
        words.issue_line.format(where=issue.where, message=issue_text(issue, language)) for issue in issues
    )
    again = words.document_again if what == words.the_document else words.path_again if what == words.the_path else what.lower()
    return words.repair.format(what=what, listed=listed, again=again)


def _where(issues: list[ContentIssue]) -> str:
    """Issue locations only: messages can quote the student's content, logs must not."""
    return f"{len(issues)} issue(s): " + ", ".join(sorted({i.where.split(' « ')[0] for i in issues}))


def _price(input_tokens: int, cached: int, output: int, price_in: float, price_cached: float, price_out: float) -> float:
    return (max(input_tokens - cached, 0) * price_in + cached * price_cached + output * price_out) / 1_000_000


def estimate_cost(usage: RunUsage, settings: Settings, config: AiConfig | None = None) -> float:
    """The run's cost; sets `usage.transcription_cost_usd` to the transcription share. A share is priced
    only when its role runs on OpenAI or its prices were set explicitly (spec 014 R11.2): OpenAI's
    prices are not another provider's."""
    s = settings
    names = ("price_in", "price_cached", "price_out")
    transcription = _price(
        usage.transcription_input_tokens, usage.transcription_cached_tokens, usage.transcription_output_tokens,
        s.transcription_price_in, s.transcription_price_cached, s.transcription_price_out,
    ) if priced(s, config.transcription.connection if config else None, *(f"transcription_{n}" for n in names)) else 0.0
    authoring = _price(
        usage.input_tokens - usage.transcription_input_tokens,
        usage.cached_tokens - usage.transcription_cached_tokens,
        usage.output_tokens - usage.transcription_output_tokens,
        s.authoring_price_in, s.authoring_price_cached, s.authoring_price_out,
    ) if priced(s, config.authoring.connection if config else None, *(f"authoring_{n}" for n in names)) else 0.0
    usage.transcription_cost_usd = round(transcription, 4)
    return round(transcription + authoring, 4)


def _image_part(page: PageImage, detail: str) -> dict[str, Any]:
    return {"type": "input_image", "image_url": page.data_url, "detail": detail}


class AuthoringAgent:
    def __init__(self, llm: CompletionClient, prompts: PromptLibrary, settings: Settings, ai: AiConfigSource) -> None:
        self._llm = llm
        self._prompts = prompts
        self._settings = settings
        self._ai = ai

    async def run(
        self,
        *,
        chapter_id: str,
        subject: Subject,
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
        source_text: str | None = None,
        document: Document | None = None,
        usage: RunUsage | None = None,
        log_extra: dict[str, Any] | None = None,
        on_progress: OnProgress | None = None,
        on_transcribed: OnTranscribed | None = None,
    ) -> AuthoringOutput:
        """From a text, or from a document read first. `usage` is filled as the run
        goes, so the caller keeps it when the run fails or is cancelled."""
        if (source_text is None) == (document is None):
            raise ValueError("exactly one of source_text and document")
        usage = usage if usage is not None else RunUsage()
        extra = log_extra or {}
        try:
            if document is not None:
                source_text, counts = await self._transcription_stage(document, usage, extra, on_progress, language)
                document = None  # the page images are not needed any more
                if on_transcribed is not None:
                    await on_transcribed(source_text, counts)
            assert source_text is not None
            pack, index = await self._pack_stage(subject, source_text, usage, extra, language)
            if on_progress is not None:
                await on_progress("curriculum", None)
            curriculum = await self._curriculum_stage(chapter_id, subject, pack, index, usage, extra, language)
        finally:
            usage.cost_estimate_usd = estimate_cost(usage, self._settings, self._ai.config)
        return AuthoringOutput(content=ValidContent(pack=pack, index=index, curriculum=curriculum), usage=usage)

    async def _call(
        self, stage: Stage, instructions: list[str], convo: list[dict[str, Any]], usage: RunUsage, schema: type | None
    ) -> CompletionResult:
        started = time.monotonic()
        try:
            return await self._llm.complete(
                role="authoring",
                instructions=instructions,
                input=convo,
                schema=schema,
                schema_name="parcours" if schema else None,
                max_output_tokens=self._settings.authoring_max_output_tokens,
            )
        except ProviderOutputTruncated as exc:
            raise AuthoringFailed("truncated", stage, usage, str(exc)) from exc
        except PROVIDER_ERRORS as exc:
            raise AuthoringFailed("provider", stage, usage, type(exc).__name__) from exc
        finally:
            elapsed = round((time.monotonic() - started) * 1000)
            if stage == "pack":
                usage.pack_ms += elapsed
            else:
                usage.curriculum_ms += elapsed

    @staticmethod
    def _log_stage(
        stage: Stage,
        attempt: int,
        issues: list[ContentIssue],
        result: CompletionResult | None,
        extra: dict[str, Any],
        started: float,
        pages: list[int] | None = None,
    ) -> None:
        log.info(
            "authoring_stage",
            extra={
                **extra,
                "stage": stage,
                **({"pages": pages} if pages is not None else {}),
                "attempt": attempt,
                "ms": round((time.monotonic() - started) * 1000),
                "ok": not issues,
                "issues": len(issues),
                **token_counts(result.usage if result else {}),
            },
        )

    # ------------------------------------------------------------ transcription

    async def _transcription_stage(
        self,
        document: Document,
        usage: RunUsage,
        extra: dict[str, Any],
        on_progress: OnProgress | None,
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    ) -> tuple[str, MarkerCounts]:
        s = self._settings
        started = time.monotonic()
        instructions = [self._prompts.transcribe(language)]
        size = s.transcription_batch_pages
        batches = [document.pages[i : i + size] for i in range(0, len(document.pages), size)]
        semaphore = asyncio.Semaphore(s.transcription_concurrency)
        texts: dict[int, str] = {}
        done = 0
        reported = asyncio.Lock()  # one progress write at a time, so the count never goes back

        async def one(pages: list[PageImage]) -> None:
            nonlocal done
            async with semaphore:
                texts[pages[0].number] = await self._transcribe(pages, instructions, usage, extra, language)
            done += len(pages)
            if on_progress is not None:
                async with reported:
                    await on_progress("transcription", done)

        try:
            async with asyncio.TaskGroup() as group:
                for pages in batches:
                    group.create_task(one(pages))
        except* AuthoringFailed as failures:
            raise failures.exceptions[0] from None
        text = join_batches(texts)
        verified = 0
        if s.transcription_verify_handwriting:
            text, verified = await self._verify_handwriting(text, document, semaphore, usage, extra, language)
        usage.transcription_ms += round((time.monotonic() - started) * 1000)
        if len(text) > s.chapter_text_max_chars:
            raise AuthoringFailed("too_long", "transcription", usage, f"{len(text)} characters")
        counts = count_markers(text, language)
        log.info(
            "transcription_done",
            extra={**extra, "pages": len(document.pages), "chars": len(text), "handwritten_marks": counts.handwritten,
                   "uncertain_marks": counts.uncertain, "illegible_marks": counts.illegible,
                   "verified_pages": verified, "ms": usage.transcription_ms},
        )
        return text, counts

    async def _transcribe(
        self,
        pages: list[PageImage],
        instructions: list[str],
        usage: RunUsage,
        extra: dict[str, Any],
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    ) -> str:
        """One batch, retried once; a batch cut short by the output limit is read
        again page by page."""
        numbers = [page.number for page in pages]
        words = AGENT_WORDS[language]
        content: list[dict[str, Any]] = [
            {"type": "input_text", "text": words.pages.format(first=numbers[0], last=numbers[-1])}
        ]
        for page in pages:
            label = words.page.format(number=page.number)
            if page.text_hint:
                label += words.text_hint + wrap("couche_texte", page.text_hint)
            content += [{"type": "input_text", "text": label}, _image_part(page, self._settings.transcription_detail)]
        issues: list[ContentIssue] = []
        for attempt in (1, 2):
            usage.attempts_transcription += 1
            started = time.monotonic()
            try:
                result = await self._llm.complete(
                    role="transcription",
                    instructions=instructions,
                    input=[{"role": "user", "content": content}],
                    max_output_tokens=self._settings.transcription_max_output_tokens,
                )
            except ProviderOutputTruncated as exc:
                if len(pages) > 1:
                    parts = [await self._transcribe([page], instructions, usage, extra, language) for page in pages]
                    return "\n\n".join(parts)
                issues = [ContentIssue(f"page {numbers[0]}", words.truncated)]
                self._log_stage("transcription", attempt, issues, None, extra, started, pages=numbers)
                if attempt == 2:
                    raise AuthoringFailed("transcription_failed", "transcription", usage, str(exc)) from exc
                continue
            except PROVIDER_ERRORS as exc:
                raise AuthoringFailed("provider", "transcription", usage, type(exc).__name__) from exc
            usage.add_transcription_tokens(result.usage)
            text, issues = validate_batch(result.text, numbers, language)
            self._log_stage("transcription", attempt, issues, result, extra, started, pages=numbers)
            if text is not None:
                return text
        raise AuthoringFailed("transcription_failed", "transcription", usage, _where(issues))

    async def _verify_handwriting(
        self,
        text: str,
        document: Document,
        semaphore: asyncio.Semaphore,
        usage: RunUsage,
        extra: dict[str, Any],
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    ) -> tuple[str, int]:
        """Re-read handwritten numbers read with confidence, page by page; lines the
        model now doubts are rewritten with `[incertain: …]`. Best effort: a page whose
        check fails keeps its transcription."""
        pages = split_pages(text)
        images = {page.number: page for page in document.pages}
        instructions = [self._prompts.verify(language)]
        words = AGENT_WORDS[language]

        async def check(number: int) -> None:
            candidates = handwritten_numbers(pages[number], language)
            if not candidates:
                return
            listing = "\n".join(f"{n}. {line}" for n, (_, line) in enumerate(candidates, start=1))
            content = [
                {"type": "input_text", "text": words.reread.format(number=number) + wrap("lignes", listing)},
                _image_part(images[number], self._settings.transcription_detail),
            ]
            try:
                async with semaphore:
                    result = await self._llm.complete(
                        role="transcription",
                        instructions=instructions,
                        input=[{"role": "user", "content": content}],
                        schema=VerifyDraft,
                        schema_name="relecture",
                        max_output_tokens=self._settings.transcription_max_output_tokens,
                    )
            except (ProviderOutputTruncated, ProviderOutputInvalid, *PROVIDER_ERRORS) as exc:
                log.warning("handwriting_check_skipped", extra={**extra, "page": number, "error": type(exc).__name__})
                return
            usage.add_transcription_tokens(result.usage)
            try:
                draft = VerifyDraft.model_validate(result.data or {"items": []})
            except ValueError:
                log.warning("handwriting_check_skipped", extra={**extra, "page": number, "error": "invalid"})
                return
            rewrites = [
                (candidates[item.n - 1][0], candidates[item.n - 1][1], item.line)
                for item in draft.items
                if not item.sure and 1 <= item.n <= len(candidates)
            ]
            pages[number] = apply_uncertain(pages[number], rewrites, language)
            checked.append(number)

        checked: list[int] = []
        await asyncio.gather(*(check(number) for number in sorted(pages)))
        return join_batches(pages), len(checked)

    # --------------------------------------------------------------- authoring

    async def _pack_stage(
        self,
        subject: Subject,
        source_text: str,
        usage: RunUsage,
        extra: dict[str, Any],
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    ) -> tuple[str, PackIndex]:
        template = self._prompts.template(subject, language)
        alternatives = self._prompts.other_templates(subject, language)
        words = AGENT_WORDS[language]
        # Static per subject, first, so every run of the subject shares the cached prefix.
        instructions = [self._prompts.authoring_pack(language), template.text, self._prompts.subject(subject, language)]
        convo: list[dict[str, Any]] = [{"role": "user", "content": wrap_source(source_text, language)}]
        issues: list[ContentIssue] = []
        for attempt in range(1, self._settings.authoring_max_repairs + 2):
            usage.attempts_pack = attempt
            started = time.monotonic()
            result = await self._call("pack", instructions, convo, usage, None)
            usage.add_tokens(result.usage)
            pack = normalise_pack(result.text)
            index, issues = index_pack(pack, template, self._settings.pack_max_chars, alternatives)
            self._log_stage("pack", attempt, issues, result, extra, started)
            if index is not None:
                return pack, index
            convo += [
                {"role": "assistant", "content": pack},
                {"role": "user", "content": _repair_message(words.the_document, issues, language)},
            ]
        raise AuthoringFailed("unstructured", "pack", usage, _where(issues))

    async def _curriculum_stage(
        self,
        chapter_id: str,
        subject: Subject,
        pack: str,
        index: PackIndex,
        usage: RunUsage,
        extra: dict[str, Any],
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    ) -> Curriculum:
        words = AGENT_WORDS[language]
        instructions = [self._prompts.authoring_curriculum(language), self._prompts.subject(subject, language)]
        convo: list[dict[str, Any]] = [
            {"role": "user", "content": words.chapter_intro + wrap("chapitre", pack)}
        ]
        issues: list[ContentIssue] = []
        for attempt in range(1, self._settings.authoring_max_repairs + 2):
            usage.attempts_curriculum = attempt
            started = time.monotonic()
            try:
                result: CompletionResult | None = await self._call(
                    "curriculum", instructions, convo, usage, CurriculumDraft
                )
            except ProviderOutputInvalid:
                result = None
            if result is None or result.data is None:
                curriculum, issues = None, [ContentIssue("parcours", words.unreadable_json)]
            else:
                usage.add_tokens(result.usage)
                curriculum, issues = validate_curriculum(draft_to_data(result.data, chapter_id), index, language)
            self._log_stage("curriculum", attempt, issues, result, extra, started)
            if curriculum is not None:
                return curriculum
            if result is not None:
                convo.append({"role": "assistant", "content": result.text})
            convo.append({"role": "user", "content": _repair_message(words.the_path, issues, language)})
        raise AuthoringFailed("unstructured", "curriculum", usage, _where(issues))
