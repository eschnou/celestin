"""Repositories (004 design 3.7).

Synchronous, one short transaction per call: each method opens a session from
the factory and commits before returning. That keeps the section tools' single
write independent of any request-scoped session, so a progress commit during an
SSE stream cannot outlive its session.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, fields, replace
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import DateTime, Integer, Boolean, String, delete, exists, func, insert, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer, sessionmaker

from app.db.base import as_utc, utcnow
from app.db.models import (
    AiUsageRow,
    AppSettingRow,
    AuthoringRunRow,
    ChapterUploadRow,
    ChapterRow,
    ConversationRow,
    CourseRow,
    ProgressRow,
    SessionRow,
    UserRow,
)
from app.domain.chapter import ChapterRecord, CourseRecord, CourseWithChapters, OwnedChapter, RunUsage
from app.domain.content import ValidContent
from app.domain.errors import (
    AuthoringRunning,
    ChapterLimit,
    ConversationBusy,
    CourseLimit,
    EmailTaken,
    LastAdmin,
    SetupDone,
    StaleVersion,
)
from app.domain.locale import DEFAULT_LOCALE, Locale, is_locale
from app.domain.progress import Progress
from app.domain.usage import UsageEntry
from app.domain.user import Role, User


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class StoredUser:
    user: User
    password_hash: str


@dataclass(frozen=True)
class UserListing:
    """One row of the admin's list: the account and when it was last seen."""

    user: User
    created_at: datetime
    last_seen_at: datetime | None


@dataclass(frozen=True)
class UserCounts:
    total: int
    enabled: int
    disabled: int


@dataclass(frozen=True)
class StoredSession:
    id: str
    user_id: str
    created_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class ProgressRecord:
    progress: Progress
    updated_at: datetime


class _Repo:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory


def _user_match(query: str) -> Any:
    """The clause that finds accounts by name or address: case-insensitive, `%` and `_` literal."""
    needle = "%" + query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return func.lower(UserRow.email).like(needle, escape="\\") | func.lower(UserRow.name).like(needle, escape="\\")


def _user(row: UserRow) -> StoredUser:
    return StoredUser(
        user=User(
            id=row.id,
            email=row.email,
            name=row.name,
            role=row.role,  # type: ignore[arg-type]
            locale=row.locale if is_locale(row.locale) else DEFAULT_LOCALE,
            enabled=row.enabled,
        ),
        password_hash=row.password_hash,
    )


class UserRepository(_Repo):
    def create(
        self,
        email: str,
        name: str,
        password_hash: str,
        role: Role = "student",
        locale: Locale = DEFAULT_LOCALE,
        enabled: bool = True,
    ) -> User:
        with self._factory() as s:
            row = UserRow(
                id=new_id(),
                email=email,
                name=name,
                password_hash=password_hash,
                role=role,
                locale=locale,
                enabled=enabled,
                created_at=utcnow(),
            )
            s.add(row)
            try:
                s.commit()
            except IntegrityError:
                # Two registrations of the same address raced; the constraint won.
                s.rollback()
                raise EmailTaken() from None
            return _user(row).user

    def by_email(self, email: str) -> StoredUser | None:
        with self._factory() as s:
            row = s.scalar(select(UserRow).where(UserRow.email == email))
            return _user(row) if row else None

    def by_id(self, user_id: str) -> User | None:
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            return _user(row).user if row else None

    def any_exists(self) -> bool:
        """Whether the instance has any account at all: the end of the first-run state (spec 013)."""
        with self._factory() as s:
            return bool(s.scalar(select(exists(select(UserRow.id)))))

    def create_first_admin(self, email: str, name: str, password_hash: str, locale: Locale) -> User:
        """An enabled admin, only if there is no account yet. The check and the insert are one SQL
        statement (`INSERT … SELECT … WHERE NOT EXISTS`), so two simultaneous setups cannot both
        succeed: SQLite takes its write lock for the whole statement. `SetupDone` otherwise."""
        user_id = new_id()
        now = utcnow()
        row = select(
            literal(user_id, String).label("id"),
            literal(email, String).label("email"),
            literal(name, String).label("name"),
            literal(password_hash, String).label("password_hash"),
            literal("admin", String).label("role"),
            literal(locale, String).label("locale"),
            literal(True, Boolean).label("enabled"),
            literal(now, DateTime(timezone=True)).label("created_at"),
        ).where(~exists(select(UserRow.id)))
        with self._factory() as s:
            result = s.execute(insert(UserRow).from_select([c.key for c in row.selected_columns], row))
            s.commit()
            if result.rowcount == 0:
                raise SetupDone()
        return User(id=user_id, email=email, name=name, role="admin", locale=locale, enabled=True)

    def set_locale(self, user_id: str, locale: Locale) -> User | None:
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            if row is None:
                return None
            row.locale = locale
            s.commit()
            return _user(row).user

    def update_hash(self, user_id: str, password_hash: str) -> None:
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            if row:
                row.password_hash = password_hash
                s.commit()

    def make_admin(self, user_id: str, password_hash: str) -> None:
        """Promote an account: admin, enabled, the given password, signed out everywhere.
        The one way to get an admin (scripts/create_admin.py); no route calls it."""
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            if row is None:
                return
            row.role = "admin"
            row.enabled = True
            row.password_hash = password_hash
            s.execute(delete(SessionRow).where(SessionRow.user_id == user_id))
            s.commit()

    def stored_by_id(self, user_id: str) -> StoredUser | None:
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            return _user(row) if row else None

    def set_enabled(self, user_id: str, enabled: bool) -> User | None:
        """Enable or disable an account. Disabling also deletes its sessions, in the
        same transaction, so no signed-in browser outlives the decision. The last enabled
        admin cannot be disabled: checked in the transaction that does it, so two admins
        disabling each other cannot both succeed."""
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            if row is None:
                return None
            if not enabled and row.role == "admin" and row.enabled:
                others = s.scalar(
                    select(func.count(UserRow.id)).where(
                        UserRow.role == "admin", UserRow.enabled.is_(True), UserRow.id != user_id
                    )
                )
                if not others:
                    raise LastAdmin()
            row.enabled = enabled
            if not enabled:
                s.execute(delete(SessionRow).where(SessionRow.user_id == user_id))
            s.commit()
            return _user(row).user

    def set_hash_and_revoke(self, user_id: str, password_hash: str, *, keep_session: str | None = None) -> bool:
        """A new password hash, and every session of the account deleted (except
        `keep_session`, the one that just proved the old password)."""
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            if row is None:
                return False
            row.password_hash = password_hash
            stmt = delete(SessionRow).where(SessionRow.user_id == user_id)
            if keep_session is not None:
                stmt = stmt.where(SessionRow.id != keep_session)
            s.execute(stmt)
            s.commit()
            return True

    def mark_seen(self, user_id: str, now: datetime) -> None:
        with self._factory() as s:
            row = s.get(UserRow, user_id)
            if row:
                row.last_seen_at = now
                s.commit()

    def counts(self) -> UserCounts:
        with self._factory() as s:
            total, enabled = s.execute(
                select(func.count(UserRow.id), func.coalesce(func.sum(UserRow.enabled.cast(Integer)), 0))
            ).one()
            return UserCounts(total=total, enabled=int(enabled), disabled=total - int(enabled))

    def list_users(
        self,
        *,
        query: str = "",
        enabled: bool | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UserListing], int]:
        """A page of accounts, those waiting for an admin first, then newest first;
        and how many match in all. `query` matches the name or the address."""
        where = []
        if query.strip():
            where.append(_user_match(query))
        if enabled is not None:
            where.append(UserRow.enabled.is_(enabled))
        if user_id is not None:
            where.append(UserRow.id == user_id)
        with self._factory() as s:
            total = s.scalar(select(func.count(UserRow.id)).where(*where)) or 0
            rows = s.execute(
                select(UserRow)
                .where(*where)
                .order_by(UserRow.enabled.asc(), UserRow.created_at.desc(), UserRow.id)
                .limit(limit)
                .offset(offset)
            ).scalars().all()
            listing = [
                UserListing(
                    user=_user(row).user,
                    created_at=as_utc(row.created_at),
                    last_seen_at=as_utc(row.last_seen_at) if row.last_seen_at else None,
                )
                for row in rows
            ]
            return listing, total


class SessionRepository(_Repo):
    def create(self, user_id: str, token_hash: str, now: datetime | None = None) -> StoredSession:
        now = now or utcnow()
        with self._factory() as s:
            row = SessionRow(
                id=new_id(), user_id=user_id, token_hash=token_hash, created_at=now, last_seen_at=now
            )
            s.add(row)
            s.commit()
            return StoredSession(row.id, row.user_id, as_utc(row.created_at), as_utc(row.last_seen_at))

    def by_token_hash(self, token_hash: str) -> StoredSession | None:
        found = self.lookup(token_hash)
        return found[0] if found else None

    def lookup(self, token_hash: str) -> tuple[StoredSession, User] | None:
        """The session and its user in one query: what every authenticated request pays."""
        with self._factory() as s:
            pair = s.execute(
                select(SessionRow, UserRow)
                .join(UserRow, UserRow.id == SessionRow.user_id)
                .where(SessionRow.token_hash == token_hash)
            ).first()
            if pair is None:
                return None
            row, user_row = pair
            return (
                StoredSession(row.id, row.user_id, as_utc(row.created_at), as_utc(row.last_seen_at)),
                _user(user_row).user,
            )

    def touch(self, session_id: str, now: datetime) -> None:
        with self._factory() as s:
            row = s.get(SessionRow, session_id)
            if row:
                row.last_seen_at = now
                s.commit()

    def delete(self, session_id: str) -> None:
        with self._factory() as s:
            s.execute(delete(SessionRow).where(SessionRow.id == session_id))
            s.commit()

    def purge_expired(self, now: datetime, idle: timedelta, absolute: timedelta) -> int:
        with self._factory() as s:
            result = s.execute(
                delete(SessionRow).where(
                    (SessionRow.last_seen_at < now - idle) | (SessionRow.created_at < now - absolute)
                )
            )
            s.commit()
            return result.rowcount or 0


def _course(row: CourseRow) -> CourseRecord:
    return CourseRecord(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        subject=row.subject,  # type: ignore[arg-type]
        created_at=as_utc(row.created_at),
        updated_at=as_utc(row.updated_at),
        language=row.language,  # type: ignore[arg-type]
    )


# The light columns: what lists and pages read. Content stays in the table.
_CHAPTER_LIGHT = (
    ChapterRow.id,
    ChapterRow.course_id,
    ChapterRow.position,
    ChapterRow.title,
    ChapterRow.section_count,
    ChapterRow.content_version,
    ChapterRow.authoring_state,
    ChapterRow.authoring_error,
    ChapterRow.created_at,
    ChapterRow.updated_at,
    ChapterRow.content_updated_at,
    ChapterRow.source_kind,
    ChapterRow.authoring_stage,
    ChapterRow.pages_done,
    ChapterRow.page_count,
)


def _chapter_light(values) -> ChapterRecord:  # noqa: ANN001 - a Row of _CHAPTER_LIGHT
    return ChapterRecord(
        id=values.id,
        course_id=values.course_id,
        position=values.position,
        title=values.title,
        section_count=values.section_count,
        content_version=values.content_version,
        authoring_state=values.authoring_state,
        authoring_error=values.authoring_error,
        created_at=as_utc(values.created_at),
        updated_at=as_utc(values.updated_at),
        content_updated_at=as_utc(values.content_updated_at) if values.content_updated_at else None,
        source_kind=values.source_kind,
        authoring_stage=values.authoring_stage,
        pages_done=values.pages_done,
        page_count=values.page_count,
    )


def _chapter_full(row: ChapterRow, source: bool = True) -> ChapterRecord:
    return replace(
        _chapter_light(row),
        source_text=row.source_text if source else None,
        pack=row.pack,
        curriculum=row.curriculum,
    )


class CourseRepository(_Repo):
    def create(
        self,
        user_id: str,
        name: str,
        subject: str,
        max_courses: int,
        course_id: str | None = None,
        language: str = "fr",
    ) -> CourseRecord:
        with self._factory() as s:
            count = s.scalar(select(func.count()).select_from(CourseRow).where(CourseRow.user_id == user_id)) or 0
            if count >= max_courses:
                raise CourseLimit()
            now = utcnow()
            row = CourseRow(
                id=course_id or new_id(),
                user_id=user_id,
                name=name,
                subject=subject,
                language=language,
                created_at=now,
                updated_at=now,
            )
            s.add(row)
            s.commit()
            return _course(row)

    def get_owned(self, user_id: str, course_id: str) -> CourseRecord | None:
        with self._factory() as s:
            row = s.scalar(select(CourseRow).where(CourseRow.id == course_id, CourseRow.user_id == user_id))
            return _course(row) if row else None

    def list_for_user(self, user_id: str, course_id: str | None = None) -> list[CourseWithChapters]:
        """Courses with their chapters' light columns, in one query."""
        with self._factory() as s:
            query = (
                select(CourseRow, *_CHAPTER_LIGHT)
                .outerjoin(ChapterRow, ChapterRow.course_id == CourseRow.id)
                .where(CourseRow.user_id == user_id)
                .order_by(CourseRow.created_at, CourseRow.id, ChapterRow.position)
            )
            if course_id is not None:
                query = query.where(CourseRow.id == course_id)
            out: dict[str, CourseWithChapters] = {}
            for row in s.execute(query):
                course_row = row[0]
                entry = out.get(course_row.id)
                if entry is None:
                    entry = out[course_row.id] = CourseWithChapters(_course(course_row), [])
                if row.id is not None:
                    entry.chapters.append(_chapter_light(row))
            return list(out.values())

    def detail(self, user_id: str, course_id: str) -> CourseWithChapters | None:
        found = self.list_for_user(user_id, course_id)
        return found[0] if found else None

    def rename(self, user_id: str, course_id: str, name: str) -> CourseRecord | None:
        with self._factory() as s:
            row = s.scalar(select(CourseRow).where(CourseRow.id == course_id, CourseRow.user_id == user_id))
            if row is None:
                return None
            row.name = name
            row.updated_at = utcnow()
            s.commit()
            return _course(row)

    def delete(self, user_id: str, course_id: str) -> bool:
        with self._factory() as s:
            result = s.execute(delete(CourseRow).where(CourseRow.id == course_id, CourseRow.user_id == user_id))
            s.commit()
            return bool(result.rowcount)

    def find_by_name(self, user_id: str, name: str) -> CourseRecord | None:
        with self._factory() as s:
            row = s.scalar(
                select(CourseRow)
                .where(CourseRow.user_id == user_id, CourseRow.name == name)
                .order_by(CourseRow.created_at)
                .limit(1)
            )
            return _course(row) if row else None


class ChapterRepository(_Repo):
    def first_of(self, course_id: str) -> ChapterRecord | None:
        with self._factory() as s:
            row = s.scalar(
                select(ChapterRow).where(ChapterRow.course_id == course_id).order_by(ChapterRow.position).limit(1)
            )
            return _chapter_full(row) if row else None

    def get_owned(
        self, user_id: str, course_id: str, chapter_id: str, *, source: bool = False
    ) -> OwnedChapter | None:
        """The chapter with its content, if `user_id` owns `course_id` and the
        chapter belongs to it: one join, ownership in the query. The pasted text
        (up to 100 000 characters) is loaded only when asked for."""
        with self._factory() as s:
            query = (
                select(ChapterRow, CourseRow)
                .join(CourseRow, CourseRow.id == ChapterRow.course_id)
                .where(ChapterRow.id == chapter_id, CourseRow.id == course_id, CourseRow.user_id == user_id)
            )
            if not source:
                query = query.options(defer(ChapterRow.source_text))
            pair = s.execute(query).first()
            if pair is None:
                return None
            return OwnedChapter(course=_course(pair[1]), chapter=_chapter_full(pair[0], source))

    def owns(self, user_id: str, course_id: str, chapter_id: str) -> bool:
        """Ownership alone, reading no content."""
        with self._factory() as s:
            return (
                s.scalar(
                    select(ChapterRow.id)
                    .join(CourseRow, CourseRow.id == ChapterRow.course_id)
                    .where(ChapterRow.id == chapter_id, CourseRow.id == course_id, CourseRow.user_id == user_id)
                )
                is not None
            )

    def create(
        self, course_id: str, source_text: str, max_chapters: int, chapter_id: str | None = None
    ) -> ChapterRecord:
        """A chapter at the end of its course, not yet ready."""
        with self._factory() as s:
            row = self._insert(s, course_id, source_text, max_chapters, "idle", chapter_id)
            s.commit()
            return _chapter_full(row)

    @staticmethod
    def _insert(
        s: Session, course_id: str, source_text: str, max_chapters: int, state: str, chapter_id: str | None = None
    ) -> ChapterRow:
        count, last = s.execute(
            select(func.count(ChapterRow.id), func.max(ChapterRow.position)).where(ChapterRow.course_id == course_id)
        ).one()
        if count >= max_chapters:
            raise ChapterLimit()
        now = utcnow()
        row = ChapterRow(
            id=chapter_id or new_id(),
            course_id=course_id,
            position=(last or 0) + 1,
            source_text=source_text,
            section_count=0,
            content_version=0,
            authoring_state=state,
            created_at=now,
            updated_at=now,
        )
        s.add(row)
        s.execute(update(CourseRow).where(CourseRow.id == course_id).values(updated_at=now))
        return row

    def adopt_content(
        self, chapter_id: str, content: ValidContent, expected_version: int | None = None
    ) -> ChapterRecord:
        """Replace the chapter's content, bump its version and delete its progress,
        in one transaction (005 design 3.10). With `expected_version`, a chapter
        changed since it was read is refused with `StaleVersion`."""
        with self._factory() as s:
            if not self._adopt(s, chapter_id, content, expected_version, idle=False):
                state = s.scalar(select(ChapterRow.authoring_state).where(ChapterRow.id == chapter_id))
                raise AuthoringRunning() if state == "generating" else StaleVersion()
            s.commit()
            row = s.get(ChapterRow, chapter_id, populate_existing=True)
            assert row is not None
            return _chapter_full(row)

    @staticmethod
    def _adopt(
        s: Session, chapter_id: str, content: ValidContent, expected_version: int | None, *, idle: bool
    ) -> bool:
        """The content update and its consequences; False when no row matched."""
        now = utcnow()
        condition = [ChapterRow.id == chapter_id]
        if expected_version is not None:
            # An editor save: refused while a run is in progress, since that run
            # would overwrite the edit when it adopts its own content.
            condition += [ChapterRow.content_version == expected_version, ChapterRow.authoring_state != "generating"]
        values: dict[str, object] = {
            "pack": content.pack,
            "title": content.title,
            "curriculum": content.curriculum.model_dump(mode="json"),
            "section_count": len(content.curriculum.sections),
            "content_version": ChapterRow.content_version + 1,
            "content_updated_at": now,
            "updated_at": now,
        }
        if idle:
            values.update(authoring_state="idle", authoring_error=None, authoring_stage=None)
        course_id = s.scalar(update(ChapterRow).where(*condition).values(**values).returning(ChapterRow.course_id))
        if course_id is None:
            return False
        s.execute(delete(ProgressRow).where(ProgressRow.chapter_id == chapter_id))
        s.execute(update(CourseRow).where(CourseRow.id == course_id).values(updated_at=now))
        return True

    def delete(self, user_id: str, course_id: str, chapter_id: str) -> bool:
        with self._factory() as s:
            owned_course = select(CourseRow.id).where(CourseRow.id == course_id, CourseRow.user_id == user_id)
            result = s.execute(
                delete(ChapterRow).where(ChapterRow.id == chapter_id, ChapterRow.course_id.in_(owned_course))
            )
            s.commit()
            return bool(result.rowcount)

    # ---------------------------------------------------------------- authoring

    def begin_authoring(
        self,
        *,
        user_id: str,
        course_id: str,
        chapter_id: str | None,
        source_text: str | None,
        trigger: str,
        model: str,
        max_chapters: int,
        source_kind: str = "text",
        page_count: int = 0,
    ) -> tuple[ChapterRecord, str]:
        """In one transaction: the chapter (created, or its text replaced) marked
        generating, and a running run row. Returns the chapter and the run id. An
        existing chapter already generating is refused, whatever the caller read."""
        stage = "transcription" if source_kind == "document" else "pack"
        with self._factory() as s:
            now = utcnow()
            if chapter_id is None:
                assert source_text is not None
                row = self._insert(s, course_id, source_text, max_chapters, "generating")
                s.flush()
                row.source_kind = source_kind
                row.authoring_stage = stage
                row.pages_done, row.page_count = 0, page_count
            else:
                values: dict[str, object] = {
                    "authoring_state": "generating",
                    "authoring_error": None,
                    "authoring_stage": stage,
                    "updated_at": now,
                }
                if source_kind == "document":  # a text run keeps the pages of the chapter's document
                    values |= {"pages_done": 0, "page_count": page_count}
                if source_text is not None:
                    values["source_text"] = source_text
                result = s.execute(
                    update(ChapterRow)
                    .where(ChapterRow.id == chapter_id, ChapterRow.authoring_state != "generating")
                    .values(**values)
                )
                if not result.rowcount:
                    raise AuthoringRunning()
                row = s.get(ChapterRow, chapter_id, populate_existing=True)
                assert row is not None
            run = AuthoringRunRow(
                id=new_id(), user_id=user_id, chapter_id=row.id, trigger=trigger, state="running",
                model=model, started_at=now, source_kind=source_kind, page_count=page_count,
            )
            s.add(run)
            s.commit()
            return _chapter_full(row), run.id

    def adopt_authored(self, chapter_id: str, run_id: str, content: ValidContent, usage: RunUsage) -> bool:
        """The run's output becomes the chapter's content and the run succeeds, in
        one transaction. False when the chapter was deleted meanwhile: the run is
        closed as discarded."""
        with self._factory() as s:
            adopted = self._adopt(s, chapter_id, content, None, idle=True)
            s.execute(
                update(AuthoringRunRow)
                .where(AuthoringRunRow.id == run_id)
                .values(
                    state="succeeded" if adopted else "failed",
                    error_code=None if adopted else "discarded",
                    finished_at=utcnow(),
                    **_usage_values(usage),
                )
            )
            s.commit()
            return adopted

    def finish_failed(self, chapter_id: str, run_id: str, code: str, usage: RunUsage) -> str | None:
        """The run failed; the chapter says so and keeps whatever content it had, and
        the stage it had reached (written as the run went). Returns that stage."""
        with self._factory() as s:
            now = utcnow()
            stage = s.scalar(
                select(ChapterRow.authoring_stage).where(
                    ChapterRow.id == chapter_id, ChapterRow.authoring_state == "generating"
                )
            )
            s.execute(
                update(AuthoringRunRow)
                .where(AuthoringRunRow.id == run_id)
                .values(state="failed", error_code=code, stage=stage, finished_at=now, **_usage_values(usage))
            )
            s.execute(
                update(ChapterRow)
                .where(ChapterRow.id == chapter_id, ChapterRow.authoring_state == "generating")
                .values(authoring_state="failed", authoring_error=code, updated_at=now)
            )
            s.commit()
            return stage

    def count_in_course(self, course_id: str) -> int:
        with self._factory() as s:
            return s.scalar(select(func.count(ChapterRow.id)).where(ChapterRow.course_id == course_id)) or 0

    def set_progress(self, chapter_id: str, stage: str, pages_done: int | None = None) -> None:
        """Where a run is: its stage, and while transcribing the pages read so far."""
        values: dict[str, object] = {"authoring_stage": stage}
        if pages_done is not None:
            values["pages_done"] = pages_done
        with self._factory() as s:
            s.execute(
                update(ChapterRow)
                .where(ChapterRow.id == chapter_id, ChapterRow.authoring_state == "generating")
                .values(**values)
            )
            s.commit()

    def store_transcription(
        self, chapter_id: str, run_id: str, text: str, page_count: int, counts: tuple[int, int, int]
    ) -> None:
        """A validated transcription becomes the chapter's source, in one transaction
        with its upload row and the run's counters: from here a failure keeps it and
        « Réessayer » starts from the pack stage (006 R3.3)."""
        handwritten, uncertain, illegible = counts
        with self._factory() as s:
            now = utcnow()
            result = s.execute(
                update(ChapterRow)
                .where(ChapterRow.id == chapter_id)
                .values(source_text=text, source_kind="document", authoring_stage="pack",
                        pages_done=page_count, page_count=page_count, updated_at=now)
            )
            if not result.rowcount:
                return  # deleted meanwhile: the run will be discarded
            s.execute(delete(ChapterUploadRow).where(ChapterUploadRow.chapter_id == chapter_id))
            s.add(ChapterUploadRow(id=new_id(), chapter_id=chapter_id, run_id=run_id, first_page=1,
                                   page_count=page_count, created_at=now))
            s.execute(
                update(AuthoringRunRow)
                .where(AuthoringRunRow.id == run_id)
                .values(handwritten_marks=handwritten, uncertain_marks=uncertain, illegible_marks=illegible)
            )
            s.commit()

    def uploads(self, chapter_id: str) -> list[tuple[int, int]]:
        """(first page, page count) of each upload behind the chapter's source."""
        with self._factory() as s:
            rows = s.execute(
                select(ChapterUploadRow.first_page, ChapterUploadRow.page_count)
                .where(ChapterUploadRow.chapter_id == chapter_id)
                .order_by(ChapterUploadRow.first_page)
            )
            return [tuple(row) for row in rows]


def _usage_values(usage: RunUsage) -> dict[str, object]:
    return {
        "attempts_transcription": usage.attempts_transcription,
        "attempts_pack": usage.attempts_pack,
        "attempts_curriculum": usage.attempts_curriculum,
        "transcription_ms": usage.transcription_ms,
        "pack_ms": usage.pack_ms,
        "curriculum_ms": usage.curriculum_ms,
        "transcription_cost_usd": usage.transcription_cost_usd,
        "input_tokens": usage.input_tokens,
        "cached_tokens": usage.cached_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cost_estimate_usd": usage.cost_estimate_usd,
    }


class AuthoringRunRepository(_Repo):
    def running_for_user(self, user_id: str) -> int:
        with self._factory() as s:
            return s.scalar(
                select(func.count()).select_from(AuthoringRunRow).where(
                    AuthoringRunRow.user_id == user_id, AuthoringRunRow.state == "running"
                )
            ) or 0

    def started_since(self, user_id: str, since: datetime) -> tuple[int, datetime | None]:
        """How many runs started after `since`, and when the oldest of them did."""
        with self._factory() as s:
            count, oldest = s.execute(
                select(func.count(AuthoringRunRow.id), func.min(AuthoringRunRow.started_at)).where(
                    AuthoringRunRow.user_id == user_id, AuthoringRunRow.started_at > since
                )
            ).one()
            return count or 0, as_utc(oldest) if oldest else None

    def active(self) -> int:
        with self._factory() as s:
            return s.scalar(select(func.count()).select_from(AuthoringRunRow).where(AuthoringRunRow.state == "running")) or 0

    def fail_orphans(self) -> int:
        """Startup: a run still marked running belongs to a process that is gone."""
        with self._factory() as s:
            now = utcnow()
            result = s.execute(
                update(AuthoringRunRow)
                .where(AuthoringRunRow.state == "running")
                .values(state="failed", error_code="interrupted", finished_at=now)
            )
            s.execute(
                update(ChapterRow)
                .where(ChapterRow.authoring_state == "generating")
                .values(authoring_state="failed", authoring_error="interrupted", updated_at=now)
            )
            s.commit()
            return result.rowcount or 0


class ProgressRepository(_Repo):
    def load(self, user_id: str, chapter_id: str) -> ProgressRecord | None:
        with self._factory() as s:
            row = s.get(ProgressRow, (user_id, chapter_id))
            return _record(row) if row else None

    def save(self, user_id: str, chapter_id: str, progress: Progress, version: int | None = None) -> None:
        """Upsert. With `version`, refused (`StaleVersion`) when the chapter's content
        changed since the turn loaded it: its section ids belong to the old path."""
        with self._factory() as s:
            if version is not None:
                current = s.scalar(select(ChapterRow.content_version).where(ChapterRow.id == chapter_id))
                if current != version:
                    raise StaleVersion()
            row = s.get(ProgressRow, (user_id, chapter_id))
            if row is None:
                row = ProgressRow(user_id=user_id, chapter_id=chapter_id)
                s.add(row)
            row.done = list(progress.done)
            row.active = progress.active
            row.updated_at = utcnow()
            s.commit()

    def clear(self, user_id: str, chapter_id: str) -> None:
        with self._factory() as s:
            s.execute(
                delete(ProgressRow).where(
                    ProgressRow.user_id == user_id, ProgressRow.chapter_id == chapter_id
                )
            )
            s.commit()

    def for_chapters(self, user_id: str, chapter_ids: list[str]) -> dict[str, ProgressRecord]:
        if not chapter_ids:
            return {}
        with self._factory() as s:
            rows = s.scalars(
                select(ProgressRow).where(
                    ProgressRow.user_id == user_id, ProgressRow.chapter_id.in_(chapter_ids)
                )
            )
            return {row.chapter_id: _record(row) for row in rows}


def _record(row: ProgressRow) -> ProgressRecord:
    return ProgressRecord(
        progress=Progress(done=frozenset(row.done or []), active=row.active),
        updated_at=as_utc(row.updated_at),
    )


@dataclass(frozen=True)
class Period:
    """A half-open span, `since <= created_at < until`; an open end is unbounded. Instants of any offset."""

    since: datetime | None = None
    until: datetime | None = None


@dataclass(frozen=True)
class CallFilters:
    user_id: str | None = None
    role: str | None = None
    feature: str | None = None
    model: str | None = None
    status: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class UsageTotals:
    """What a set of calls came to. `cost_usd` is the sum of the costs the provider reported and is None when no
    call reported one; `costed_calls` is how many did, out of `calls`. Tokens sum what was reported."""

    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float | None = None
    costed_calls: int = 0


@dataclass(frozen=True)
class UsageSummary:
    totals: UsageTotals
    models: list[str]


@dataclass(frozen=True)
class UserUsage:
    user_id: str
    name: str
    email: str
    enabled: bool
    totals: UsageTotals


@dataclass(frozen=True)
class RoleUsage:
    role: str
    totals: UsageTotals


@dataclass(frozen=True)
class ModelUsage:
    model: str
    provider: str
    totals: UsageTotals


@dataclass(frozen=True)
class Breakdown:
    totals: UsageTotals
    by_role: list[RoleUsage]
    by_model: list[ModelUsage]


@dataclass(frozen=True)
class CallListing:
    """One call, with the account's name and the course's subject and language (never the course's name)."""

    id: int
    entry: UsageEntry
    user_name: str
    user_email: str
    course_subject: str | None
    course_language: str | None


UserUsageOrder = Literal["calls", "input_tokens", "output_tokens", "cost", "name"]


def _utc(value: datetime) -> datetime:
    """SQLite stores no offset: an instant is compared as UTC, whatever offset it came with."""
    return as_utc(value).astimezone(UTC)


def _totals_columns() -> tuple[Any, ...]:
    return (
        func.count(AiUsageRow.id),
        func.coalesce(func.sum(AiUsageRow.input_tokens), 0),
        func.coalesce(func.sum(AiUsageRow.cached_tokens), 0),
        func.coalesce(func.sum(AiUsageRow.output_tokens), 0),
        func.coalesce(func.sum(AiUsageRow.reasoning_tokens), 0),
        func.sum(AiUsageRow.cost_usd),
        func.count(AiUsageRow.cost_usd),
    )


def _totals(columns: tuple[Any, ...]) -> UsageTotals:
    calls, tokens_in, cached, tokens_out, reasoning, cost, costed = columns
    return UsageTotals(
        calls=int(calls),
        input_tokens=int(tokens_in),
        cached_tokens=int(cached),
        output_tokens=int(tokens_out),
        reasoning_tokens=int(reasoning),
        cost_usd=None if cost is None else float(cost),
        costed_calls=int(costed),
    )


def _sum_totals(parts: Iterable[UsageTotals]) -> UsageTotals:
    """The totals of disjoint sets of calls: the cost is a sum only of those that reported one."""
    parts = list(parts)
    costs = [p.cost_usd for p in parts if p.cost_usd is not None]
    return UsageTotals(
        calls=sum(p.calls for p in parts),
        input_tokens=sum(p.input_tokens for p in parts),
        cached_tokens=sum(p.cached_tokens for p in parts),
        output_tokens=sum(p.output_tokens for p in parts),
        reasoning_tokens=sum(p.reasoning_tokens for p in parts),
        cost_usd=sum(costs) if costs else None,
        costed_calls=sum(p.costed_calls for p in parts),
    )


def _period_where(period: Period) -> list[Any]:
    where = []
    if period.since is not None:
        where.append(AiUsageRow.created_at >= _utc(period.since))
    if period.until is not None:
        where.append(AiUsageRow.created_at < _utc(period.until))
    return where


class AiUsageRepository(_Repo):
    """The usage ledger (spec 015). Writes are one row per call; reads aggregate in SQL."""

    def add(self, entry: UsageEntry) -> None:
        """Store one row. A course or chapter deleted while its call was in flight must not cost the row: it is
        stored without them (the same thing the foreign keys do to rows already there)."""
        values = {**asdict(entry), "created_at": _utc(entry.created_at)}
        try:
            self._insert(values)
        except IntegrityError:
            if values["course_id"] is None and values["chapter_id"] is None:
                raise  # the user is gone: nothing to attribute the call to
            self._insert({**values, "course_id": None, "chapter_id": None})

    def _insert(self, values: dict[str, Any]) -> None:
        with self._factory() as s:
            s.add(AiUsageRow(**values))
            s.commit()

    def add_once(self, entry: UsageEntry) -> bool:
        """`add`, unless the user already has a row of that feature for that correlation id (a session reported
        twice). A row with no correlation id is always stored. Returns whether it was."""
        if entry.correlation_id is not None:
            with self._factory() as s:
                known = s.scalar(
                    select(AiUsageRow.id)
                    .where(
                        AiUsageRow.user_id == entry.user_id,
                        AiUsageRow.feature == entry.feature,
                        AiUsageRow.correlation_id == entry.correlation_id,
                    )
                    .limit(1)
                )
            if known is not None:
                return False
        self.add(entry)
        return True

    def summary(self, period: Period, *, user_id: str | None = None) -> UsageSummary:
        where = _period_where(period)
        if user_id is not None:
            where.append(AiUsageRow.user_id == user_id)
        with self._factory() as s:
            totals = _totals(tuple(s.execute(select(*_totals_columns()).where(*where)).one()))
            models = s.scalars(
                select(AiUsageRow.model).where(*where, AiUsageRow.model != "").distinct().order_by(AiUsageRow.model)
            ).all()
            return UsageSummary(totals=totals, models=list(models))

    def per_user(
        self,
        period: Period,
        *,
        query: str = "",
        order: UserUsageOrder = "calls",
        descending: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[UserUsage], int]:
        """The users with calls in the period, and how many there are in all. `query` matches the name or the
        address as the accounts list does."""
        where = _period_where(period)
        if query.strip():
            where.append(_user_match(query))
        columns = _totals_columns()
        grouped = (
            select(AiUsageRow.user_id, UserRow.name, UserRow.email, UserRow.enabled, *columns)
            .join(UserRow, UserRow.id == AiUsageRow.user_id)
            .where(*where)
            .group_by(AiUsageRow.user_id, UserRow.name, UserRow.email, UserRow.enabled)
        )
        sort = {
            "calls": columns[0],
            "input_tokens": columns[1],
            "output_tokens": columns[3],
            "cost": columns[5],
            "name": func.lower(UserRow.name),
        }[order]
        ordering = sort.desc() if descending else sort.asc()
        if order == "cost":
            ordering = ordering.nulls_last()
        with self._factory() as s:
            total = s.scalar(select(func.count()).select_from(grouped.subquery())) or 0
            rows = s.execute(grouped.order_by(ordering, AiUsageRow.user_id).limit(limit).offset(offset)).all()
            return [
                UserUsage(user_id=row[0], name=row[1], email=row[2], enabled=bool(row[3]), totals=_totals(tuple(row[4:])))
                for row in rows
            ], total

    def user_breakdown(self, user_id: str, period: Period) -> Breakdown:
        where = [*_period_where(period), AiUsageRow.user_id == user_id]
        columns = _totals_columns()
        with self._factory() as s:
            by_role = s.execute(
                select(AiUsageRow.role, *columns).where(*where).group_by(AiUsageRow.role).order_by(AiUsageRow.role)
            ).all()
            by_model = s.execute(
                select(AiUsageRow.model, AiUsageRow.provider, *columns)
                .where(*where)
                .group_by(AiUsageRow.model, AiUsageRow.provider)
                .order_by(columns[0].desc(), AiUsageRow.model)
            ).all()
        return Breakdown(
            totals=_sum_totals(_totals(tuple(row[1:])) for row in by_role),  # the roles partition the rows
            by_role=[RoleUsage(role=row[0], totals=_totals(tuple(row[1:]))) for row in by_role],
            by_model=[ModelUsage(model=row[0], provider=row[1], totals=_totals(tuple(row[2:]))) for row in by_model],
        )

    def calls(
        self, period: Period, filters: CallFilters, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[CallListing], bool]:
        """A page of calls, newest first, and whether there is a next page (one more row is read, no count)."""
        where = _period_where(period)
        for column, value in (
            (AiUsageRow.user_id, filters.user_id),
            (AiUsageRow.role, filters.role),
            (AiUsageRow.feature, filters.feature),
            (AiUsageRow.model, filters.model),
            (AiUsageRow.status, filters.status),
            (AiUsageRow.correlation_id, filters.correlation_id),
        ):
            if value is not None:
                where.append(column == value)
        with self._factory() as s:
            rows = s.execute(
                select(AiUsageRow, UserRow.name, UserRow.email, CourseRow.subject, CourseRow.language)
                .join(UserRow, UserRow.id == AiUsageRow.user_id)
                .outerjoin(CourseRow, CourseRow.id == AiUsageRow.course_id)
                .where(*where)
                .order_by(AiUsageRow.created_at.desc(), AiUsageRow.id.desc())
                .limit(limit + 1)
                .offset(offset)
            ).all()
            listing = [
                CallListing(
                    id=row.id,
                    entry=_entry(row),
                    user_name=name,
                    user_email=email,
                    course_subject=subject,
                    course_language=language,
                )
                for row, name, email, subject, language in rows[:limit]
            ]
            return listing, len(rows) > limit


def _entry(row: AiUsageRow) -> UsageEntry:
    values = {f.name: getattr(row, f.name) for f in fields(UsageEntry)}
    return UsageEntry(**{**values, "created_at": as_utc(row.created_at)})


@dataclass(frozen=True)
class ConversationRecord:
    id: str
    user_id: str
    chapter_id: str
    content_version: int
    entries: list[dict[str, Any]]
    entry_count: int
    char_count: int
    state: str
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def live(self) -> bool:
        return self.state == "live"


def _conversation(row: ConversationRow) -> ConversationRecord:
    return ConversationRecord(
        id=row.id,
        user_id=row.user_id,
        chapter_id=row.chapter_id,
        content_version=row.content_version,
        entries=list(row.entries or []),
        entry_count=row.entry_count,
        char_count=row.char_count,
        state=row.state,
        closed_reason=row.closed_reason,
        created_at=as_utc(row.created_at),
        updated_at=as_utc(row.updated_at),
    )


def _entry_chars(entry: dict[str, Any]) -> int:
    """What an entry costs against the cap: its text, or its tool arguments."""
    text = entry.get("text")
    if isinstance(text, str):
        return len(text)
    return len(json.dumps(entry.get("arguments") or {}, ensure_ascii=False))


class ConversationRepository(_Repo):
    """Stored discussions (007 design 4.2). One live conversation per student and
    chapter, the database enforcing it through a partial unique index."""

    def live(self, user_id: str, chapter_id: str) -> ConversationRecord | None:
        with self._factory() as s:
            row = s.scalar(
                select(ConversationRow).where(
                    ConversationRow.user_id == user_id,
                    ConversationRow.chapter_id == chapter_id,
                    ConversationRow.state == "live",
                )
            )
            return _conversation(row) if row else None

    def get_owned(
        self, user_id: str, chapter_id: str, conversation_id: str
    ) -> ConversationRecord | None:
        """Owner and chapter are in the query, so a valid id from another chapter
        does not resolve (007 design 8)."""
        with self._factory() as s:
            row = s.scalar(
                select(ConversationRow).where(
                    ConversationRow.id == conversation_id,
                    ConversationRow.user_id == user_id,
                    ConversationRow.chapter_id == chapter_id,
                )
            )
            return _conversation(row) if row else None

    def start(self, user_id: str, chapter_id: str, content_version: int) -> ConversationRecord:
        """Close any live one, insert a new empty one, in one transaction."""
        now = utcnow()
        with self._factory() as s:
            s.execute(
                update(ConversationRow)
                .where(
                    ConversationRow.user_id == user_id,
                    ConversationRow.chapter_id == chapter_id,
                    ConversationRow.state == "live",
                )
                .values(state="closed", closed_reason="replaced", updated_at=now)
            )
            row = ConversationRow(
                id=uuid.uuid4().hex,
                user_id=user_id,
                chapter_id=chapter_id,
                mode="discussion",
                content_version=content_version,
                entries=[],
                entry_count=0,
                char_count=0,
                state="live",
                closed_reason=None,
                created_at=now,
                updated_at=now,
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            return _conversation(row)

    def close(self, conversation_id: str, reason: str) -> None:
        with self._factory() as s:
            s.execute(
                update(ConversationRow)
                .where(ConversationRow.id == conversation_id, ConversationRow.state == "live")
                .values(state="closed", closed_reason=reason, updated_at=utcnow())
            )
            s.commit()

    def append(
        self,
        conversation_id: str,
        entries: list[dict[str, Any]],
        *,
        expected_count: int,
        max_entries: int,
        max_chars: int,
    ) -> ConversationRecord:
        """One UPDATE, so a turn lands whole or not at all (007 NFR 4.4.1).

        `expected_count` is the optimistic guard: a mismatch means another turn
        appended first, which is `ConversationBusy` rather than an interleaved
        transcript. Crossing either cap closes the row as `capped`.
        """
        with self._factory() as s:
            row = s.get(ConversationRow, conversation_id)
            if row is None or row.entry_count != expected_count:
                raise ConversationBusy()
            merged = list(row.entries or []) + entries
            row.entries = merged
            row.entry_count = len(merged)
            row.char_count += sum(_entry_chars(e) for e in entries)
            row.updated_at = utcnow()
            if row.entry_count >= max_entries or row.char_count >= max_chars:
                row.state = "closed"
                row.closed_reason = "capped"
            # Read back from memory: the values are all known here, and refreshing
            # would re-select and re-parse the whole transcript blob.
            after = _conversation(row)
            s.commit()
            return after

    def started_since(self, user_id: str, since: datetime) -> int:
        with self._factory() as s:
            return (
                s.scalar(
                    select(func.count())
                    .select_from(ConversationRow)
                    .where(
                        ConversationRow.user_id == user_id,
                        ConversationRow.created_at >= since,
                    )
                )
                or 0
            )


class AppSettingsRepository(_Repo):
    """Instance-wide settings (spec 013): a key, a text value, who changed it and when."""

    def get(self, key: str) -> str | None:
        with self._factory() as s:
            row = s.get(AppSettingRow, key)
            return row.value if row else None

    def put(self, key: str, value: str, updated_by: str | None) -> None:
        with self._factory() as s:
            s.merge(AppSettingRow(key=key, value=value, updated_at=utcnow(), updated_by=updated_by))
            s.commit()

    def delete(self, key: str) -> bool:
        with self._factory() as s:
            removed = s.execute(delete(AppSettingRow).where(AppSettingRow.key == key)).rowcount
            s.commit()
            return bool(removed)


@dataclass(frozen=True)
class Repositories:
    users: UserRepository
    sessions: SessionRepository
    courses: CourseRepository
    chapters: ChapterRepository
    runs: AuthoringRunRepository
    progress: ProgressRepository
    conversations: ConversationRepository
    ai_usage: AiUsageRepository
    app_settings: AppSettingsRepository

    @classmethod
    def from_factory(cls, factory: sessionmaker[Session]) -> Repositories:
        return cls(
            users=UserRepository(factory),
            sessions=SessionRepository(factory),
            courses=CourseRepository(factory),
            chapters=ChapterRepository(factory),
            runs=AuthoringRunRepository(factory),
            progress=ProgressRepository(factory),
            conversations=ConversationRepository(factory),
            ai_usage=AiUsageRepository(factory),
            app_settings=AppSettingsRepository(factory),
        )
