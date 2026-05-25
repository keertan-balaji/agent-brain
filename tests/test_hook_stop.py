"""brain hook stop: records turn boundary."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(payload: dict, db_url: str) -> int:
    r = subprocess.run(
        ["brain", "hook", "stop"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode


def test_stop_records_event(pg_url: str) -> None:
    rc = _run({
        "session_id": "stop-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/stop",
        "hook_event_name": "Stop", "stop_hook_active": False,
    }, pg_url)
    assert rc == 0
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        kinds = [
            r.event_kind
            for r in s.execute(
                text(
                    "SELECT event_kind FROM session_events se "
                    "JOIN sessions ses ON se.session_id = ses.id "
                    "WHERE ses.cc_session_id = 'stop-1'"
                )
            ).fetchall()
        ]
    assert "stop" in kinds
