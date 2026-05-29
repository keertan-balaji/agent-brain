"""Health page + health_stats query (v0.11.1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.app import create_app
from brain.web.queries import HealthStats, health_stats


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_health_stats_returns_model_on_empty_brain(pg_url: str) -> None:
    engine = get_engine(pg_url)
    stats = health_stats(engine)
    assert isinstance(stats, HealthStats)
    assert stats.sources_total >= 0
    assert stats.pool.size >= 1
    assert stats.embedding.percent >= 0


def test_health_stats_counts_real_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("health-target")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'health-target', :h, 'active')"
            ),
            {"h": h},
        )
    stats = health_stats(engine)
    assert stats.sources_substantive >= 1
    assert stats.captures_24h >= 1


def test_health_page_renders(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    # Mockup uses "System Observability" as the H2.
    assert "Observability" in res.text or "System Health" in res.text
    # Should display the substantive-sources tile.
    assert "Substantive" in res.text or "Sources" in res.text
