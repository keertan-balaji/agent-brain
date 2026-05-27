"""PreCompact emits thin_session event when bundle has no substantive content."""

from __future__ import annotations

import json
import os
import subprocess

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


def test_pre_compact_emits_thin_session_event_for_empty_bundle(pg_url: str, tmp_path) -> None:
    # Fresh DB → no decisions/gotchas/failures/subtasks → bundle is thin.
    payload = {
        "session_id": "pc-thin-1",
        "transcript_path": str(tmp_path / "t.jsonl"),
        "cwd": "/tmp/proj-thin",
        "hook_event_name": "PreCompact",
        "trigger": "manual",
    }
    res = _run_hook("pre-compact", payload, pg_url)
    assert res.returncode == 0, res.stderr

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text("SELECT id FROM sessions WHERE cc_session_id = 'pc-thin-1'")
        ).scalar()
        rows = s.execute(
            text(
                "SELECT payload FROM session_events "
                "WHERE session_id = :sid AND event_kind = 'thin_session'"
            ),
            {"sid": sid},
        ).fetchall()
    assert len(rows) == 1
    assert rows[0].payload["trigger"] == "pre_compact"


def test_pre_compact_no_thin_event_when_bundle_has_decisions(pg_url: str, tmp_path) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="decision", content="significant decision"))

    payload = {
        "session_id": "pc-thin-2",
        "transcript_path": str(tmp_path / "t.jsonl"),
        "cwd": "/tmp/proj-fat",
        "hook_event_name": "PreCompact",
        "trigger": "manual",
    }
    res = _run_hook("pre-compact", payload, pg_url)
    assert res.returncode == 0

    with session_scope(engine) as s:
        sid = s.execute(
            text("SELECT id FROM sessions WHERE cc_session_id = 'pc-thin-2'")
        ).scalar()
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM session_events "
                "WHERE session_id = :sid AND event_kind = 'thin_session'"
            ),
            {"sid": sid},
        ).scalar()
    assert n == 0
