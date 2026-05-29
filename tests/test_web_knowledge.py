"""Knowledge graph page + knowledge_graph_data query (v0.11.1)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.app import create_app
from brain.web.queries import knowledge_graph_data


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_knowledge_graph_data_empty_brain_returns_empty_shape(pg_url: str) -> None:
    engine = get_engine(pg_url)
    g = knowledge_graph_data(engine, limit=50)
    assert g.nodes == []
    assert g.edges == []


def test_knowledge_graph_data_returns_substantive_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("graph-source")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'graph-source', :h, 'active')"
            ),
            {"h": h},
        )
    g = knowledge_graph_data(engine, limit=50)
    assert len(g.nodes) >= 1
    assert any(n.label.startswith("decision") or n.kind == "decision" for n in g.nodes)


def test_knowledge_page_renders(client: TestClient) -> None:
    res = client.get("/knowledge")
    assert res.status_code == 200
    # Cytoscape CDN must be loaded for the graph to render client-side.
    assert "cytoscape" in res.text.lower()
    # The data endpoint URL must be embedded so the client can fetch it.
    assert "/_htmx/knowledge.json" in res.text


def test_knowledge_json_endpoint_returns_valid_json(client: TestClient) -> None:
    res = client.get("/_htmx/knowledge.json")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
