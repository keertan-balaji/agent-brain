"""brain hook session-end: marks session ended + records event."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(event: str, payload: dict, db_url: str) -> tuple[int, str, str]:
    r = subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode, r.stdout, r.stderr


def test_session_end_sets_ended_at(pg_url: str) -> None:
    # Pre-create the session via session-start
    _run("session-start", {
        "session_id": "se-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/se",
        "hook_event_name": "SessionStart", "source": "startup",
    }, pg_url)
    rc, _, err = _run("session-end", {
        "session_id": "se-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/se",
        "hook_event_name": "SessionEnd", "reason": "user_quit",
    }, pg_url)
    assert rc == 0, err
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        ended = s.execute(
            text("SELECT ended_at FROM sessions WHERE cc_session_id = 'se-1'")
        ).scalar()
    assert ended is not None


def test_session_end_for_unknown_session_is_noop(pg_url: str) -> None:
    rc, _, err = _run("session-end", {
        "session_id": "ghost", "transcript_path": "/t.jsonl", "cwd": "/tmp",
        "hook_event_name": "SessionEnd", "reason": "ignored",
    }, pg_url)
    assert rc == 0, err  # Must not raise
