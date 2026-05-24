"""entities + edges (knowledge graph layer; LLM extraction in Phase 2).

Revision ID: 006_entities_edges
Revises: 005_procedures_and_events
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_entities_edges"
down_revision = "005_procedures_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("aliases", sa.ARRAY(sa.Text)),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
    )
    op.create_index("entities_kind_idx", "entities", ["kind"])

    op.create_table(
        "edges",
        sa.Column(
            "src_id", sa.BigInteger, sa.ForeignKey("entities.id"), primary_key=True
        ),
        sa.Column(
            "dst_id", sa.BigInteger, sa.ForeignKey("entities.id"), primary_key=True
        ),
        sa.Column("relation", sa.Text, primary_key=True),
        sa.Column("weight", sa.Float),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id")),
        sa.Column(
            "t_valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("edges")
    op.drop_table("entities")
