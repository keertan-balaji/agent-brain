"""Shared pytest fixtures: a fresh per-session DB with all migrations applied.

BUGS.md entry 2026-05-27 documents the data-loss bug fixed here: the test
suite previously defaulted to the dev `brain` DB. Per-test TRUNCATE +
per-session `alembic downgrade base` wiped real captures every test run.

The new default points at a separate `brain_test` database on the same
container. The fixture below auto-creates `brain_test` if it doesn't
exist, then runs migrations against it. Override via BRAIN_TEST_DB_URL
if you need a different test DB.
"""

import os
import subprocess

import pytest


_DEFAULT_TEST_URL = "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain_test"


def _ensure_test_db_exists(url: str) -> None:
    """If the test DB doesn't exist, create it via the postgres superuser DB.

    Safe to call repeatedly — CREATE DATABASE is idempotent via the IF NOT EXISTS
    check (Postgres doesn't support that syntax for CREATE DATABASE, so we test
    for existence via pg_database first).
    """
    from urllib.parse import urlparse

    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    db_name = parsed.path.lstrip("/")
    admin_url = url.replace(f"/{db_name}", "/postgres")

    from sqlalchemy import create_engine, text as sql_text

    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                sql_text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": db_name},
            ).scalar()
            if not exists:
                conn.execute(sql_text(f'CREATE DATABASE "{db_name}"'))
                # Install pgvector + pg_trgm so migrations have them available.
    finally:
        admin.dispose()

    target = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with target.connect() as conn:
            conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    finally:
        target.dispose()


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.environ.get("BRAIN_TEST_DB_URL", _DEFAULT_TEST_URL)
    if "/brain_test" not in url and url == _DEFAULT_TEST_URL:
        # Defensive — should never trigger since we set _DEFAULT_TEST_URL above.
        raise RuntimeError("test pg_url must not point at the dev brain DB")
    return url


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(pg_url: str) -> None:
    """Run alembic downgrade base + upgrade head once per test session."""
    _ensure_test_db_exists(pg_url)
    env = {**os.environ, "BRAIN_DB_URL": pg_url}
    subprocess.run(["alembic", "downgrade", "base"], check=False, env=env)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)


@pytest.fixture(autouse=True)
def _truncate_tables(pg_url: str) -> None:
    """Truncate all data tables after each test to prevent cross-test pollution.

    Migration state (brain_config, alembic_version) is preserved. This runs AFTER
    each test (yield first) so the test itself sees a fresh schema with whatever
    fixtures/setup it does.

    Subprocess-based hook tests can leave row-level locks that briefly conflict
    with TRUNCATE — retry on DeadlockDetected with a small backoff. BUGS.md
    entry 2026-05-27 documents the race.
    """
    yield
    import time

    from sqlalchemy import create_engine, text as sql_text
    from sqlalchemy.exc import OperationalError

    engine = create_engine(pg_url)
    try:
        for attempt in range(5):
            try:
                with engine.begin() as conn:
                    # statement_timeout caps how long TRUNCATE will wait for the
                    # blocking lock before raising — avoids hanging the whole suite.
                    conn.execute(sql_text("SET LOCAL statement_timeout = '3s'"))
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
                                reasoning_cache,
                                session_events
                            RESTART IDENTITY CASCADE
                            """
                        )
                    )
                    # brain_config is intentionally not TRUNCATEd (preserves seeded
                    # constants), but transient/testable rows like strict_mode must
                    # not leak across tests. Reset to the seed default rather than
                    # deleting — test_upgrade_head_creates_brain_config asserts the
                    # seeded row exists.
                    conn.execute(
                        sql_text(
                            "UPDATE brain_config SET value = 'false', updated_at = NOW() "
                            "WHERE key = 'strict_mode' AND value <> 'false'"
                        )
                    )
                break
            except OperationalError as exc:
                msg = str(exc).lower()
                if "deadlock" in msg or "lock timeout" in msg or "statement timeout" in msg:
                    if attempt == 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
    finally:
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
