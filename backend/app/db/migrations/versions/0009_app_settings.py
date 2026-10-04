"""spec 013: instance settings kept by the application (the encrypted OpenAI key)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-03 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A new table only: nothing existing is altered, so SQLite rebuilds nothing.
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('app_settings')
