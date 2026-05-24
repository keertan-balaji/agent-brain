"""Drop LLM-coupling artifacts (cost_log table + reasoning_cache LLM columns).

Phase 2.5 pivots reasoning helpers from embedded-Haiku to agent-driven, so
per-call cost tracking and per-model cache keying become dead weight.

Existing reasoning_cache rows are truncated because their cache_key hashes
include model_id/model_ver and would be unreachable after the column drop.

Revision ID: 009_drop_llm_coupling
Revises: 008_phase2_tables
"""

from __future__ import annotations

from alembic import op

revision = "009_drop_llm_coupling"
down_revision = "008_phase2_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE reasoning_cache")
    op.drop_column("reasoning_cache", "llm_model_id")
    op.drop_column("reasoning_cache", "llm_model_ver")
    op.drop_column("reasoning_cache", "tokens_used")
    op.execute("DROP INDEX IF EXISTS cost_log_session_idx")
    op.drop_table("cost_log")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "cost_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id")),
        sa.Column("helper", sa.Text, nullable=False),
        sa.Column("llm_model", sa.Text, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("usd", sa.Float, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("cost_log_session_idx", "cost_log", ["session_id", "occurred_at"])
    op.add_column("reasoning_cache", sa.Column("llm_model_id", sa.Text, nullable=True))
    op.add_column("reasoning_cache", sa.Column("llm_model_ver", sa.Text, nullable=True))
    op.add_column(
        "reasoning_cache",
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
    )
