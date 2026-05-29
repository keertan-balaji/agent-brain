"""Recall page render + search smoke (v0.11.1)."""

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


def test_recall_page_renders_empty_state(client: TestClient) -> None:
    res = client.get("/recall")
    assert res.status_code == 200
    # The page shows the query input + an empty-state when no q is set.
    assert 'name="q"' in res.text
    assert "Memory Retrieval" in res.text  # page title from the mockup


def test_recall_page_runs_query_and_shows_hits(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("recall-target-unique-phrase")
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'recall-target-unique-phrase', :h, 'active') RETURNING id"
            ),
            {"h": h},
        ).scalar()
        # Materialize FTS row so plainto_tsquery can match it.
        s.execute(
            text(
                "INSERT INTO sources_fts(source_id, tsv) "
                "VALUES (:s, to_tsvector('english', 'recall-target-unique-phrase'))"
            ),
            {"s": sid},
        )
    res = client.get("/recall?q=recall-target-unique-phrase")
    assert res.status_code == 200
    assert "recall-target-unique-phrase" in res.text
    # At least one hit card is rendered — the partial uses class "recall-hit".
    assert "recall-hit" in res.text


def test_recall_page_no_match_shows_empty_state(client: TestClient) -> None:
    res = client.get("/recall?q=zzz-no-such-phrase-anywhere")
    assert res.status_code == 200
    assert "No matches" in res.text or "0 matches" in res.text


def test_favicon_returns_204(client: TestClient) -> None:
    res = client.get("/favicon.ico")
    assert res.status_code == 204
