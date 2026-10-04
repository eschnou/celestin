"""student-authored courses: courses, chapters, authoring runs; enrolments dropped

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16 12:00:00

No data is preserved (005 R6.5): progress rows referenced catalog chapters that no
longer exist, so the table is recreated with a foreign key to `chapters`.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

# Edited in place when the subjects became four categories (before any release): a database created
# before that must be recreated.
SUBJECTS = "('mathematics', 'sciences', 'languages', 'general')"


def upgrade() -> None:
    op.drop_table('enrolments')
    op.drop_table('progress')

    op.create_table('courses',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('subject', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(f"subject in {SUBJECTS}", name='ck_courses_subject'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.create_index('ix_courses_user_id', ['user_id'], unique=False)

    op.create_table('chapters',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('course_id', sa.String(length=32), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('source_text', sa.Text(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('pack', sa.Text(), nullable=True),
    sa.Column('curriculum', sa.JSON(), nullable=True),
    sa.Column('section_count', sa.Integer(), nullable=False),
    sa.Column('content_version', sa.Integer(), nullable=False),
    sa.Column('authoring_state', sa.String(length=12), nullable=False),
    sa.Column('authoring_error', sa.String(length=24), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('content_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("authoring_state in ('idle', 'generating', 'failed')", name='ck_chapters_authoring_state'),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.create_index('ix_chapters_course_id', ['course_id'], unique=False)

    op.create_table('authoring_runs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('chapter_id', sa.String(length=32), nullable=True),
    sa.Column('trigger', sa.String(length=12), nullable=False),
    sa.Column('state', sa.String(length=12), nullable=False),
    sa.Column('error_code', sa.String(length=24), nullable=True),
    sa.Column('stage', sa.String(length=12), nullable=True),
    sa.Column('model', sa.String(length=64), nullable=False),
    sa.Column('attempts_pack', sa.Integer(), nullable=False),
    sa.Column('attempts_curriculum', sa.Integer(), nullable=False),
    sa.Column('pack_ms', sa.Integer(), nullable=False),
    sa.Column('curriculum_ms', sa.Integer(), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('cached_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('reasoning_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_estimate_usd', sa.Float(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("state in ('running', 'succeeded', 'failed')", name='ck_authoring_runs_state'),
    sa.CheckConstraint("trigger in ('create', 'retry', 'source_edit')", name='ck_authoring_runs_trigger'),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('authoring_runs', schema=None) as batch_op:
        batch_op.create_index('ix_authoring_runs_state', ['state'], unique=False)
        batch_op.create_index('ix_authoring_runs_user_started', ['user_id', 'started_at'], unique=False)

    op.create_table('progress',
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('chapter_id', sa.String(length=32), nullable=False),
    sa.Column('done', sa.JSON(), nullable=False),
    sa.Column('active', sa.String(length=40), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'chapter_id')
    )


def downgrade() -> None:
    op.drop_table('progress')
    with op.batch_alter_table('authoring_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_authoring_runs_user_started')
        batch_op.drop_index('ix_authoring_runs_state')
    op.drop_table('authoring_runs')
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.drop_index('ix_chapters_course_id')
    op.drop_table('chapters')
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.drop_index('ix_courses_user_id')
    op.drop_table('courses')

    op.create_table('progress',
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('chapter_id', sa.String(length=40), nullable=False),
    sa.Column('done', sa.JSON(), nullable=False),
    sa.Column('active', sa.String(length=40), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'chapter_id')
    )
    op.create_table('enrolments',
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('class_id', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'class_id')
    )
