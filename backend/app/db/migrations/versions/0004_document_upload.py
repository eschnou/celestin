"""document upload: source kind, run stage and pages on chapters; transcription counters on runs; chapter_uploads

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-18 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

INTEGER_RUN_COLUMNS = (
    'page_count', 'attempts_transcription', 'transcription_ms',
    'handwritten_marks', 'uncertain_marks', 'illegible_marks',
)


def upgrade() -> None:
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_kind', sa.String(length=12), server_default='text', nullable=False))
        batch_op.add_column(sa.Column('authoring_stage', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('pages_done', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('page_count', sa.Integer(), server_default='0', nullable=False))
        batch_op.create_check_constraint('ck_chapters_source_kind', "source_kind in ('text', 'document')")

    with op.batch_alter_table('authoring_runs', schema=None) as batch_op:
        batch_op.alter_column('stage', existing_type=sa.String(length=12), type_=sa.String(length=16),
                              existing_nullable=True)
        batch_op.add_column(sa.Column('source_kind', sa.String(length=12), server_default='text', nullable=False))
        for name in INTEGER_RUN_COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('transcription_cost_usd', sa.Float(), server_default='0', nullable=False))
        batch_op.drop_constraint('ck_authoring_runs_trigger', type_='check')
        batch_op.create_check_constraint(
            'ck_authoring_runs_trigger', "trigger in ('create', 'retry', 'source_edit', 'replace')"
        )

    op.create_table('chapter_uploads',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('chapter_id', sa.String(length=32), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('first_page', sa.Integer(), nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chapter_uploads', schema=None) as batch_op:
        batch_op.create_index('ix_chapter_uploads_chapter_id', ['chapter_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('chapter_uploads', schema=None) as batch_op:
        batch_op.drop_index('ix_chapter_uploads_chapter_id')
    op.drop_table('chapter_uploads')
    with op.batch_alter_table('authoring_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_authoring_runs_trigger', type_='check')
        batch_op.create_check_constraint('ck_authoring_runs_trigger', "trigger in ('create', 'retry', 'source_edit')")
        batch_op.drop_column('transcription_cost_usd')
        for name in reversed(INTEGER_RUN_COLUMNS):
            batch_op.drop_column(name)
        batch_op.drop_column('source_kind')
        batch_op.alter_column('stage', existing_type=sa.String(length=16), type_=sa.String(length=12),
                              existing_nullable=True)
    with op.batch_alter_table('chapters', schema=None) as batch_op:
        batch_op.drop_constraint('ck_chapters_source_kind', type_='check')
        batch_op.drop_column('page_count')
        batch_op.drop_column('pages_done')
        batch_op.drop_column('authoring_stage')
        batch_op.drop_column('source_kind')
