"""The authoring runner (005 design 3.9): limits, background tasks, adoption.

One instance per process. Limits come from the runs table, so they survive a
restart; the lock makes check-then-insert atomic within the process, and the
semaphore bounds provider load across students. A run's outcome is written in one
transaction; a run cut short by a restart is failed at the next startup.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db.base import utcnow
from app.db.repositories import Repositories
from app.domain.chapter import ChapterRecord, CourseRecord, OwnedChapter, RunUsage, Stage
from app.domain.errors import (
    AiNotConfigured,
    AuthoringBusy,
    AuthoringQuota,
    AuthoringRunning,
    CallDiagnostics,
    ChapterLimit,
    DocumentNeeded,
    NothingToRetry,
)
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage
from app.domain.subject import Subject
from app.domain.transcription import MarkerCounts
from app.domain.usage import UsageScope, usage_scope
from app.domain.user import User
from app.providers.base import AiConfigSource
from app.services.authoring.agent import AuthoringAgent, AuthoringFailed, AuthoringOutput
from app.services.authoring.progress import LiveProgress
from app.services.documents import Document

log = logging.getLogger(__name__)

QUOTA_WINDOW = timedelta(hours=24)


class AuthoringRunner:
    def __init__(self, agent: AuthoringAgent, repos: Repositories, settings: Settings, ai: AiConfigSource) -> None:
        self._agent = agent
        self._repos = repos
        self._settings = settings
        self._ai = ai
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.authoring_max_concurrent)
        self._tasks: set[asyncio.Task[None]] = set()

    def _model(self) -> str:
        """The authoring model in force when a run starts (it can change between runs, spec 014 R2.4)."""
        config = self._ai.config
        if config is None:
            raise AiNotConfigured()
        return config.authoring.model

    # ------------------------------------------------------------------ starts

    async def start_document(
        self, user: User, course: CourseRecord, chapter: ChapterRecord | None, document: Document
    ) -> ChapterRecord:
        """A new chapter from a document, or a chapter's document replaced: the pages
        are read first, then the chapter is prepared from their transcription."""
        # A replaced document keeps the chapter's source until its transcription lands.
        if chapter is None:
            return await self._start(user, course, None, "", "create", document)
        return await self._start(user, course, chapter, None, "replace", document)

    async def check_can_start(self, user: User, course: CourseRecord, chapter: ChapterRecord | None) -> None:
        """The refusals `start_document` would give, checked before the document is
        rendered, so a refused upload does not hold a shared worker. `_start` checks
        again under its lock."""
        if chapter is not None and chapter.authoring_state == "generating":
            raise AuthoringRunning()

        def check() -> None:
            self._check_limits(user)
            if chapter is None and self._repos.chapters.count_in_course(course.id) >= self._settings.max_chapters_per_course:
                raise ChapterLimit()

        await asyncio.to_thread(check)

    async def start_source_edit(self, user: User, owned: OwnedChapter, source_text: str) -> ChapterRecord:
        return await self._start(user, owned.course, owned.chapter, source_text, "source_edit")

    async def start_retry(self, user: User, owned: OwnedChapter) -> ChapterRecord:
        """Again from the stored source. A document is not kept: a run that failed
        before its transcription was stored needs the document again (006 R3.3)."""
        if owned.chapter.authoring_state == "generating":
            raise AuthoringRunning()
        if owned.chapter.authoring_state != "failed":
            raise NothingToRetry()
        if owned.chapter.needs_document:
            raise DocumentNeeded()
        return await self._start(user, owned.course, owned.chapter, None, "retry")

    async def _start(
        self,
        user: User,
        course: CourseRecord,
        chapter: ChapterRecord | None,
        source_text: str | None,
        trigger: str,
        document: Document | None = None,
    ) -> ChapterRecord:
        async with self._lock:
            if chapter is not None and chapter.authoring_state == "generating":
                self._refused(user, "running")
                raise AuthoringRunning()
            record, run_id = await asyncio.to_thread(
                self._begin, user, course, chapter.id if chapter else None, source_text, trigger,
                len(document.pages) if document else 0,
            )
        extra = {"run_id": run_id, "user_id": user.id, "course_id": course.id, "chapter_id": record.id}
        if document is None:
            text = source_text if source_text is not None else record.source_text or ""
            size: dict[str, object] = {"source_chars": len(text)}
        else:
            text = None
            size = {"pages": len(document.pages), "document_kind": document.kind}
        log.info(
            "authoring_started",
            extra={**extra, "trigger": trigger, "subject": course.subject, "language": course.language, **size,
                   "model": self._model()},
        )
        # The usage ledger (spec 015): a task copies the context it is created in, so every stage, repair, retry and
        # page of this run, in the background after the request has returned, is attributed to its owner.
        with usage_scope(UsageScope(user.id, "authoring", course.id, record.id, run_id)):
            task = asyncio.create_task(
                self._execute(run_id, record.id, course.subject, text, document, extra, course.language)
            )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return record

    def _begin(
        self,
        user: User,
        course: CourseRecord,
        chapter_id: str | None,
        source_text: str | None,
        trigger: str,
        page_count: int,
    ) -> tuple[ChapterRecord, str]:
        """`page_count` 0 means a text source."""
        """Limits, then the chapter and run rows: one thread hop."""
        self._check_limits(user)
        return self._repos.chapters.begin_authoring(
            user_id=user.id,
            course_id=course.id,
            chapter_id=chapter_id,
            source_text=source_text,
            trigger=trigger,
            model=self._model(),
            max_chapters=self._settings.max_chapters_per_course,
            source_kind="document" if page_count else "text",
            page_count=page_count,
        )

    def _check_limits(self, user: User) -> None:
        s = self._settings
        if self._repos.runs.running_for_user(user.id) >= s.authoring_concurrent_per_student:
            self._refused(user, "busy")
            raise AuthoringBusy(s.authoring_concurrent_per_student)
        count, oldest = self._repos.runs.started_since(user.id, utcnow() - QUOTA_WINDOW)
        if count >= s.authoring_runs_per_day and oldest is not None:
            self._refused(user, "quota")
            retry_at = (oldest + QUOTA_WINDOW).astimezone(ZoneInfo(s.timezone))
            raise AuthoringQuota(retry_at.strftime("%H:%M"))

    @staticmethod
    def _refused(user: User, reason: str) -> None:
        log.info("authoring_refused", extra={"user_id": user.id, "reason": reason})

    # --------------------------------------------------------------- execution

    async def _execute(
        self,
        run_id: str,
        chapter_id: str,
        subject: Subject,
        source_text: str | None,
        document: Document | None,
        extra: dict,
        language: CourseLanguage = DEFAULT_COURSE_LANGUAGE,
    ) -> None:
        usage = RunUsage()
        chapters = self._repos.chapters
        page_count = len(document.pages) if document else 0

        async def on_progress(stage: Stage, pages_done: int | None) -> None:
            await asyncio.to_thread(chapters.set_progress, chapter_id, stage, pages_done)

        async def on_transcribed(text: str, counts: MarkerCounts) -> None:
            await asyncio.to_thread(
                chapters.store_transcription, chapter_id, run_id, text, page_count,
                (counts.handwritten, counts.uncertain, counts.illegible),
            )

        live = LiveProgress(chapters, chapter_id, self._settings, extra)
        run = self._agent.run(
            chapter_id=chapter_id, subject=subject, language=language, source_text=source_text,
            document=document,
            usage=usage, log_extra=extra, on_progress=on_progress, on_transcribed=on_transcribed, progress=live,
        )
        del document  # the agent drops the page images once they are read
        try:
            async with self._semaphore:
                async with asyncio.timeout(self._settings.authoring_timeout_s):
                    output = await run
            await asyncio.to_thread(self._adopt, run_id, chapter_id, output, extra)
        except AuthoringFailed as exc:
            self._fail(run_id, chapter_id, exc.code, usage, extra, exc.detail, diagnostics=exc.diagnostics)
        except TimeoutError:
            self._fail(run_id, chapter_id, "timeout", usage, extra, "run timeout", reason="run_ceiling")
        except asyncio.CancelledError:
            # Written synchronously: a cancelled task must not await again.
            self._fail(run_id, chapter_id, "interrupted", usage, extra, "cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 - every failure leaves a state
            # The type only: a database error's message carries the bound values,
            # which here are the student's content (005 NFR 4.3.4).
            log.error("authoring_internal_error", extra={**extra, "error": type(exc).__name__})
            self._fail(run_id, chapter_id, "internal", usage, extra, type(exc).__name__)
        finally:
            live.close()
            run.close()  # never awaited when the task is cancelled while waiting for the semaphore

    def _adopt(self, run_id: str, chapter_id: str, output: AuthoringOutput, extra: dict) -> None:
        adopted = self._repos.chapters.adopt_authored(chapter_id, run_id, output.content, output.usage)
        if not adopted:
            log.info("authoring_discarded", extra=extra)
            return
        usage = output.usage
        log.info(
            "authoring_succeeded",
            extra={
                **extra,
                "sections": len(output.content.curriculum.sections),
                "exercises": len(output.content.index.exercises),
                "points_a_verifier": output.content.index.to_verify,
                "total_ms": usage.transcription_ms + usage.pack_ms + usage.curriculum_ms,
                **_usage_log(usage),
            },
        )

    def _fail(
        self,
        run_id: str,
        chapter_id: str,
        code: str,
        usage: RunUsage,
        extra: dict,
        detail: str,
        *,
        diagnostics: CallDiagnostics | None = None,
        reason: str | None = None,
    ) -> None:
        stage = None
        try:
            stage = self._repos.chapters.finish_failed(chapter_id, run_id, code, usage)
        except Exception as exc:  # noqa: BLE001 - the orphan sweep at startup is the fallback
            log.error("authoring_fail_not_stored", extra={**extra, "error": type(exc).__name__})
        log.warning(
            "authoring_failed",
            extra={
                **extra, "code": code, "stage": stage, "detail": detail[:300],
                **_diagnostics_log(diagnostics, reason), **_usage_log(usage),
            },
        )

    # -------------------------------------------------------------- lifecycle

    def active_count(self) -> int:
        return len(self._tasks)

    def fail_orphans(self) -> int:
        count = self._repos.runs.fail_orphans()
        if count:
            log.warning("authoring_orphans_failed", extra={"count": count})
        return count

    async def wait_idle(self) -> None:
        """Tests: let every started run finish."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
            # A run that has just finished stays in the set until its done callback
            # runs, and a gather over finished tasks returns without yielding: yield,
            # or this loop spins before the callback can remove it.
            await asyncio.sleep(0)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)


def _diagnostics_log(diagnostics: CallDiagnostics | None, reason: str | None) -> dict[str, object]:
    """Why the run failed, from the provider call that failed (spec 016 R6.4): a class name, a fixed reason and
    numbers. Never the exception's message."""
    if diagnostics is None:
        return {"reason": reason} if reason else {}
    return {
        "error_class": diagnostics.error_class,
        "reason": diagnostics.reason,
        "status_code": diagnostics.status_code,
        "idle_ms": diagnostics.idle_ms,
        "received_chars": diagnostics.received_chars,
        "provider_request_id": diagnostics.request_id,
    }


def _usage_log(usage: RunUsage) -> dict[str, object]:
    return {
        "attempts_transcription": usage.attempts_transcription,
        "attempts_pack": usage.attempts_pack,
        "attempts_curriculum": usage.attempts_curriculum,
        "transcription_ms": usage.transcription_ms,
        "pack_ms": usage.pack_ms,
        "curriculum_ms": usage.curriculum_ms,
        "input_tokens": usage.input_tokens,
        "cached_tokens": usage.cached_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cost_estimate_usd": usage.cost_estimate_usd,
    }
