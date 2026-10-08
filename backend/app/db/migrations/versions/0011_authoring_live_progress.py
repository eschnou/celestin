"""spec 016: live progress of a preparation (characters received, time of the last write)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('chapters') as batch:
        batch.add_column(sa.Column('authoring_received_chars', sa.Integer(), server_default='0', nullable=False))
        batch.add_column(sa.Column('authoring_progress_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('chapters') as batch:
        batch.drop_column('authoring_progress_at')
        batch.drop_column('authoring_received_chars')
