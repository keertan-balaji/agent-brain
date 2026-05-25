"""brain hook pre-compact: gather + render + insert bundle + emit compact instructions."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.schemas import SourceInput
from brain.write import write


def _run(payload: dict, db_url: str) -> tuple[int, str]:
    r = subprocess.run(
        ["brain", "hook", "pre-compact"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode, r.stdout


def test_pre_compact_inserts_bundle(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="decision", content="chose pgvector"))
    write(engine, SourceInput(kind="gotcha", content="::jsonb collides"))

    rc, stdout = _run({
        "session_id": "pc-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/pc1",
        "hook_event_name": "PreCompact", "trigger": "manual",
    }, pg_url)
    assert rc == 0
    # stdout becomes compact instructions; must be non-empty text
    assert "brain" in stdout.lower()

    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT trigger, token_budget, rendered FROM session_resume_bundles "
                "WHERE cwd = '/tmp/pc1'"
            )
        ).one()
    assert row.trigger == "pre_compact"
    assert "pgvector" in row.rendered or "Decisions" in row.rendered


def test_pre_compact_supersedes_prior_bundle(pg_url: str) -> None:
    payload = {
        "session_id": "pc-2", "transcript_path": "/t.jsonl", "cwd": "/tmp/pc2",
        "hook_event_name": "PreCompact", "trigger": "manual",
    }
    _run(payload, pg_url)
    _run(payload, pg_url)  # second call should supersede first
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        rows = s.execute(
            text("SELECT superseded_at FROM session_resume_bundles WHERE cwd = '/tmp/pc2' ORDER BY id"),
        ).fetchall()
    assert len(rows) == 2
    assert rows[0].superseded_at is not None  # first bundle superseded
    assert rows[1].superseded_at is None      # second is the live one


def test_pre_compact_creates_project_row(pg_url: str) -> None:
    _run({
        "session_id": "pc-3", "transcript_path": "/t.jsonl", "cwd": "/tmp/proj-fresh-pc",
        "hook_event_name": "PreCompact", "trigger": "manual",
    }, pg_url)
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        slug = s.execute(
            text("SELECT slug FROM projects WHERE repo_root = '/tmp/proj-fresh-pc'"),
        ).scalar()
    assert slug == "proj-fresh-pc"
