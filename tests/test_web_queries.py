"""Query functions backing the Telescope frontend (v0.11.0)."""

from __future__ import annotations

from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.queries import (
    dashboard_stats,
    list_sources,
    source_by_id,
)


def _seed_decision(engine, content: str, uri: str | None = None) -> int:
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


def test_dashboard_stats_empty_brain_returns_zeros(pg_url: str) -> None:
    engine = get_engine(pg_url)
    stats = dashboard_stats(engine)
    assert stats.hero.total == 0
    assert stats.hero.delta_week == 0


def test_dashboard_stats_counts_substantive_captures(pg_url: str) -> None:
    engine = get_engine(pg_url)
    _seed_decision(engine, "d1")
    _seed_decision(engine, "d2")
    stats = dashboard_stats(engine)
    assert stats.hero.total >= 2
    # Breakdown carries per-kind counts.
    assert stats.capture_cadence.by_kind.get("decision", 0) >= 2


def test_list_sources_default_returns_substantive_kinds(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_decision(engine, "browse-me", uri="decision://test-1")
    page = list_sources(engine, kind=None, page=1, per_page=20)
    ids = {row.id for row in page.rows}
    assert sid in ids
    assert page.total >= 1


def test_list_sources_filtered_by_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_decision(engine, "filter-me", uri="decision://test-2")
    page = list_sources(engine, kind="decision", page=1, per_page=20)
    assert sid in {r.id for r in page.rows}
    page_g = list_sources(engine, kind="gotcha", page=1, per_page=20)
    assert sid not in {r.id for r in page_g.rows}


def test_source_by_id_returns_full_detail(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_decision(engine, "detail-me", uri="decision://detail-1")
    src = source_by_id(engine, source_id=sid)
    assert src.id == sid
    assert src.content == "detail-me"
    assert src.uri == "decision://detail-1"


def test_source_by_id_returns_none_when_absent(pg_url: str) -> None:
    engine = get_engine(pg_url)
    assert source_by_id(engine, source_id=999_999) is None
