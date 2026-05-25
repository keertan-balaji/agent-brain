"""End-to-end Phase 3a-1: simulate session lifecycle via hook subprocess invocations.

Walks the full path:
  1. SessionStart (startup) - new session
  2. UserPromptSubmit - prompt captured
  3. Several decision/gotcha writes
  4. PreCompact - bundle generated + persisted
  5. SessionStart (compact) on a new cc_session_id - bundle injected via additionalContext
  6. The injected bundle contains the prior decisions/gotchas
"""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.schemas import SourceInput
from brain.write import write


def _hook(event: str, payload: dict, db_url: str) -> tuple[int, str]:
    r = subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode, r.stdout


def test_phase3a_1_full_lifecycle(pg_url: str) -> None:
    engine = get_engine(pg_url)
    cwd = "/tmp/e2e-3a1"

    # 1. SessionStart (startup)
    rc, out = _hook("session-start", {
        "session_id": "e2e-startup",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "SessionStart",
        "source": "startup",
    }, pg_url)
    assert rc == 0
    # No bundle yet -> empty additionalContext
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == ""

    # 2. UserPromptSubmit
    _hook("user-prompt-submit", {
        "session_id": "e2e-startup",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "UserPromptSubmit",
        "prompt": "let's ship phase 3a-1",
    }, pg_url)

    # 3. Capture some decisions/gotchas
    write(engine, SourceInput(kind="decision", content="ship 3a-1 first; failure capture goes to 3a-2"))
    write(engine, SourceInput(kind="gotcha", content="PreCompact stdout becomes compact instructions, not next-session context"))
    write(engine, SourceInput(kind="pattern", content="DB-mediated bundle handoff via consumed_at flag"))

    # 4. PreCompact
    rc, stdout = _hook("pre-compact", {
        "session_id": "e2e-startup",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "PreCompact",
        "trigger": "manual",
    }, pg_url)
    assert rc == 0
    assert "brain" in stdout.lower()

    # Verify bundle persisted
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT trigger, consumed_at, rendered FROM session_resume_bundles WHERE cwd = :c ORDER BY id DESC LIMIT 1"),
            {"c": cwd},
        ).one()
    assert row.trigger == "pre_compact"
    assert row.consumed_at is None
    assert "ship 3a-1" in row.rendered

    # 5. New SessionStart with source=compact
    rc, out = _hook("session-start", {
        "session_id": "e2e-postcompact",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "SessionStart",
        "source": "compact",
    }, pg_url)
    assert rc == 0
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]

    # 6. Injected bundle contains the planted content
    assert "ship 3a-1" in ctx  # decision survived
    assert "DB-mediated bundle handoff" in ctx  # pattern survived

    # 7. Bundle is now consumed
    with session_scope(engine) as s:
        consumed = s.execute(
            text("SELECT consumed_at FROM session_resume_bundles WHERE cwd = :c ORDER BY id DESC LIMIT 1"),
            {"c": cwd},
        ).scalar()
    assert consumed is not None
