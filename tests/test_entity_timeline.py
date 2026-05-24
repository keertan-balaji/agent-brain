"""Tests for the entity_timeline helper."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.helpers.entity_timeline import entity_timeline


def test_timeline_returns_chronological_events(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind,content,content_hash) "
                "VALUES ('note','seed',sha256('et-seed'::bytea)) RETURNING id"
            )
        ).scalar()
        ent_id = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('concept','pgvector',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        pid = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('et','development') RETURNING id")
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p,'claude-code') "
                "RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        # Two events referencing the entity via source_id.
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 1, 'reflection', :src, NOW() - INTERVAL '2 hours')"
            ),
            {"s": sess_id, "src": sid},
        )
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 2, 'decision', :src, NOW() - INTERVAL '1 hour')"
            ),
            {"s": sess_id, "src": sid},
        )
    items = entity_timeline(engine, ent_id)
    # 2 events + 1 source (the entity's seed source) = 3 items
    assert len(items) == 3
    # The two events come first (older than the seed source's NOW())
    event_items = [it for it in items if it.role == "event"]
    assert len(event_items) == 2
    # Chronological ordering across the full list
    for i in range(len(items) - 1):
        assert items[i].occurred_at <= items[i + 1].occurred_at


def test_timeline_filters_by_date_range(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind,content,content_hash) "
                "VALUES ('note','x',sha256('et-range'::bytea)) RETURNING id"
            )
        ).scalar()
        ent_id = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('concept','et2',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        pid = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('et2','development') RETURNING id")
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p,'claude-code') RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 1, 'note', :src, NOW() - INTERVAL '10 days')"
            ),
            {"s": sess_id, "src": sid},
        )
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, source_id, occurred_at) "
                "VALUES (:s, 2, 'note', :src, NOW() - INTERVAL '1 hour')"
            ),
            {"s": sess_id, "src": sid},
        )
    items = entity_timeline(
        engine,
        ent_id,
        from_ts=datetime.now(timezone.utc) - timedelta(days=2),
    )
    # Only the recent event (1 hour ago) + the seed source (NOW()) survive the from_ts cutoff
    # — the 10-day-old event is excluded
    assert len(items) == 2
