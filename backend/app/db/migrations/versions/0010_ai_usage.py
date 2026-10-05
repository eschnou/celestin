"""spec 015: the AI usage ledger; voice_usage is carried into it and dropped

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-05 09:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ai_usage',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('course_id', sa.String(length=32), nullable=True),
    sa.Column('chapter_id', sa.String(length=32), nullable=True),
    sa.Column('correlation_id', sa.String(length=32), nullable=True),
    sa.Column('role', sa.String(length=14), nullable=False),
    sa.Column('feature', sa.String(length=16), nullable=False),
    sa.Column('model', sa.String(length=200), nullable=False),
    sa.Column('provider', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('error_code', sa.String(length=40), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('ttft_ms', sa.Integer(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('cached_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('reasoning_tokens', sa.Integer(), nullable=True),
    sa.Column('input_audio_tokens', sa.Integer(), nullable=True),
    sa.Column('output_audio_tokens', sa.Integer(), nullable=True),
    sa.Column('audio_seconds', sa.Float(), nullable=True),
    sa.Column('cost_usd', sa.Float(), nullable=True),
    sa.CheckConstraint("role in ('tutor','authoring','transcription','voice')", name='ck_ai_usage_role'),
    sa.CheckConstraint(
        "feature in ('tutor_turn','discussion_turn','authoring','document_reading','work_reading',"
        "'dictation','voice_session','ai_test')",
        name='ck_ai_usage_feature',
    ),
    sa.CheckConstraint("status in ('ok','failed','truncated','cancelled')", name='ck_ai_usage_status'),
    sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.create_index('ix_ai_usage_chapter', ['chapter_id'], unique=False)
        batch_op.create_index('ix_ai_usage_correlation', ['correlation_id'], unique=False)
        batch_op.create_index('ix_ai_usage_course', ['course_id'], unique=False)
        batch_op.create_index('ix_ai_usage_created', ['created_at'], unique=False)
        batch_op.create_index('ix_ai_usage_user_created', ['user_id', 'created_at'], unique=False)

    # The sessions voice_usage held, as ledger rows. Their cost was an estimate from environment prices, not a
    # figure the provider reported: it is not carried. The model is unknown for them.
    op.execute(
        "INSERT INTO ai_usage (created_at, user_id, correlation_id, role, feature, model, provider, status, "
        "error_code, input_tokens, cached_tokens, output_tokens, input_audio_tokens, output_audio_tokens, "
        "audio_seconds) "
        "SELECT created_at, user_id, session_id, 'voice', 'voice_session', '', '', "
        "CASE WHEN reason = 'error' THEN 'failed' ELSE 'ok' END, "
        "CASE WHEN reason = 'error' THEN 'voice_error' ELSE NULL END, "
        "input_text + input_audio, cached_text + cached_audio, output_text + output_audio, "
        "input_audio, output_audio, duration_s "
        "FROM voice_usage"
    )
    op.drop_table('voice_usage')


def downgrade() -> None:
    op.create_table('voice_usage',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=False),
    sa.Column('session_id', sa.String(length=32), nullable=False),
    sa.Column('reason', sa.String(length=8), nullable=False),
    sa.Column('duration_s', sa.Integer(), nullable=False),
    sa.Column('responses', sa.Integer(), nullable=False),
    sa.Column('input_text', sa.Integer(), nullable=False),
    sa.Column('input_audio', sa.Integer(), nullable=False),
    sa.Column('cached_text', sa.Integer(), nullable=False),
    sa.Column('cached_audio', sa.Integer(), nullable=False),
    sa.Column('output_text', sa.Integer(), nullable=False),
    sa.Column('output_audio', sa.Integer(), nullable=False),
    sa.Column('cost_estimate_usd', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # Best effort: what the ledger did not keep (the reason, the response count, the text/audio split of the
    # cached tokens, the estimated cost) is rebuilt from what it did.
    op.execute(
        "INSERT INTO voice_usage (user_id, session_id, reason, duration_s, responses, input_text, input_audio, "
        "cached_text, cached_audio, output_text, output_audio, cost_estimate_usd, created_at) "
        "SELECT user_id, COALESCE(correlation_id, ''), CASE WHEN status = 'failed' THEN 'error' ELSE 'learner' END, "
        "CAST(COALESCE(audio_seconds, 0) AS INTEGER), 0, "
        "COALESCE(input_tokens, 0) - COALESCE(input_audio_tokens, 0), COALESCE(input_audio_tokens, 0), "
        "COALESCE(cached_tokens, 0), 0, "
        "COALESCE(output_tokens, 0) - COALESCE(output_audio_tokens, 0), COALESCE(output_audio_tokens, 0), "
        "0.0, created_at "
        "FROM ai_usage WHERE feature = 'voice_session'"
    )
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_usage_user_created')
        batch_op.drop_index('ix_ai_usage_created')
        batch_op.drop_index('ix_ai_usage_course')
        batch_op.drop_index('ix_ai_usage_correlation')
        batch_op.drop_index('ix_ai_usage_chapter')
    op.drop_table('ai_usage')
