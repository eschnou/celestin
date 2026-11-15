"""spec 019: the open path — `progress.skipped`, the sections the student chose to pass

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-15 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing progress has skipped nothing. A plain string default, so SQLite adds the column in place
    # rather than rebuilding the table (0008).
    with op.batch_alter_table('progress') as batch:
        batch.add_column(sa.Column('skipped', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    # The older schema cannot tell a skipped section from one not started: the skips are forgotten, done and active
    # stay. Nothing points at `progress`, so a rebuild deletes nothing through a foreign key.
    with op.batch_alter_table('progress') as batch:
        batch.drop_column('skipped')
