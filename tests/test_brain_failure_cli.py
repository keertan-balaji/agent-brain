"""brain failure record/list/invalidate CLI."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(args: list[str], env_db_url: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["brain", *args],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )
    return result.returncode, result.stdout, result.stderr


def test_failure_record_cli_creates_row(pg_url: str) -> None:
    rc, stdout, stderr = _run(
        [
            "failure", "record",
            "--target-problem", "P_cli",
            "--attempted-approach", "A_cli",
            "--outcome-evidence", "evidence",
        ],
        pg_url,
    )
    assert rc == 0, stderr
    assert "failure_id=" in stdout
    assert "retry_count=1" in stdout


def test_failure_list_cli_shows_active(pg_url: str) -> None:
    rc, _, stderr = _run(
        [
            "failure", "record",
            "--target-problem", "P_cli_list",
            "--attempted-approach", "A_cli_list",
        ],
        pg_url,
    )
    assert rc == 0, stderr

    rc, stdout, stderr = _run(["failure", "list", "--limit", "50"], pg_url)
    assert rc == 0, stderr
    assert "P_cli_list" in stdout


def test_failure_invalidate_cli_marks_row_inactive(pg_url: str) -> None:
    rc, rec_stdout, stderr = _run(
        [
            "failure", "record",
            "--target-problem", "P_cli_inv",
            "--attempted-approach", "A_cli_inv",
        ],
        pg_url,
    )
    assert rc == 0, stderr
    # Parse failure_id from "failure_id=42 retry_count=1"
    fid = int(rec_stdout.strip().split()[0].split("=")[1])

    rc, stdout, stderr = _run(
        [
            "failure", "invalidate", str(fid),
            "--reason", "fixed in commit deadbeef",
        ],
        pg_url,
    )
    assert rc == 0, stderr
    assert f"invalidated failure_id={fid}" in stdout

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        ended = s.execute(
            text("SELECT t_valid_to FROM failure_memories WHERE id = :i"),
            {"i": fid},
        ).scalar()
    assert ended is not None


def test_failure_list_cli_empty_message_when_no_rows(pg_url: str) -> None:
    rc, stdout, stderr = _run(["failure", "list"], pg_url)
    assert rc == 0, stderr
    assert "(no active failures)" in stdout
