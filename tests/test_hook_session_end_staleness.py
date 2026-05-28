"""SessionEnd hook records stale_sources count in session_events (v0.9.0)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.provenance import attach_provenance


def _run_hook(event, payload, env_db_url):
    return subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )


def test_session_end_records_staleness_event_when_files_changed(
    pg_url: str, tmp_path: Path
) -> None:
    engine = get_engine(pg_url)

    # 1) Seed a session.
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', NOW() - INTERVAL '1 hour', :cc, :cwd)"
            ),
            {"cc": "se-stale-1", "cwd": str(tmp_path)},
        )

    # 2) Capture a source with provenance pointing at a file.
    f = tmp_path / "src.py"
    f.write_text("v1\n")
    content = "about src.py"
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('gotcha', :c, :h, 'active') RETURNING id"
            ),
            {"c": content, "h": sha256_bytes(content)},
        ).scalar()
    attach_provenance(engine, source_id=int(sid), source_files=[{"path": str(f)}])

    # 3) Mutate the file (capture is now stale).
    f.write_text("v2 different\n")

    # 4) Fire SessionEnd.
    payload = {
        "session_id": "se-stale-1",
        "transcript_path": str(tmp_path / "absent.jsonl"),
        "cwd": str(tmp_path),
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 0, res.stderr

    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT payload FROM session_events "
                "WHERE event_kind = 'staleness_detected' "
                "  AND session_id = (SELECT id FROM sessions WHERE cc_session_id = :cc)"
            ),
            {"cc": "se-stale-1"},
        ).first()
    assert row is not None
    assert row.payload["stale_count"] >= 1
    assert any(int(sid) == s_["source_id"] for s_ in row.payload["stale_sources"])


def test_session_end_does_not_record_staleness_event_when_clean(
    pg_url: str, tmp_path: Path
) -> None:
    """No stale sources => no staleness_detected event."""
    engine = get_engine(pg_url)

    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', NOW() - INTERVAL '1 hour', :cc, :cwd)"
            ),
            {"cc": "se-stale-clean", "cwd": str(tmp_path)},
        )
    # No sources with provenance_meta = no stale_sources.

    payload = {
        "session_id": "se-stale-clean",
        "transcript_path": str(tmp_path / "absent.jsonl"),
        "cwd": str(tmp_path),
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 0, res.stderr

    with session_scope(engine) as s:
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM session_events "
                "WHERE event_kind = 'staleness_detected' "
                "  AND session_id = (SELECT id FROM sessions WHERE cc_session_id = :cc)"
            ),
            {"cc": "se-stale-clean"},
        ).scalar()
    assert n == 0
