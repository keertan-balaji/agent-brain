"""brain staleness check/diff CLI + brain write --from-file."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(args, pg_url):
    return subprocess.run(
        ["brain", *args],
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": pg_url},
    )


def test_brain_write_from_file_attaches_provenance(pg_url: str, tmp_path: Path) -> None:
    f = tmp_path / "src.py"
    f.write_text("def hello(): return 'world'\n")
    res = _run(
        ["write",
         "--kind", "decision",
         "--content", "hello() is correct",
         "--from-file", str(f)],
        pg_url,
    )
    assert res.returncode == 0, res.stderr

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT id, provenance_meta FROM sources "
                "WHERE content = 'hello() is correct' ORDER BY id DESC LIMIT 1"
            )
        ).first()
    assert row is not None
    assert row.provenance_meta is not None
    assert row.provenance_meta["source_files"][0]["path"] == str(f)


def test_brain_staleness_check_reports_changed(pg_url: str, tmp_path: Path) -> None:
    f = tmp_path / "src.py"
    f.write_text("v1\n")
    _run(
        ["write", "--kind", "gotcha", "--content", "g1", "--from-file", str(f)],
        pg_url,
    )
    f.write_text("v2 changed\n")
    res = _run(["staleness", "check"], pg_url)
    assert res.returncode == 0, res.stderr
    assert "changed" in res.stdout.lower() or "stale" in res.stdout.lower()
    assert str(f) in res.stdout


def test_brain_staleness_check_empty_when_clean(pg_url: str) -> None:
    res = _run(["staleness", "check"], pg_url)
    assert res.returncode == 0, res.stderr
    assert "no stale" in res.stdout.lower() or "0 stale" in res.stdout.lower()


def test_brain_write_from_file_with_line_range(pg_url: str, tmp_path: Path) -> None:
    f = tmp_path / "src2.py"
    f.write_text("x = 1\ny = 2\nz = 3\n")
    res = _run(
        ["write",
         "--kind", "decision",
         "--content", "y is the middle line",
         "--from-file", f"{f}:2-2"],
        pg_url,
    )
    assert res.returncode == 0, res.stderr

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT provenance_meta FROM sources "
                "WHERE content = 'y is the middle line' ORDER BY id DESC LIMIT 1"
            )
        ).first()
    sf = row.provenance_meta["source_files"][0]
    assert sf["path"] == str(f)
    assert sf["line_range"] == [2, 2]
