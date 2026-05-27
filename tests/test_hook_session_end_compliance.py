"""SessionEnd hook records under_captured + honors strict_mode (Phase 3a-4)."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.schemas import SourceInput
from brain.write import write


def _run_hook(event, payload, env_db_url):
    return subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )


def _seed_undercaptured_session(engine, cc_id: str) -> int:
    """Pre-seed a sessions row with 6 user-prompt-submit events. Returns the sid.
    The actual session_end hook re-uses this row via cc_session_id lookup."""
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, :cc, '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1), "cc": cc_id},
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


def test_session_end_records_under_captured_event(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_undercaptured_session(engine, "se-uc-1")

    payload = {
        "session_id": "se-uc-1",
        "transcript_path": "/tmp/se-uc-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 0, res.stderr

    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT payload FROM session_events "
                "WHERE session_id = :sid AND event_kind = 'under_captured'"
            ),
            {"sid": sid},
        ).first()
    assert row is not None, "expected under_captured event to be recorded"
    assert row.payload["turn_count"] == 6
    assert row.payload["capture_count"] == 0


def test_session_end_no_under_captured_event_for_compliant_session(pg_url: str) -> None:
    """A session with 3+ captures in window should NOT record under_captured."""
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, 'se-ok-1', '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1)},
        ).scalar()
        for _ in range(6):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb)"
                ),
                {"sid": sid},
            )

    write(engine, SourceInput(kind="decision", content="d1"))
    write(engine, SourceInput(kind="gotcha", content="g1"))
    write(engine, SourceInput(kind="note", content="n1"))

    payload = {
        "session_id": "se-ok-1",
        "transcript_path": "/tmp/se-ok-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 0, res.stderr

    with session_scope(engine) as s:
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM session_events "
                "WHERE session_id = :sid AND event_kind = 'under_captured'"
            ),
            {"sid": int(sid)},
        ).scalar()
    assert n == 0


def test_session_end_strict_mode_exits_non_zero(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO brain_config(key, value, updated_at) "
                "VALUES ('strict_mode', 'true', NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value='true'"
            )
        )
    _seed_undercaptured_session(engine, "se-strict-1")

    payload = {
        "session_id": "se-strict-1",
        "transcript_path": "/tmp/se-strict-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 2, f"expected exit 2, got {res.returncode} stderr={res.stderr}"

    # Clean up: reset strict_mode so other tests in the suite are not polluted.
    # brain_config is excluded from conftest truncation (it holds seeded constants).
    with session_scope(engine) as s:
        s.execute(
            text(
                "UPDATE brain_config SET value='false' WHERE key='strict_mode'"
            )
        )


def test_session_end_silent_on_absent_session_row(pg_url: str) -> None:
    """If no sessions row exists for the cc_session_id, hook must not crash."""
    payload = {
        "session_id": "se-absent-1",
        "transcript_path": "/tmp/se-absent-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    # end_session auto-creates a missing sessions row via start_session under the
    # hood. With turn_count=0 the under_captured predicate is false. Hook exits 0.
    assert res.returncode == 0, res.stderr
