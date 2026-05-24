"""Phase 2 tables: embeddings_1024 (pgvector HNSW), extracted_claims, reasoning_cache, cost_log.

Revision ID: 008_phase2_tables
Revises: 007_retrieval_log_resume_bundles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_phase2_tables"
down_revision = "007_retrieval_log_resume_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE embeddings_1024 (
            source_id   BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            model_id    TEXT NOT NULL,
            model_ver   TEXT NOT NULL,
            vec         HALFVEC(1024) NOT NULL,
            embedded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source_id, model_id, model_ver)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX embeddings_1024_hnsw_idx ON embeddings_1024
            USING hnsw (vec halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)
        """
    )
    op.create_index(
        "embeddings_1024_active_idx", "embeddings_1024", ["model_id", "model_ver"]
    )

    op.create_table(
        "extracted_claims",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("predicate", sa.Text, nullable=False),
        sa.Column("object", sa.Text, nullable=False),
        sa.Column("qualifier", sa.Text),
        sa.Column("evidence_span_start", sa.Integer, nullable=False),
        sa.Column("evidence_span_end", sa.Integer, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("extracted_by_model", sa.Text, nullable=False),
        sa.Column(
            "extracted_at",
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
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="extracted_claims_confidence_check"
        ),
    )
    op.execute(
        "CREATE INDEX extracted_claims_subject_idx ON extracted_claims "
        "USING GIN(to_tsvector('english', subject))"
    )

    op.create_table(
        "reasoning_cache",
        sa.Column("cache_key", sa.LargeBinary, primary_key=True),
        sa.Column("helper_name", sa.Text, nullable=False),
        sa.Column("input_hash", sa.LargeBinary, nullable=False),
        sa.Column("llm_model_id", sa.Text, nullable=False),
        sa.Column("llm_model_ver", sa.Text, nullable=False),
        sa.Column("prompt_ver", sa.Text, nullable=False),
        sa.Column("output_json", postgresql.JSONB, nullable=False),
        sa.Column("tokens_used", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index(
        "reasoning_cache_helper_idx", "reasoning_cache", ["helper_name", "input_hash"]
    )

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


def downgrade() -> None:
    op.drop_table("cost_log")
    op.drop_table("reasoning_cache")
    op.drop_table("extracted_claims")
    op.drop_table("embeddings_1024")
