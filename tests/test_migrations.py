"""Verify alembic upgrade head + downgrade base cycle is clean."""

import subprocess

from sqlalchemy import text

from brain.db import get_engine


def test_upgrade_head_creates_brain_config(pg_url: str) -> None:
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={"BRAIN_DB_URL": pg_url, "PATH": __import__("os").environ["PATH"]},
    )
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT key, value FROM brain_config ORDER BY key")
        ).fetchall()
    keys = {r[0] for r in rows}
    assert "active_embedding_model_id" in keys
    assert "active_embedding_model_ver" in keys
    assert "active_embedding_dim" in keys
    assert "tool_output_cap" in keys
    assert "strict_mode" in keys


def test_downgrade_base_drops_brain_config(pg_url: str) -> None:
    env = {"BRAIN_DB_URL": pg_url, "PATH": __import__("os").environ["PATH"]}
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    subprocess.run(["alembic", "downgrade", "base"], check=True, env=env)
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        existing = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).fetchall()
    table_names = {r[0] for r in existing}
    assert "brain_config" not in table_names
    assert "alembic_version" in table_names  # alembic's own tracking table is kept
    # Restore head so subsequent tests (which rely on the session-scoped fixture
    # having applied migrations) still see a populated schema.
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)


def test_phase2_tables_exist(pg_url: str) -> None:
    """embeddings_1024, extracted_claims, reasoning_cache (cost_log dropped in 009)."""
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        existing = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).fetchall()
    table_names = {r[0] for r in existing}
    for required in ("embeddings_1024", "extracted_claims", "reasoning_cache"):
        assert required in table_names, f"missing Phase 2 table: {required}"


def test_embeddings_hnsw_index_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'embeddings_1024'"
            )
        ).fetchall()
    idx = {r[0] for r in rows}
    assert "embeddings_1024_hnsw_idx" in idx


def test_phase2_5_drops_cost_log(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        ).fetchall()
    names = {r[0] for r in rows}
    assert "cost_log" not in names, "cost_log should be dropped in migration 009"


def test_phase2_5_drops_reasoning_cache_llm_columns(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='reasoning_cache'"
            )
        ).fetchall()
    col_names = {r[0] for r in cols}
    for dead in ("llm_model_id", "llm_model_ver", "tokens_used"):
        assert dead not in col_names, f"{dead} should be dropped by migration 009"
    for kept in ("cache_key", "helper_name", "input_hash", "prompt_ver", "output_json", "hit_count"):
        assert kept in col_names
