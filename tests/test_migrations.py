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
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={"BRAIN_DB_URL": pg_url, "PATH": __import__("os").environ["PATH"]},
    )
    subprocess.run(
        ["alembic", "downgrade", "base"],
        check=True,
        env={"BRAIN_DB_URL": pg_url, "PATH": __import__("os").environ["PATH"]},
    )
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
