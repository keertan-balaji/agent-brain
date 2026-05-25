"""Migration 010 schema additions: sessions.cc_session_id, sessions.cwd,
session_resume_bundles.consumed_at + cwd, new session_events table."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine


def test_sessions_has_cc_session_id(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='sessions'"
            )
        ).fetchall()
    names = {r[0] for r in cols}
    assert "cc_session_id" in names
    assert "cwd" in names


def test_session_resume_bundles_has_consumed_at_and_cwd(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='session_resume_bundles'"
            )
        ).fetchall()
    names = {r[0] for r in cols}
    assert "consumed_at" in names
    assert "cwd" in names


def test_session_events_table_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='session_events'"
            )
        ).fetchall()
    names = {r[0] for r in cols}
    for required in ("id", "session_id", "event_kind", "payload", "occurred_at"):
        assert required in names, f"missing column {required}"


def test_sessions_cc_id_index(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename='sessions'")
        ).fetchall()
    names = {r[0] for r in rows}
    assert "sessions_cc_session_id_idx" in names


def test_session_resume_bundles_cwd_consumed_index(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename='session_resume_bundles'")
        ).fetchall()
    names = {r[0] for r in rows}
    assert "bundles_cwd_unconsumed_idx" in names
