"""discussion mode: stored conversations, one live per student and chapter

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-20 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversations',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('chapter_id', sa.String(length=32), nullable=False),
        sa.Column('mode', sa.String(length=12), nullable=False),
        sa.Column('content_version', sa.Integer(), nullable=False),
        sa.Column('entries', sa.JSON(), nullable=False),
        sa.Column('entry_count', sa.Integer(), nullable=False),
        sa.Column('char_count', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(length=8), nullable=False),
        sa.Column('closed_reason', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state in ('live','closed')", name='ck_conversations_state'),
        sa.CheckConstraint("mode in ('discussion')", name='ck_conversations_mode'),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conversations_user_chapter', 'conversations', ['user_id', 'chapter_id'])
    # Partial: at most one live conversation per student and chapter, closed ones
    # unconstrained. Both SQLite and PostgreSQL support the predicate.
    op.create_index(
        'uq_conversations_live',
        'conversations',
        ['user_id', 'chapter_id'],
        unique=True,
        sqlite_where=sa.text("state = 'live'"),
        postgresql_where=sa.text("state = 'live'"),
    )


def downgrade() -> None:
    op.drop_index('uq_conversations_live', table_name='conversations')
    op.drop_index('ix_conversations_user_chapter', table_name='conversations')
    op.drop_table('conversations')
