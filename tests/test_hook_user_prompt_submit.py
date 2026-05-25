"""brain hook user-prompt-submit: records prompt event."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(payload: dict, db_url: str) -> int:
    r = subprocess.run(
        ["brain", "hook", "user-prompt-submit"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode


def test_user_prompt_submit_records_event(pg_url: str) -> None:
    rc = _run({
        "session_id": "ups-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/ups",
        "hook_event_name": "UserPromptSubmit", "prompt": "what is the brain?",
    }, pg_url)
    assert rc == 0
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT event_kind, payload FROM session_events se "
                "JOIN sessions ses ON se.session_id = ses.id "
                "WHERE ses.cc_session_id = 'ups-1'"
            )
        ).fetchall()
    kinds = {r.event_kind for r in rows}
    assert "user_prompt_submit" in kinds
    prompt_row = next(r for r in rows if r.event_kind == "user_prompt_submit")
    assert prompt_row.payload["prompt"] == "what is the brain?"


def test_user_prompt_submit_truncates_long_prompts(pg_url: str) -> None:
    long_prompt = "x" * 5000
    rc = _run({
        "session_id": "ups-2", "transcript_path": "/t.jsonl", "cwd": "/tmp/ups2",
        "hook_event_name": "UserPromptSubmit", "prompt": long_prompt,
    }, pg_url)
    assert rc == 0
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        payload = s.execute(
            text(
                "SELECT payload FROM session_events se "
                "JOIN sessions ses ON se.session_id = ses.id "
                "WHERE ses.cc_session_id = 'ups-2' AND event_kind = 'user_prompt_submit'"
            )
        ).scalar()
    assert len(payload["prompt"]) == 1000
