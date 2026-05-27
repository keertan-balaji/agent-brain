"""src/brain/compliance.py — capture stats + under-captured + thin-bundle helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.compliance import (
    CaptureStats,
    is_strict_mode,
    is_thin_bundle,
    is_under_captured,
    session_capture_stats,
    under_captured_sessions,
)
from brain.db import get_engine, session_scope
from brain.hooks.bundle import BundleSelection
from brain.schemas import SourceInput
from brain.write import write


def _make_session(engine, *, project_id=None, started_at=None, ended_at=None) -> int:
    started = started_at or (datetime.now(timezone.utc) - timedelta(hours=1))
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent, started_at, ended_at, cwd) "
                "VALUES (:p, 'claude-code', :st, :en, '/tmp/x') RETURNING id"
            ),
            {"p": project_id, "st": started, "en": ended_at},
        ).scalar()
    return int(sid)


def _record_turns(engine, *, session_id: int, n: int) -> None:
    with session_scope(engine) as s:
        for i in range(n):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload, occurred_at) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb, NOW() - (:i * INTERVAL '1 minute'))"
                ),
                {"sid": session_id, "i": i},
            )


def test_session_capture_stats_empty_session(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _make_session(engine)
    stats = session_capture_stats(engine, session_id=sid)
    assert stats.session_id == sid
    assert stats.turn_count == 0
    assert stats.capture_count == 0
    assert stats.decision_count == 0
    assert stats.failure_count == 0


def test_session_capture_stats_counts_turns_and_captures(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _make_session(engine, ended_at=datetime.now(timezone.utc) + timedelta(hours=1))
    _record_turns(engine, session_id=sid, n=6)
    write(engine, SourceInput(kind="decision", content="we picked Postgres"))
    write(engine, SourceInput(kind="gotcha", content="halfvec needs ::halfvec cast"))
    write(engine, SourceInput(kind="note", content="nb on the migration order"))
    stats = session_capture_stats(engine, session_id=sid)
    assert stats.turn_count == 6
    assert stats.capture_count == 3
    assert stats.decision_count == 1
    assert stats.gotcha_count == 1


def test_session_capture_stats_excludes_captures_outside_window(pg_url: str) -> None:
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    sid = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
    write(engine, SourceInput(kind="decision", content="late-arriving decision"))
    stats = session_capture_stats(engine, session_id=sid)
    assert stats.capture_count == 0


def test_is_under_captured_true_when_many_turns_few_captures() -> None:
    stats = CaptureStats(
        session_id=1, cc_session_id="x", project_id=None,
        turn_count=6, capture_count=2,
        decision_count=0, gotcha_count=0, subtask_summary_count=0, failure_count=0,
    )
    assert is_under_captured(stats) is True


def test_is_under_captured_false_below_turn_threshold() -> None:
    stats = CaptureStats(
        session_id=1, cc_session_id="x", project_id=None,
        turn_count=3, capture_count=0,
        decision_count=0, gotcha_count=0, subtask_summary_count=0, failure_count=0,
    )
    assert is_under_captured(stats) is False


def test_is_under_captured_false_when_capture_threshold_met() -> None:
    stats = CaptureStats(
        session_id=1, cc_session_id="x", project_id=None,
        turn_count=10, capture_count=3,
        decision_count=1, gotcha_count=1, subtask_summary_count=1, failure_count=0,
    )
    assert is_under_captured(stats) is False  # strictly < 3 to fail


def test_is_thin_bundle_true_when_all_substantive_empty() -> None:
    sel = BundleSelection()
    assert is_thin_bundle(sel) is True


def test_is_thin_bundle_false_with_open_subtask() -> None:
    sel = BundleSelection(subtasks_open=[{"subtask_id": 1, "title": "x", "goal": "y"}])
    assert is_thin_bundle(sel) is False


def test_is_thin_bundle_false_with_decision() -> None:
    sel = BundleSelection(decisions=[{"source_id": 1, "kind": "decision", "head": "..."}])
    assert is_thin_bundle(sel) is False


def test_is_thin_bundle_patterns_alone_still_thin() -> None:
    sel = BundleSelection(patterns=[{"source_id": 1, "kind": "pattern", "head": "..."}])
    assert is_thin_bundle(sel) is True


def test_under_captured_sessions_returns_only_qualifying(pg_url: str) -> None:
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)

    a = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
    _record_turns(engine, session_id=a, n=6)

    b = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now + timedelta(hours=1))
    _record_turns(engine, session_id=b, n=6)
    for i in range(5):
        write(engine, SourceInput(kind="decision", content=f"d{i}"))

    c = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
    _record_turns(engine, session_id=c, n=3)

    d = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=None)
    _record_turns(engine, session_id=d, n=6)

    rows = under_captured_sessions(engine)
    ids = {r.session_id for r in rows}
    assert a in ids
    assert b not in ids
    assert c not in ids
    assert d not in ids


def test_is_strict_mode_false_when_unset(pg_url: str) -> None:
    engine = get_engine(pg_url)
    assert is_strict_mode(engine) is False


def test_is_strict_mode_true_when_set_true(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO brain_config(key, value, updated_at) "
                "VALUES ('strict_mode', 'true', NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value"
            )
        )
    assert is_strict_mode(engine) is True


def test_is_strict_mode_false_when_set_false(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO brain_config(key, value, updated_at) "
                "VALUES ('strict_mode', 'false', NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value"
            )
        )
    assert is_strict_mode(engine) is False
