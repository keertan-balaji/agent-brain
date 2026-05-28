"""brain.staleness — DB-wide scan + git-diff-driven scan."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.provenance import attach_provenance
from brain.staleness import StaleSource, scan_db, scan_diff


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)


def _git_commit_all(repo: Path, msg: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()


def _seed_source(engine, content: str, kind: str = "decision") -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES (:k, :c, :h, 'active') RETURNING id"
            ),
            {"k": kind, "c": content, "h": h},
        ).scalar()
    return int(sid)


def test_scan_db_returns_empty_when_no_provenance(pg_url: str) -> None:
    engine = get_engine(pg_url)
    _seed_source(engine, "no provenance")
    report = scan_db(engine)
    assert report.stale_sources == []


def test_scan_db_flags_changed_file(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "x.py"
    f.write_text("v1\n")
    sid = _seed_source(engine, "about x.py")
    attach_provenance(engine, source_id=sid, source_files=[{"path": str(f)}])
    f.write_text("v2 — significantly different\n")
    report = scan_db(engine)
    ids = {s.source_id for s in report.stale_sources}
    assert sid in ids
    assert next(s.status for s in report.stale_sources if s.source_id == sid) == "changed"


def test_scan_db_flags_missing_file(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "y.py"
    f.write_text("body\n")
    sid = _seed_source(engine, "about y.py")
    attach_provenance(engine, source_id=sid, source_files=[{"path": str(f)}])
    f.unlink()
    report = scan_db(engine)
    statuses = {s.source_id: s.status for s in report.stale_sources}
    assert statuses.get(sid) == "missing"


def test_scan_db_passes_unchanged_file(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "z.py"
    f.write_text("steady\n")
    sid = _seed_source(engine, "about z.py")
    attach_provenance(engine, source_id=sid, source_files=[{"path": str(f)}])
    report = scan_db(engine)
    assert all(s.source_id != sid for s in report.stale_sources)


def test_scan_diff_only_scans_changed_files(pg_url: str, tmp_path: Path) -> None:
    """git diff says 'a.py' changed; b.py untouched. Only sources tied to a.py
    should appear in the report."""
    engine = get_engine(pg_url)
    repo = tmp_path / "r"
    repo.mkdir()
    _git_init(repo)
    a = repo / "a.py"; a.write_text("a v1\n")
    b = repo / "b.py"; b.write_text("b steady\n")
    sha0 = _git_commit_all(repo, "init")

    sid_a = _seed_source(engine, "about a")
    sid_b = _seed_source(engine, "about b")
    attach_provenance(engine, source_id=sid_a, source_files=[{"path": str(a)}])
    attach_provenance(engine, source_id=sid_b, source_files=[{"path": str(b)}])

    # Only a.py changes.
    a.write_text("a v2 changed\n")
    _git_commit_all(repo, "change a")

    report = scan_diff(engine, since_ref=sha0, repo_cwd=str(repo))
    flagged = {s.source_id for s in report.stale_sources}
    assert sid_a in flagged
    assert sid_b not in flagged


def test_scan_diff_returns_empty_for_no_changes(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    repo = tmp_path / "r"
    repo.mkdir()
    _git_init(repo)
    (repo / "c.py").write_text("c\n")
    sha = _git_commit_all(repo, "init")
    report = scan_diff(engine, since_ref=sha, repo_cwd=str(repo))
    assert report.stale_sources == []


def test_scan_diff_falls_back_gracefully_when_not_a_git_repo(pg_url: str, tmp_path: Path) -> None:
    """If repo_cwd isn't a git working tree, scan_diff returns empty rather than raising."""
    engine = get_engine(pg_url)
    report = scan_diff(engine, since_ref="HEAD", repo_cwd=str(tmp_path))
    assert report.stale_sources == []
    assert report.scanned_files == 0
