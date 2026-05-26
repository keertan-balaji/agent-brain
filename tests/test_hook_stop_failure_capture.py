"""End-to-end: Stop hook reads transcript, writes failure_memories rows."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run_hook(event: str, payload: dict, env_db_url: str) -> tuple[int, str, str]:
    """Mirror of the helper in test_hook_session_start.py — subprocess + BRAIN_DB_URL."""
    result = subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )
    return result.returncode, result.stdout, result.stderr


def _write_failure_transcript(p: Path) -> None:
    lines = [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": "compile the rust crate"}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "cargo build --release"}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result", "is_error": True,
                                  "content": "error[E0432]: unresolved import"}]}},
    ]
    p.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def test_stop_hook_records_failure_from_transcript(pg_url: str, tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    _write_failure_transcript(transcript)
    payload = {
        "session_id": "stop-test-1",
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }
    rc, stdout, stderr = _run_hook("stop", payload, pg_url)
    assert rc == 0, stderr
    assert json.loads(stdout.strip() or "{}") == {}

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT id, target_problem, attempted_approach, retry_count "
                "FROM failure_memories "
                "WHERE attempted_approach LIKE 'Bash: cargo build%' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).first()
    assert row is not None
    assert "compile the rust crate" in row.target_problem
    assert row.retry_count == 1


def test_stop_hook_bumps_retry_on_recurrence(pg_url: str, tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    _write_failure_transcript(transcript)
    payload = {
        "session_id": "stop-test-2",
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }
    for _ in range(2):
        rc, _, stderr = _run_hook("stop", payload, pg_url)
        assert rc == 0, stderr

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        rc_val = s.execute(
            text(
                "SELECT retry_count FROM failure_memories "
                "WHERE attempted_approach LIKE 'Bash: cargo build%' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).scalar()
    assert rc_val == 2


def test_stop_hook_with_no_failure_transcript_writes_nothing(pg_url: str, tmp_path: Path) -> None:
    p = tmp_path / "ok.jsonl"
    lines = [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": "list files"}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "ls"}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result",
                                  "content": "a.txt\nb.txt"}]}},
    ]
    p.write_text("\n".join(json.dumps(line) for line in lines) + "\n")

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        before = s.execute(text("SELECT COUNT(*) FROM failure_memories")).scalar()

    payload = {
        "session_id": "stop-test-3",
        "transcript_path": str(p),
        "cwd": str(tmp_path),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }
    rc, _, stderr = _run_hook("stop", payload, pg_url)
    assert rc == 0, stderr

    with session_scope(engine) as s:
        after = s.execute(text("SELECT COUNT(*) FROM failure_memories")).scalar()
    assert after == before


def test_stop_hook_silent_on_missing_transcript(pg_url: str, tmp_path: Path) -> None:
    payload = {
        "session_id": "stop-test-4",
        "transcript_path": str(tmp_path / "absent.jsonl"),
        "cwd": str(tmp_path),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    }
    rc, _, stderr = _run_hook("stop", payload, pg_url)
    assert rc == 0, stderr
