"""Migration 014: sources.provenance_meta JSONB + GIN index on source_files."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope


def test_provenance_meta_column_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'sources' AND column_name = 'provenance_meta'"
            )
        ).first()
    assert row is not None
    assert row.data_type == "jsonb"


def test_provenance_files_gin_index_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "  AND tablename = 'sources' "
                "  AND indexname = 'sources_provenance_files_gin_idx'"
            )
        ).scalar()
    assert n == 1


def test_provenance_meta_defaults_null(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('note', 'no provenance', sha256('test'::bytea), 'active') RETURNING id"
            )
        )
        row = s.execute(
            text(
                "SELECT provenance_meta FROM sources "
                "WHERE content = 'no provenance' LIMIT 1"
            )
        ).first()
    assert row is not None
    assert row.provenance_meta is None
