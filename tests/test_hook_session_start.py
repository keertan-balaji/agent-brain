"""brain hook session-start: stdin -> session row + bundle lookup + stdout."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run_hook(event: str, payload: dict, env_db_url: str) -> tuple[int, str, str]:
    """Pipe JSON into `brain hook <event>` via subprocess; capture exit + streams."""
    result = subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )
    return result.returncode, result.stdout, result.stderr


def test_session_start_creates_session_row(pg_url: str) -> None:
    payload = {
        "session_id": "ss-1",
        "transcript_path": "/tmp/ss-1.jsonl",
        "cwd": "/tmp/proj-a",
        "hook_event_name": "SessionStart",
        "source": "startup",
        "model": "claude-opus",
    }
    rc, stdout, stderr = _run_hook("session-start", payload, pg_url)
    assert rc == 0, stderr
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT id, cwd FROM sessions WHERE cc_session_id = :cc"),
            {"cc": "ss-1"},
        ).one()
    assert row.cwd == "/tmp/proj-a"
    obj = json.loads(stdout)
    assert obj["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_session_start_emits_empty_context_when_no_bundle(pg_url: str) -> None:
    payload = {
        "session_id": "ss-2",
        "transcript_path": "/tmp/ss-2.jsonl",
        "cwd": "/tmp/proj-empty",
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    rc, stdout, _ = _run_hook("session-start", payload, pg_url)
    assert rc == 0
    obj = json.loads(stdout)
    assert obj["hookSpecificOutput"]["additionalContext"] == ""


def test_session_start_injects_unconsumed_bundle(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        proj_id = s.execute(
            text(
                "INSERT INTO projects(slug, task_type, repo_root) "
                "VALUES ('p3a-test', 'development', '/tmp/proj-c') RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO session_resume_bundles("
                "project_id, trigger, token_budget, manifest, rendered, cwd"
                ") VALUES(:p, 'pre_compact', 4000, CAST('{}' AS jsonb), :r, :c)"
            ),
            {"p": proj_id, "r": "# Resume bundle\n\nplanted content here", "c": "/tmp/proj-c"},
        )

    payload = {
        "session_id": "ss-3",
        "transcript_path": "/tmp/ss-3.jsonl",
        "cwd": "/tmp/proj-c",
        "hook_event_name": "SessionStart",
        "source": "compact",
    }
    rc, stdout, _ = _run_hook("session-start", payload, pg_url)
    assert rc == 0
    obj = json.loads(stdout)
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert "planted content here" in ctx

    # Bundle should now be consumed
    with session_scope(engine) as s:
        consumed = s.execute(
            text(
                "SELECT consumed_at FROM session_resume_bundles WHERE cwd = :c ORDER BY id DESC LIMIT 1"
            ),
            {"c": "/tmp/proj-c"},
        ).scalar()
    assert consumed is not None


def test_session_start_records_event(pg_url: str) -> None:
    payload = {
        "session_id": "ss-4",
        "transcript_path": "/tmp/ss-4.jsonl",
        "cwd": "/tmp/proj-d",
        "hook_event_name": "SessionStart",
        "source": "resume",
    }
    _run_hook("session-start", payload, pg_url)
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(text("SELECT id FROM sessions WHERE cc_session_id = 'ss-4'")).scalar()
        kinds = [
            r.event_kind
            for r in s.execute(
                text("SELECT event_kind FROM session_events WHERE session_id = :i"), {"i": sid}
            ).fetchall()
        ]
    assert "session_start" in kinds
