"""Bundle selection: gather decisions/gotchas/patterns/failures/subtasks/events."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.hooks.bundle import BundleSelection, gather_bundle_selection
from brain.hooks.events import record_event
from brain.hooks.session import start_session
from brain.schemas import SourceInput
from brain.write import write


def test_bundle_selection_picks_recent_kinds(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="b1", cwd="/x", agent="cc", source="startup")

    write(engine, SourceInput(kind="decision", content="chose pgvector"))
    write(engine, SourceInput(kind="gotcha", content="::jsonb collides with bind params"))
    write(engine, SourceInput(kind="pattern", content="CAST(:x AS jsonb)"))
    write(engine, SourceInput(kind="note", content="unrelated note"))

    record_event(engine, session_id=sid, event_kind="user_prompt_submit", payload={"prompt": "p1"})
    record_event(engine, session_id=sid, event_kind="stop")

    sel = gather_bundle_selection(engine, session_id=sid, cwd="/x", limit_per_kind=10)
    assert isinstance(sel, BundleSelection)

    decision_heads = [d["head"] for d in sel.decisions]
    assert any("pgvector" in h for h in decision_heads)

    gotcha_heads = [g["head"] for g in sel.gotchas]
    assert any("jsonb" in h for h in gotcha_heads)

    pattern_heads = [p["head"] for p in sel.patterns]
    assert any("CAST" in h for h in pattern_heads)

    # Recent events: 2 of them
    assert len(sel.recent_events) >= 2
    assert any(e["event_kind"] == "stop" for e in sel.recent_events)


def test_bundle_selection_respects_limit(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="b2", cwd="/y", agent="cc", source="startup")
    for i in range(15):
        write(engine, SourceInput(kind="gotcha", content=f"gotcha number {i}"))
    sel = gather_bundle_selection(engine, session_id=sid, cwd="/y", limit_per_kind=5)
    assert len(sel.gotchas) == 5


def test_bundle_selection_empty_when_no_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="b3", cwd="/z", agent="cc", source="startup")
    sel = gather_bundle_selection(engine, session_id=sid, cwd="/z", limit_per_kind=10)
    assert sel.decisions == []
    assert sel.gotchas == []
    assert sel.patterns == []
    assert sel.failures == []
    assert sel.subtasks_open == []
    assert sel.recent_events == []


def test_gather_picks_up_staleness_detected_event(pg_url: str) -> None:
    """gather_bundle_selection pulls the most recent staleness_detected event payload
    for the given session into selection.stale_sources."""
    import json as _json

    from sqlalchemy import text as _text

    from brain.content_hash import sha256_bytes
    from brain.db import get_engine, session_scope

    engine = get_engine(pg_url)
    # Seed: a session, a sources row, a staleness_detected session_event.
    with session_scope(engine) as s:
        sid = s.execute(
            _text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', NOW(), 'cc-bundle-stale', '/tmp/r') RETURNING id"
            )
        ).scalar()
        h = sha256_bytes("about /tmp/foo.py")
        src_id = s.execute(
            _text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'about /tmp/foo.py', :h, 'active') RETURNING id"
            ),
            {"h": h},
        ).scalar()
        payload = {
            "stale_count": 1,
            "scanned_sources": 5,
            "scanned_files": 1,
            "stale_sources": [
                {"source_id": int(src_id), "kind": "decision", "path": "/tmp/foo.py", "status": "changed"},
            ],
        }
        s.execute(
            _text(
                "INSERT INTO session_events(session_id, event_kind, payload) "
                "VALUES (:sid, 'staleness_detected', CAST(:p AS jsonb))"
            ),
            {"sid": int(sid), "p": _json.dumps(payload)},
        )

    sel = gather_bundle_selection(engine, session_id=int(sid), cwd="/tmp/r")
    assert len(sel.stale_sources) == 1
    assert sel.stale_sources[0]["source_id"] == int(src_id)
    assert sel.stale_sources[0]["status"] == "changed"
