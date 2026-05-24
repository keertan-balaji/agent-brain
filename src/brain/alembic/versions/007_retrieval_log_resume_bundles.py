"""retrieval_log + session_resume_bundles.

Revision ID: 007_retrieval_log_resume_bundles
Revises: 006_entities_edges
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007_retrieval_log_resume_bundles"
down_revision = "006_entities_edges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retrieval_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("filters", postgresql.JSONB),
        sa.Column("candidates", postgresql.JSONB),
        sa.Column("selected", sa.ARRAY(sa.BigInteger)),
        sa.Column("synthesized_ratio", sa.Float),
        sa.Column("captured_ratio", sa.Float),
        sa.Column(
            "abstained", sa.Boolean, nullable=False, server_default=sa.text("FALSE")
        ),
        sa.Column("top1_score", sa.Float),
        sa.Column("agent", sa.Text),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id")),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "retrieval_log_session_idx", "retrieval_log", ["session_id", "occurred_at"]
    )

    op.create_table(
        "session_resume_bundles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.BigInteger,
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id")),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("token_budget", sa.Integer, nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("rendered", sa.Text, nullable=False),
        sa.CheckConstraint(
            "trigger IN ('pre_compact','session_end','manual')",
            name="session_resume_bundles_trigger_check",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX bundles_project_active_unique_idx
        ON session_resume_bundles(project_id) WHERE superseded_at IS NULL
        """
    )
    op.create_index(
        "bundles_project_idx",
        "session_resume_bundles",
        ["project_id", sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("session_resume_bundles")
    op.drop_table("retrieval_log")
