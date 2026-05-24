"""Shared pytest fixtures."""

import os

import pytest


@pytest.fixture(scope="session")
def pg_url() -> str:
    """Connection URL for the dev Postgres instance.

    Phase 1 uses the docker-compose Postgres directly for tests; pytest-postgresql
    integration is added in Task 3 once we have migrations to apply.
    """
    url = os.environ.get(
        "BRAIN_TEST_DB_URL",
        "postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain",
    )
    return url
