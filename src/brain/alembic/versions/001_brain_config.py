"""Brain config table + touch_updated_at trigger function.

Revision ID: 001_brain_config
Revises:
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001_brain_config"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # vector extension declared here so Phase 2 migration only needs CREATE TABLE.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.create_table(
        "brain_config",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Seed defaults. Phase 2 fills in real model_ver/dim; Phase 1 records the planned values.
    # NOTE: the JSON literal contains ":" which SQLAlchemy text() would otherwise
    # interpret as a bind parameter — bind the value explicitly to dodge that.
    op.execute(
        sa.text(
            """
            INSERT INTO brain_config(key, value) VALUES
                ('active_embedding_model_id', 'bge-m3'),
                ('active_embedding_model_ver', '2024-06'),
                ('active_embedding_dim', '1024'),
                ('tool_output_cap', :tool_output_cap),
                ('strict_mode', 'false'),
                ('sleep_time_compute', 'false');
            """
        ).bindparams(
            tool_output_cap='{"head_bytes":4096,"tail_bytes":4096,"error_span_bytes":4096}'
        )
    )


def downgrade() -> None:
    op.drop_table("brain_config")
    op.execute("DROP FUNCTION IF EXISTS touch_updated_at()")
    # Don't drop extensions — they may be used by other databases on the same cluster.
