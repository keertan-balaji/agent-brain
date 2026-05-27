"""brain health audit reports under-captured sessions correctly (Phase 3a-4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.helpers.health import audit


def _make_session(engine, *, ended_at) -> int:
    started = datetime.now(timezone.utc) - timedelta(hours=2)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, ended_at, cwd) "
                "VALUES ('claude-code', :st, :en, '/tmp/x') RETURNING id"
            ),
            {"st": started, "en": ended_at},
        ).scalar()
    return int(sid)


def _record_turns(engine, *, session_id, n):
    with session_scope(engine) as s:
        for _ in range(n):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb)"
                ),
                {"sid": session_id},
            )


def test_audit_reports_undercaptured_via_session_events_not_events_table(pg_url: str) -> None:
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    sid = _make_session(engine, ended_at=now - timedelta(minutes=10))
    _record_turns(engine, session_id=sid, n=6)
    # Zero captures during the window.
    report = audit(engine)
    ids = {u.session_id for u in report.undercaptured_sessions}
    assert sid in ids


def test_audit_skips_session_with_fewer_than_5_turns(pg_url: str) -> None:
    """Below the turn threshold, sessions are not flagged (exploratory work)."""
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    sid = _make_session(engine, ended_at=now - timedelta(minutes=10))
    _record_turns(engine, session_id=sid, n=3)
    report = audit(engine)
    ids = {u.session_id for u in report.undercaptured_sessions}
    assert sid not in ids


def test_audit_threshold_param_passes_through_as_capture_threshold(pg_url: str) -> None:
    """The existing `undercapture_threshold` CLI param now maps to capture_threshold."""
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    sid = _make_session(engine, ended_at=now - timedelta(minutes=10))
    _record_turns(engine, session_id=sid, n=6)
    # With threshold=10 and 0 captures, this session is under-captured.
    # With threshold=0, no session can be under (cc < 0 is impossible).
    high = audit(engine, undercapture_threshold=10)
    low = audit(engine, undercapture_threshold=0)
    assert sid in {u.session_id for u in high.undercaptured_sessions}
    assert sid not in {u.session_id for u in low.undercaptured_sessions}
