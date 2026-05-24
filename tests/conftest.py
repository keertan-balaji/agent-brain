"""Shared pytest fixtures: a fresh per-session DB with all migrations applied."""

import os
import subprocess

import pytest


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.environ.get(
        "BRAIN_TEST_DB_URL",
        "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain",
    )
    return url


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(pg_url: str) -> None:
    """Run alembic downgrade base + upgrade head once per test session."""
    env = {**os.environ, "BRAIN_DB_URL": pg_url}
    subprocess.run(["alembic", "downgrade", "base"], check=False, env=env)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)


@pytest.fixture(autouse=True)
def _truncate_tables(pg_url: str) -> None:
    """Truncate all data tables after each test to prevent cross-test pollution.

    Migration state (brain_config, alembic_version) is preserved. This runs AFTER
    each test (yield first) so the test itself sees a fresh schema with whatever
    fixtures/setup it does.
    """
    yield
    # Truncate in dependency-safe order via CASCADE.
    from sqlalchemy import create_engine, text as sql_text

    engine = create_engine(pg_url)
    with engine.begin() as conn:
        # CASCADE handles FK chains automatically. Skip brain_config (seeded constants).
        conn.execute(
            sql_text(
                """
                TRUNCATE TABLE
                    session_resume_bundles, retrieval_log,
                    edges, entities,
                    events, procedures,
                    failure_memories,
                    memory_classifications, source_projects, sources_fts,
                    sources,
                    subtasks, sessions, projects,
                    reasoning_cache
                RESTART IDENTITY CASCADE
                """
            )
        )
    engine.dispose()


@pytest.fixture(scope="session")
def bge_m3_embedder():
    """Session-scoped BGE-M3 dense embedder. Loads model once (~5s after first download)."""
    from brain.embed.bge_m3 import BgeM3Embedder

    return BgeM3Embedder()


@pytest.fixture(scope="session")
def mxbai_reranker():
    """Session-scoped mxbai cross-encoder. First use downloads weights (~1GB)."""
    from brain.retrieval.rerank import MxbaiReranker

    return MxbaiReranker()
