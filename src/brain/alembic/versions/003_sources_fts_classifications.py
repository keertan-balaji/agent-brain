"""Sources + FTS + source_projects M2M + memory_classifications.

Revision ID: 003_sources_fts_classifications
Revises: 002_projects_sessions_subtasks
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

revision = "003_sources_fts_classifications"
down_revision = "002_projects_sessions_subtasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("uri", sa.Text),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.LargeBinary, nullable=False),
        sa.Column("mime", sa.Text),
        sa.Column("tokens", sa.Integer),
        sa.Column("lang", sa.Text),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
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
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
        sa.Column("invalidation_reason", sa.Text),
        sa.Column("parent_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column("span_start", sa.Integer),
        sa.Column("span_end", sa.Integer),
        sa.Column("project_id", sa.BigInteger, sa.ForeignKey("projects.id")),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column(
            "provenance_kind",
            sa.Text,
            nullable=False,
            server_default="captured",
        ),
        sa.Column("synthesized_from", sa.ARRAY(sa.BigInteger)),
        sa.Column(
            "generation_depth",
            sa.SmallInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "flags",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "provenance_kind IN ('captured','ingested','synthesized','user_authored')",
            name="sources_provenance_kind_check",
        ),
        sa.CheckConstraint(
            "status IN ('active','archived','draft')",
            name="sources_status_check",
        ),
        sa.CheckConstraint(
            "generation_depth BETWEEN 0 AND 3",
            name="sources_generation_depth_check",
        ),
    )
    op.create_index("sources_kind_idx", "sources", ["kind"])
    op.create_index(
        "sources_validity_idx", "sources", ["t_valid_from", "t_valid_to"]
    )
    op.create_index(
        "sources_provenance_idx", "sources", ["provenance_kind"]
    )
    op.create_index(
        "sources_project_idx",
        "sources",
        ["project_id"],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index("sources_status_idx", "sources", ["status"])
    op.create_index(
        "sources_hash_lookup_idx", "sources", ["content_hash"]
    )
    op.execute(
        """
        CREATE UNIQUE INDEX sources_scoped_active_idx
        ON sources (kind, COALESCE(uri,''), content_hash)
        WHERE t_valid_to IS NULL
        """
    )
    op.execute(
        """
        CREATE TRIGGER sources_touch BEFORE UPDATE ON sources
        FOR EACH ROW EXECUTE FUNCTION touch_updated_at()
        """
    )

    # Add the deferred sessions.summary_id FK now that sources exists.
    op.create_foreign_key(
        "sessions_summary_id_fk",
        "sessions",
        "sources",
        ["summary_id"],
        ["id"],
    )

    op.create_table(
        "sources_fts",
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tsv", TSVECTOR, nullable=False),
    )
    op.execute("CREATE INDEX sources_fts_idx ON sources_fts USING GIN(tsv)")

    op.create_table(
        "source_projects",
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            sa.BigInteger,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "memory_classifications",
        sa.Column(
            "source_id",
            sa.BigInteger,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bucket", sa.Text, primary_key=True),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("classifier", sa.Text, nullable=False),
        sa.CheckConstraint(
            "bucket IN ('semantic','episodic','procedural','failure')",
            name="memory_classifications_bucket_check",
        ),
    )
    op.create_index(
        "memory_classifications_bucket_idx",
        "memory_classifications",
        ["bucket"],
    )


def downgrade() -> None:
    op.drop_table("memory_classifications")
    op.drop_table("source_projects")
    op.drop_table("sources_fts")
    op.drop_constraint("sessions_summary_id_fk", "sessions", type_="foreignkey")
    op.execute("DROP TRIGGER IF EXISTS sources_touch ON sources")
    op.drop_table("sources")
