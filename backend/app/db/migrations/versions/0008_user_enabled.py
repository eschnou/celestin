"""spec 012: an account can be disabled, and remembers when it was last used

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing account stays enabled: nobody is locked out by the upgrade. The default
    # is a plain string on purpose: any SQL expression makes alembic rebuild the table on
    # SQLite, and with foreign keys on that would delete every course of every student.
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    # What the open sessions say is the best the past can tell.
    op.execute('update users set last_seen_at = (select max(last_seen_at) from sessions where sessions.user_id = users.id)')


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('last_seen_at')
        batch.drop_column('enabled')
