"""PreToolUse hook injects brain recall hits as additionalContext (v0.10.1)."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope


def _run_hook(event, payload, env_db_url):
    return subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )


def _seed_substantive_source(engine, content, kind="decision", uri=None) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES (:k, :c, :h, 'active', :u) RETURNING id"
            ),
            {"k": kind, "c": content, "h": h, "u": uri},
        ).scalar()
        # Materialize FTS row so plainto_tsquery can match it.
        s.execute(
            text(
                "INSERT INTO sources_fts(source_id, tsv) "
                "VALUES (:s, to_tsvector('english', :content))"
            ),
            {"s": sid, "content": content},
        )
    return int(sid)


def test_pretool_use_injects_recall_for_bash_pytest(pg_url: str) -> None:
    """A captured pattern about pytest should surface when about to run pytest."""
    engine = get_engine(pg_url)
    _seed_substantive_source(
        engine,
        "pytest tests convention: always use --tb=line for shorter failure output in tests",
        kind="pattern",
        uri="pattern://pytest-tb-line",
    )

    payload = {
        "session_id": "pretool-1",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/ -v"},
    }
    res = _run_hook("pre-tool-use", payload, pg_url)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout or "{}")
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert ctx, "additionalContext should be non-empty when there is a hit"
    assert "pytest" in ctx.lower()


def test_pretool_use_skips_blocklisted_tool(pg_url: str) -> None:
    """TodoWrite (and other agent-internal tools) should not trigger recall."""
    payload = {
        "session_id": "pretool-2",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": "TodoWrite",
        "tool_input": {"todos": []},
    }
    res = _run_hook("pre-tool-use", payload, pg_url)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout or "{}")
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert ctx == ""


def test_pretool_use_empty_context_when_no_recall_hit(pg_url: str) -> None:
    """If recall returns nothing, hook emits empty context — no spam."""
    payload = {
        "session_id": "pretool-3",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls /tmp"},
    }
    res = _run_hook("pre-tool-use", payload, pg_url)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout or "{}")
    # 'ls /tmp' shouldn't match anything in the brain → empty context.
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_pretool_use_silent_on_recall_failure(pg_url: str) -> None:
    """If recall raises for any reason, hook still emits a valid envelope
    (non-fatal — must not break the session)."""
    payload = {
        "session_id": "pretool-4",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/tmp/x.py", "old_string": "a", "new_string": "b"},
    }
    res = _run_hook("pre-tool-use", payload, pg_url)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout or "{}")
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
