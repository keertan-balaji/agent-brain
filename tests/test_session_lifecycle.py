"""Session lifecycle: start_session, find_by_cc_id, end_session."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.hooks.session import end_session, find_session_by_cc_id, start_session


def test_start_session_creates_row(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(
        engine,
        cc_session_id="abc-123",
        cwd="/tmp/foo",
        agent="claude-code",
        source="startup",
    )
    assert sid > 0
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT cc_session_id, cwd, ended_at FROM sessions WHERE id = :i"),
            {"i": sid},
        ).one()
    assert row.cc_session_id == "abc-123"
    assert row.cwd == "/tmp/foo"
    assert row.ended_at is None


def test_start_session_returns_existing_when_cc_id_matches(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid_a = start_session(engine, cc_session_id="dup", cwd="/tmp", agent="cc", source="startup")
    sid_b = start_session(engine, cc_session_id="dup", cwd="/tmp", agent="cc", source="resume")
    assert sid_a == sid_b


def test_find_session_by_cc_id(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="findme", cwd="/x", agent="cc", source="startup")
    assert find_session_by_cc_id(engine, "findme") == sid
    assert find_session_by_cc_id(engine, "nope") is None


def test_end_session_sets_ended_at(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="enders", cwd="/x", agent="cc", source="startup")
    end_session(engine, cc_session_id="enders", reason="user_quit")
    with session_scope(engine) as s:
        ended = s.execute(
            text("SELECT ended_at FROM sessions WHERE id = :i"), {"i": sid}
        ).scalar()
    assert ended is not None


def test_end_session_unknown_cc_id_is_noop(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # Should not raise
    end_session(engine, cc_session_id="ghost", reason="ignored")
