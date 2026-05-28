"""Verify production templates render expected content (v0.11.0)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.app import create_app


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_dashboard_renders_hero_value(client: TestClient, pg_url: str) -> None:
    import re
    engine = get_engine(pg_url)
    h = sha256_bytes("test-decision")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'test-decision', :h, 'active')"
            ),
            {"h": h},
        )
    res = client.get("/")
    assert res.status_code == 200
    m = re.search(r'class="[^"]*hero-value[^"]*"[^>]*>\s*(\d+)', res.text)
    assert m is not None, "hero-value element with integer content not found"
    assert int(m.group(1)) >= 1, f"expected hero >= 1 after inserting a decision, got {m.group(1)}"


def test_sources_lists_recently_inserted(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("sources-page")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES ('decision', 'sources-page', :h, 'active', 'decision://test-sources-page')"
            ),
            {"h": h},
        )
    res = client.get("/sources")
    assert res.status_code == 200
    assert "decision://test-sources-page" in res.text
    assert "sources-page" in res.text


def test_source_detail_renders_content(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("detail-content")
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'detail-content', :h, 'active') RETURNING id"
            ),
            {"h": h},
        ).scalar()
    res = client.get(f"/sources/{int(sid)}")
    assert res.status_code == 200
    assert "detail-content" in res.text


def test_source_detail_404_for_missing(client: TestClient) -> None:
    res = client.get("/sources/999999")
    assert res.status_code == 404


def test_dashboard_topbar_renders_page_title(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    # Dashboard's {% block page_title %}Dashboard{% endblock %} must reach the topbar.
    assert "Dashboard" in res.text


def test_sources_topbar_renders_page_title(client: TestClient) -> None:
    res = client.get("/sources")
    assert res.status_code == 200
    assert "Sources" in res.text
