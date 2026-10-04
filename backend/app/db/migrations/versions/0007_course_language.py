"""spec 011: the language of a course

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing course is French: what it has always been.
    with op.batch_alter_table('courses') as batch:
        batch.add_column(sa.Column('language', sa.String(length=8), nullable=False, server_default='fr'))


def downgrade() -> None:
    with op.batch_alter_table('courses') as batch:
        batch.drop_column('language')
