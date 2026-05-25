"""Session lifecycle: cc_session_id + cwd on sessions, consumed_at + cwd on
session_resume_bundles, new session_events table.

Revision ID: 010_session_lifecycle
Revises: 009_drop_llm_coupling
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010_session_lifecycle"
down_revision = "009_drop_llm_coupling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("cc_session_id", sa.Text, nullable=True))
    op.add_column("sessions", sa.Column("cwd", sa.Text, nullable=True))
    op.create_index("sessions_cc_session_id_idx", "sessions", ["cc_session_id"])
    op.create_index("sessions_cwd_idx", "sessions", ["cwd"])

    op.add_column(
        "session_resume_bundles",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_resume_bundles",
        sa.Column("cwd", sa.Text, nullable=False, server_default=""),
    )
    op.execute(
        """
        CREATE INDEX bundles_cwd_unconsumed_idx
        ON session_resume_bundles(cwd, generated_at DESC)
        WHERE consumed_at IS NULL AND superseded_at IS NULL
        """
    )

    op.create_table(
        "session_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_kind", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "event_kind IN ('session_start','session_end','user_prompt_submit','stop','pre_compact','hook_error')",
            name="session_events_kind_check",
        ),
    )
    op.create_index(
        "session_events_session_idx",
        "session_events",
        ["session_id", sa.text("occurred_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("session_events_session_idx", table_name="session_events")
    op.drop_table("session_events")
    op.execute("DROP INDEX IF EXISTS bundles_cwd_unconsumed_idx")
    op.drop_column("session_resume_bundles", "cwd")
    op.drop_column("session_resume_bundles", "consumed_at")
    op.drop_index("sessions_cwd_idx", table_name="sessions")
    op.drop_index("sessions_cc_session_id_idx", table_name="sessions")
    op.drop_column("sessions", "cwd")
    op.drop_column("sessions", "cc_session_id")
