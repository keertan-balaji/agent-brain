"""Action-bar API endpoints (v0.11.0): invalidate + detail-page wiring."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.app import create_app


@pytest.fixture
def client(pg_url: str) -> TestClient:
    return TestClient(create_app(db_url=pg_url))


def _seed(engine, content: str, *, uri: str | None = None) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES ('decision', :c, :h, 'active', :u) RETURNING id"
            ),
            {"c": content, "h": h, "u": uri},
        ).scalar()
    return int(sid)


def test_invalidate_sets_t_valid_to(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed(engine, "kill-me", uri="decision://kill-me")

    res = client.post(f"/api/sources/{sid}/invalidate")
    assert res.status_code == 200
    assert "Invalidated" in res.text

    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT t_valid_to FROM sources WHERE id = :i"), {"i": sid}
        ).first()
    assert row.t_valid_to is not None


def test_invalidate_twice_returns_404(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed(engine, "twice", uri="decision://twice")
    assert client.post(f"/api/sources/{sid}/invalidate").status_code == 200
    assert client.post(f"/api/sources/{sid}/invalidate").status_code == 404


def test_invalidate_missing_returns_404(client: TestClient) -> None:
    assert client.post("/api/sources/9999999/invalidate").status_code == 404


def test_detail_page_wires_invalidate_button(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed(engine, "wire-me", uri="decision://wire-me")
    res = client.get(f"/sources/{sid}")
    assert res.status_code == 200
    assert f'hx-post="/api/sources/{sid}/invalidate"' in res.text
    assert 'hx-target="#action-bar-status"' in res.text


def test_detail_page_open_in_recall_links_to_recall_q(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed(engine, "recall-me-with-unique-phrase", uri="decision://recall-me")
    res = client.get(f"/sources/{sid}")
    assert res.status_code == 200
    # v0.12.1: "Open in recall" now points at the live /recall page (shipped
    # in v0.11.1), seeded with the first 80 chars of source.content
    # (URL-encoded). The original action-bar branch pointed at the
    # sources-list-by-id fallback because /recall didn't exist yet.
    assert 'href="/recall?q=' in res.text
    assert "recall-me-with-unique-phrase" in res.text
