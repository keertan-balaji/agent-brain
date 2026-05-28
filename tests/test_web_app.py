"""FastAPI web app smoke tests (v0.11.0)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from brain.web.app import create_app


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_app_factory_returns_fastapi_instance(pg_url: str) -> None:
    app = create_app(db_url=pg_url)
    assert app is not None
    assert app.title == "agent-brain"


def test_dashboard_route_returns_200(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    # The hero metric must appear somewhere on the page.
    assert "hero-value" in res.text


def test_static_files_served(client: TestClient) -> None:
    res = client.get("/static/app.css")
    assert res.status_code == 200
    # app.css holds Crimson Matrix overrides (scrollbar, scanline, MS icons).
    assert "crimson-scanline" in res.text
