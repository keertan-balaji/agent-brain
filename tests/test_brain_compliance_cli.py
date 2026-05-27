"""brain compliance check/list/list-thin CLI."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(args, pg_url):
    return subprocess.run(
        ["brain", *args],
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": pg_url},
    )


def _seed_undercaptured(engine) -> int:
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, ended_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, :en, 'cli-uc-1', '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1), "en": now - timedelta(minutes=5)},
        ).scalar()
        for _ in range(6):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb)"
                ),
                {"sid": sid},
            )
    return int(sid)


def test_compliance_check_prints_stats(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_undercaptured(engine)
    res = _run(["compliance", "check", "--session-id", str(sid)], pg_url)
    assert res.returncode == 0, res.stderr
    assert "turn_count=6" in res.stdout
    assert "capture_count=0" in res.stdout
    assert "under_captured=True" in res.stdout


def test_compliance_list_returns_recent_undercaptured(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_undercaptured(engine)
    res = _run(["compliance", "list"], pg_url)
    assert res.returncode == 0, res.stderr
    assert str(sid) in res.stdout


def test_compliance_list_thin_shows_thin_sessions(pg_url: str) -> None:
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, 'cli-thin-1', '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1)},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO session_events(session_id, event_kind, payload) "
                "VALUES (:sid, 'thin_session', '{\"trigger\": \"pre_compact\"}'::jsonb)"
            ),
            {"sid": sid},
        )
    res = _run(["compliance", "list-thin"], pg_url)
    assert res.returncode == 0, res.stderr
    assert str(sid) in res.stdout


def test_compliance_list_empty_message_when_no_rows(pg_url: str) -> None:
    res = _run(["compliance", "list"], pg_url)
    assert res.returncode == 0
    assert "(no under-captured sessions)" in res.stdout
