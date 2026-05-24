"""Procedures table + events table + procedure_id FK.

Revision ID: 005_procedures_and_events
Revises: 004_failure_memories
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_procedures_and_events"
down_revision = "004_failure_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procedures",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("target_situation", sa.Text, nullable=False),
        sa.Column("granularity", sa.Text, nullable=False),
        sa.Column("build_method", sa.Text, nullable=False),
        sa.Column("built_from", sa.ARRAY(sa.BigInteger)),
        sa.Column("success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_applied_at", sa.DateTime(timezone=True)),
        sa.Column("last_outcome", sa.Text),
        sa.Column("deprecated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "superseded_by",
            sa.BigInteger,
            sa.ForeignKey("procedures.id"),
        ),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "granularity IN ('step','script')",
            name="procedures_granularity_check",
        ),
        sa.CheckConstraint(
            "build_method IN ('distilled_from_episodes','user_authored','imported','llm_proposed')",
            name="procedures_build_method_check",
        ),
        sa.CheckConstraint(
            "last_outcome IS NULL OR last_outcome IN ('success','failure','partial','unknown')",
            name="procedures_last_outcome_check",
        ),
        sa.CheckConstraint(
            "superseded_by IS NULL OR superseded_by != id",
            name="procedures_no_self_supersede",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX procedures_active_unique_idx
        ON procedures (target_situation, granularity) WHERE deprecated_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX procedures_active_idx ON procedures(target_situation)
        WHERE deprecated_at IS NULL
        """
    )
    op.create_index(
        "procedures_outcome_idx",
        "procedures",
        ["last_outcome", sa.text("last_applied_at DESC")],
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("subtask_id", sa.BigInteger, sa.ForeignKey("subtasks.id")),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("sessions.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("tool", sa.Text),
        sa.Column("input_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("output_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("status", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.Column(
            "procedure_id",
            sa.BigInteger,
            sa.ForeignKey("procedures.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("session_id", "ordinal", name="events_session_ordinal_uq"),
    )
    op.create_index("events_subtask_idx", "events", ["subtask_id"])
    op.execute(
        "CREATE INDEX events_procedure_idx ON events(procedure_id) "
        "WHERE procedure_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("procedures")
