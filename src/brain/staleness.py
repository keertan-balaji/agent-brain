"""Staleness scanner (v0.9.0).

Two scans:
  - scan_db: every active source with provenance_meta gets hash-compared to live FS
  - scan_diff: only files changed since a git ref are inspected (cheap)

Both are pure read — they never mutate sources.t_valid_to. Mutation is the
agent's job via brain-revise or brain.write.invalidate.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.provenance import file_hash, list_sources_for_files


@dataclass(frozen=True)
class StaleSource:
    source_id: int
    kind: str
    uri: str | None
    path: str
    sha256_at_capture: str | None
    current_sha256: str | None
    status: str  # "changed" | "missing" | "untracked"
    line_range: tuple[int, int] | None


@dataclass(frozen=True)
class StalenessReport:
    stale_sources: list[StaleSource] = field(default_factory=list)
    scanned_files: int = 0
    scanned_sources: int = 0


def _classify(at_capture: str | None, current: str | None) -> str | None:
    """Return a status string if the file is stale; None if fresh."""
    if at_capture is None:
        # We never had a capture-time hash — can't tell, so treat as untracked.
        return "untracked"
    if current is None:
        return "missing"
    if at_capture != current:
        return "changed"
    return None


def scan_db(engine: Engine) -> StalenessReport:
    """Whole-DB sweep. Iterates every active source with provenance_meta."""
    sql = text(
        "SELECT id, kind, uri, provenance_meta "
        "FROM sources "
        "WHERE t_valid_to IS NULL "
        "  AND status = 'active' "
        "  AND provenance_meta IS NOT NULL"
    )
    stale: list[StaleSource] = []
    scanned_files = 0
    scanned_sources = 0
    with session_scope(engine) as s:
        rows = s.execute(sql).fetchall()
    for r in rows:
        scanned_sources += 1
        for sf in (r.provenance_meta or {}).get("source_files", []):
            path = sf.get("path")
            if not path:
                continue
            scanned_files += 1
            cur = file_hash(Path(path))
            status = _classify(sf.get("sha256_at_capture"), cur)
            if status is None:
                continue
            lr = sf.get("line_range")
            stale.append(
                StaleSource(
                    source_id=int(r.id),
                    kind=r.kind,
                    uri=r.uri,
                    path=path,
                    sha256_at_capture=sf.get("sha256_at_capture"),
                    current_sha256=cur,
                    status=status,
                    line_range=tuple(lr) if lr else None,
                )
            )
    return StalenessReport(
        stale_sources=stale,
        scanned_files=scanned_files,
        scanned_sources=scanned_sources,
    )


def _git_diff_paths(since_ref: str, repo_cwd: str) -> list[str] | None:
    """Return absolute paths of files changed since ref, or None if not a git repo."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{since_ref}..HEAD"],
            cwd=repo_cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return [str(Path(repo_cwd) / p) for p in out.splitlines() if p.strip()]


def scan_diff(
    engine: Engine,
    *,
    since_ref: str = "HEAD~1",
    repo_cwd: str | None = None,
) -> StalenessReport:
    """Diff-based scan. O(changed_files), not O(total_sources).

    repo_cwd defaults to the current process cwd. If the directory isn't a git
    working tree, returns an empty report rather than raising.
    """
    cwd = repo_cwd or "."
    paths = _git_diff_paths(since_ref, cwd)
    if paths is None or not paths:
        return StalenessReport()

    matches = list_sources_for_files(engine, paths=paths)
    stale: list[StaleSource] = []
    for m in matches:
        cur = file_hash(Path(m.path))
        status = _classify(m.sha256_at_capture, cur)
        if status is None:
            continue
        stale.append(
            StaleSource(
                source_id=m.source_id,
                kind=m.kind,
                uri=m.uri,
                path=m.path,
                sha256_at_capture=m.sha256_at_capture,
                current_sha256=cur,
                status=status,
                line_range=m.line_range,
            )
        )
    return StalenessReport(
        stale_sources=stale,
        scanned_files=len(paths),
        scanned_sources=len({m.source_id for m in matches}),
    )
