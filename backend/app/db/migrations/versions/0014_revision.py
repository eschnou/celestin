"""spec 020: révision — course-scoped rows in `conversations`, `revision_results`, and the `revision_turn` feature

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-15 20:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


_SCOPE = (
    "(mode <> 'revision' and chapter_id is not null and course_id is null) or "
    "(mode = 'revision' and chapter_id is null and course_id is not null)"
)


_FEATURES = (
    "'tutor_turn','discussion_turn',{revision}'authoring','document_reading','work_reading',"
    "'dictation','voice_session','ai_test'"
)


def _features(revision: bool) -> str:
    return "feature in (" + _FEATURES.format(revision="'revision_turn'," if revision else "") + ")"


def _live_index() -> None:
    op.create_index(
        'uq_conversations_live',
        'conversations',
        ['user_id', 'chapter_id', 'mode'],
        unique=True,
        sqlite_where=sa.text("state = 'live'"),
        postgresql_where=sa.text("state = 'live'"),
    )


def upgrade() -> None:
    # As in 0012: the partial index goes before the rebuild and comes back after it.
    op.drop_index('uq_conversations_live', table_name='conversations')
    # Batch mode: SQLite cannot alter a check constraint or a column's nullability in place, so the table is rebuilt.
    # Nothing points at `conversations` yet (`revision_results` is created below), so the rebuild deletes nothing
    # through a foreign key.
    with op.batch_alter_table('conversations') as batch:
        batch.add_column(sa.Column('course_id', sa.String(length=32), nullable=True))
        batch.create_foreign_key(
            'fk_conversations_course_id', 'courses', ['course_id'], ['id'], ondelete='CASCADE'
        )
        batch.add_column(sa.Column('scope', sa.JSON(), nullable=True))
        batch.alter_column('chapter_id', existing_type=sa.String(length=32), nullable=True)
        batch.drop_constraint('ck_conversations_mode', type_='check')
        batch.create_check_constraint('ck_conversations_mode', "mode in ('parcours','discussion','revision')")
        batch.create_check_constraint('ck_conversations_scope', _SCOPE)
    _live_index()
    op.create_index(
        'uq_conversations_live_revision',
        'conversations',
        ['user_id', 'course_id'],
        unique=True,
        sqlite_where=sa.text("state = 'live' and mode = 'revision'"),
        postgresql_where=sa.text("state = 'live' and mode = 'revision'"),
    )
    op.create_table(
        'revision_results',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(length=32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('course_id', sa.String(length=32), sa.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chapter_id', sa.String(length=32), sa.ForeignKey('chapters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('section_id', sa.String(length=40), nullable=False),
        sa.Column('outcome', sa.String(length=8), nullable=False),
        sa.Column('content_version', sa.Integer(), nullable=False),
        sa.Column(
            'conversation_id', sa.String(length=32), sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("outcome in ('solid','shaky','todo')", name='ck_revision_results_outcome'),
    )
    op.create_index('ix_revision_results_user_course', 'revision_results', ['user_id', 'course_id'])
    # A révision turn is its own feature in the usage ledger (spec 015): a course, no chapter. Nothing points at
    # `ai_usage`, so the rebuild deletes nothing.
    with op.batch_alter_table('ai_usage') as batch:
        batch.drop_constraint('ck_ai_usage_feature', type_='check')
        batch.create_check_constraint('ck_ai_usage_feature', _features(revision=True))


def downgrade() -> None:
    # The older schema has no place for a révision: its results, its rows and its ledger rows go (the older check
    # would refuse them), the discussions, the séances and every other ledger row stay.
    op.execute("delete from ai_usage where feature = 'revision_turn'")
    with op.batch_alter_table('ai_usage') as batch:
        batch.drop_constraint('ck_ai_usage_feature', type_='check')
        batch.create_check_constraint('ck_ai_usage_feature', _features(revision=False))
    op.drop_index('ix_revision_results_user_course', table_name='revision_results')
    op.drop_table('revision_results')
    op.execute("delete from conversations where mode = 'revision'")
    op.drop_index('uq_conversations_live_revision', table_name='conversations')
    op.drop_index('uq_conversations_live', table_name='conversations')
    with op.batch_alter_table('conversations') as batch:
        batch.drop_constraint('ck_conversations_scope', type_='check')
        batch.drop_constraint('ck_conversations_mode', type_='check')
        batch.create_check_constraint('ck_conversations_mode', "mode in ('discussion','parcours')")
        batch.alter_column('chapter_id', existing_type=sa.String(length=32), nullable=False)
        batch.drop_column('scope')
        batch.drop_constraint('fk_conversations_course_id', type_='foreignkey')
        batch.drop_column('course_id')
    _live_index()
