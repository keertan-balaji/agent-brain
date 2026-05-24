"""failure_memories.

Revision ID: 004_failure_memories
Revises: 003_sources_fts_classifications
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_failure_memories"
down_revision = "003_sources_fts_classifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failure_memories",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id"),
            nullable=False,
        ),
        sa.Column("target_problem", sa.Text, nullable=False),
        sa.Column("attempted_approach", sa.Text, nullable=False),
        sa.Column("outcome_evidence", sa.Text),
        sa.Column("root_cause", sa.Text),
        sa.Column("lesson", sa.Text),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "last_attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "first_attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
        sa.Column("invalidation_reason", sa.Text),
        sa.UniqueConstraint(
            "target_problem",
            "attempted_approach",
            name="failure_memories_problem_approach_uq",
        ),
    )
    op.execute(
        "CREATE INDEX failure_memories_problem_idx ON failure_memories "
        "USING GIN(to_tsvector('english', target_problem))"
    )
    op.execute(
        "CREATE INDEX failure_memories_approach_idx ON failure_memories "
        "USING GIN(to_tsvector('english', attempted_approach))"
    )


def downgrade() -> None:
    op.drop_table("failure_memories")
