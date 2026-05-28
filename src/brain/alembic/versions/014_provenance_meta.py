"""sources.provenance_meta JSONB + GIN index on source_files for staleness lookups (v0.9.0).

Revision ID: 014_provenance_meta
Revises: 013_drop_event_kind_check
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "014_provenance_meta"
down_revision = "013_drop_event_kind_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("provenance_meta", JSONB(), nullable=True),
    )
    op.execute(
        "CREATE INDEX sources_provenance_files_gin_idx "
        "ON sources USING GIN ((provenance_meta->'source_files'))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sources_provenance_files_gin_idx")
    op.drop_column("sources", "provenance_meta")
