"""Tables (004 design 4.1). Portable types only: String, Integer, Float, JSON,
DateTime(timezone=True); ids are uuid4 hex strings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.subject import SUBJECT_IDS
from app.domain.user import ROLES


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(f"role in {ROLES!r}", name="ck_users_role"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # The interface language (spec 010). The supported list is code, not a constraint.
    locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="fr")
    # Spec 012: false until an admin enables the account (verification mode), or after
    # an admin disabled it. Existing accounts stay enabled.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When the account was last used (spec 012): the dashboard's « dernière activité ». Kept on
    # the account, not derived from sessions, which are deleted on sign-out and reset.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionRow(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


AUTHORING_STATES = ("idle", "generating", "failed")
SOURCE_KINDS = ("text", "document")
RUN_STATES = ("running", "succeeded", "failed")
RUN_TRIGGERS = ("create", "retry", "source_edit", "replace")


class CourseRow(Base):
    """A student's course (005 design 4.1). The subject never changes."""

    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(f"subject in {SUBJECT_IDS!r}", name="ck_courses_subject"),
        Index("ix_courses_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    subject: Mapped[str] = mapped_column(String(24), nullable=False)
    # The course's language (spec 011): fixed at creation, like the subject.
    language: Mapped[str] = mapped_column(String(8), nullable=False, server_default="fr")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChapterRow(Base):
    """A chapter: what was pasted, and the content adopted from it. `pack`,
    `curriculum` and `title` are set together; ready means `content_version > 0`."""

    __tablename__ = "chapters"
    __table_args__ = (
        CheckConstraint(f"authoring_state in {AUTHORING_STATES!r}", name="ck_chapters_authoring_state"),
        CheckConstraint(f"source_kind in {SOURCE_KINDS!r}", name="ck_chapters_source_kind"),
        Index("ix_chapters_course_id", "course_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pack: Mapped[str | None] = mapped_column(Text, nullable=True)
    curriculum: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    section_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    authoring_state: Mapped[str] = mapped_column(String(12), nullable=False, default="idle")
    authoring_error: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Spec 006: where the source came from, and how far a run got (kept on failure).
    source_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="text", server_default="text")
    authoring_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pages_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthoringRunRow(Base):
    """One authoring run: audit, quota and cost. Survives the chapter's deletion so a
    deleted chapter still counts against the daily limit."""

    __tablename__ = "authoring_runs"
    __table_args__ = (
        CheckConstraint(f"state in {RUN_STATES!r}", name="ck_authoring_runs_state"),
        CheckConstraint(f"trigger in {RUN_TRIGGERS!r}", name="ck_authoring_runs_trigger"),
        Index("ix_authoring_runs_user_started", "user_id", "started_at"),
        Index("ix_authoring_runs_state", "state"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )
    trigger: Mapped[str] = mapped_column(String(12), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(24), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="text", server_default="text")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attempts_transcription: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    transcription_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    transcription_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    handwritten_marks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    uncertain_marks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    illegible_marks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts_pack: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts_curriculum: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pack_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    curriculum_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChapterUploadRow(Base):
    """Which pages of a chapter's source came from which upload (006 design 4.1), so
    that appending pages later is a new row and a partial run."""

    __tablename__ = "chapter_uploads"
    __table_args__ = (Index("ix_chapter_uploads_chapter_id", "chapter_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    first_page: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProgressRow(Base):
    __tablename__ = "progress"

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    chapter_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("chapters.id", ondelete="CASCADE"), primary_key=True
    )
    done: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


CONVERSATION_STATES = ("live", "closed")
CLOSED_REASONS = ("replaced", "content_changed", "capped")


class ConversationRow(Base):
    """One discussion on one chapter for one student (007 design 4.1).

    `entries` is the transcript as a JSON array of the DTO shapes the turn already
    uses, like `chapters.curriculum`: one blob, so appending a turn is a single
    UPDATE and therefore atomic. `mode` is stored although only `discussion` is
    written today — révision will add a value, not a table.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "state in ('" + "','".join(CONVERSATION_STATES) + "')", name="ck_conversations_state"
        ),
        CheckConstraint("mode in ('discussion')", name="ck_conversations_mode"),
        Index("ix_conversations_user_chapter", "user_id", "chapter_id"),
        # At most one live conversation per student and chapter, enforced by the
        # database rather than by a read-then-write race.
        Index(
            "uq_conversations_live",
            "user_id",
            "chapter_id",
            unique=True,
            sqlite_where=text("state = 'live'"),
            postgresql_where=text("state = 'live'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chapter_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(12), nullable=False, default="discussion")
    # The chapter version the conversation was held against: a content change makes
    # it unusable, because its pack is gone (007 R8.3).
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(8), nullable=False, default="live")
    closed_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VoiceUsageRow(Base):
    __tablename__ = "voice_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(8), nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    responses: Mapped[int] = mapped_column(Integer, nullable=False)
    input_text: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_audio: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_text: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_audio: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_text: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_audio: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AppSettingRow(Base):
    """One instance-wide setting kept by the application (spec 013 §3.4). Today a single row,
    `openai_api_key`, whose value is a JSON document holding the API key *encrypted*."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The admin who made the change: an id, with no foreign key (the row outlives any account).
    updated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
