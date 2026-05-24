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
