"""Capture-time provenance helpers (v0.9.0).

A "provenance_meta" payload attached to a sources row records WHICH FILES the
captured knowledge was extracted from + WHAT COMMIT the repo was at when the
capture happened. The staleness module (brain.staleness) reads this to detect
when a file has changed since capture — agent then invokes brain-revise.

This module is pure: no LLM calls, no agent prompts. Hash + JSONB writes only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, text

from brain.db import session_scope


def file_hash(path: Path | str) -> str | None:
    """Return sha256 hex of file contents, or None if file is missing/unreadable."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def attach_provenance(
    engine: Engine,
    *,
    source_id: int,
    source_files: list[dict],
    commit_at_capture: str | None = None,
    branch_at_capture: str | None = None,
) -> None:
    """Write provenance_meta into the given source row.

    source_files: each entry should have at least {'path': str}. Optional keys:
      - line_range: [start, end]
      - sha256_at_capture: if not provided, computed from the file contents now.
    Missing files get sha256_at_capture=None — they'll surface as 'missing' in
    the staleness report.
    """
    enriched: list[dict] = []
    for sf in source_files:
        entry = dict(sf)
        if "sha256_at_capture" not in entry:
            entry["sha256_at_capture"] = file_hash(Path(entry["path"]))
        enriched.append(entry)

    payload = {
        "source_files": enriched,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    if commit_at_capture:
        payload["commit_at_capture"] = commit_at_capture
    if branch_at_capture:
        payload["branch_at_capture"] = branch_at_capture

    with session_scope(engine) as s:
        s.execute(
            text(
                "UPDATE sources SET provenance_meta = CAST(:m AS jsonb) WHERE id = :i"
            ),
            {"m": json.dumps(payload), "i": source_id},
        )


@dataclass(frozen=True)
class ProvenanceMatch:
    source_id: int
    kind: str
    uri: str | None
    path: str
    sha256_at_capture: str | None
    line_range: tuple[int, int] | None


def list_sources_for_files(engine: Engine, *, paths: list[str]) -> list[ProvenanceMatch]:
    """Return all active sources whose provenance_meta references any of the
    given file paths. Uses the GIN index on (provenance_meta->'source_files').

    paths: absolute file paths to look up.
    """
    if not paths:
        return []
    matches: list[ProvenanceMatch] = []
    # JSONB containment query, one per path — straightforward and lets the GIN
    # index work optimally. Could be unified into one query with a UNION but
    # path counts are small (typically <50 per session).
    sql = text(
        "SELECT id, kind, uri, provenance_meta "
        "FROM sources "
        "WHERE t_valid_to IS NULL "
        "  AND status = 'active' "
        "  AND provenance_meta IS NOT NULL "
        "  AND provenance_meta->'source_files' @> CAST(:needle AS jsonb)"
    )
    with session_scope(engine) as s:
        for p in paths:
            needle = json.dumps([{"path": p}])
            rows = s.execute(sql, {"needle": needle}).fetchall()
            for r in rows:
                pm = r.provenance_meta or {}
                for sf in pm.get("source_files", []):
                    if sf.get("path") != p:
                        continue
                    lr = sf.get("line_range")
                    matches.append(
                        ProvenanceMatch(
                            source_id=int(r.id),
                            kind=r.kind,
                            uri=r.uri,
                            path=p,
                            sha256_at_capture=sf.get("sha256_at_capture"),
                            line_range=tuple(lr) if lr else None,
                        )
                    )
    return matches
