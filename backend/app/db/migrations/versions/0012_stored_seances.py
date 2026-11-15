"""spec 018: stored séances — parcours rows in `conversations`, one live per student, chapter and mode

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-15 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The live index moves to (user, chapter, mode) before any parcours row can exist.
    op.drop_index('uq_conversations_live', table_name='conversations')
    # Batch mode: SQLite cannot alter a check constraint in place, so the table is rebuilt. Nothing points at
    # `conversations`, so the rebuild deletes nothing through a foreign key.
    with op.batch_alter_table('conversations') as batch:
        batch.add_column(sa.Column('section_id', sa.String(length=40), nullable=True))
        batch.add_column(sa.Column('card_count', sa.Integer(), server_default='0', nullable=False))
        batch.drop_constraint('ck_conversations_mode', type_='check')
        batch.create_check_constraint('ck_conversations_mode', "mode in ('discussion','parcours')")
    op.create_index(
        'uq_conversations_live',
        'conversations',
        ['user_id', 'chapter_id', 'mode'],
        unique=True,
        sqlite_where=sa.text("state = 'live'"),
        postgresql_where=sa.text("state = 'live'"),
    )


def downgrade() -> None:
    # The parcours rows have no place in the older schema: they go, the discussions stay.
    op.execute("delete from conversations where mode = 'parcours'")
    op.drop_index('uq_conversations_live', table_name='conversations')
    with op.batch_alter_table('conversations') as batch:
        batch.drop_constraint('ck_conversations_mode', type_='check')
        batch.create_check_constraint('ck_conversations_mode', "mode in ('discussion')")
        batch.drop_column('card_count')
        batch.drop_column('section_id')
    op.create_index(
        'uq_conversations_live',
        'conversations',
        ['user_id', 'chapter_id'],
        unique=True,
        sqlite_where=sa.text("state = 'live'"),
        postgresql_where=sa.text("state = 'live'"),
    )
