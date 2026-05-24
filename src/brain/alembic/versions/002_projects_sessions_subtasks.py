"""Projects, sessions, subtasks.

Revision ID: 002_projects_sessions_subtasks
Revises: 001_brain_config
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_projects_sessions_subtasks"
down_revision = "001_brain_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column(
            "task_type",
            sa.Text,
            nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("repo_root", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "task_type IN ('development','research','repo-analysis','generic')",
            name="projects_task_type_check",
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("summary_id", sa.BigInteger),  # FK to sources added in 003
    )

    op.create_table(
        "subtasks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("sessions.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("goal", sa.Text),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.Text),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('success','failure','abandoned','in_progress')",
            name="subtasks_outcome_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("subtasks")
    op.drop_table("sessions")
    op.drop_table("projects")
