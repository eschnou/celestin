"""spec 010: the interface language of a user

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing account reads 'fr': what it has always seen.
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('locale', sa.String(length=8), nullable=False, server_default='fr'))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('locale')
