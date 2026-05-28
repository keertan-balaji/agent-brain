# Agent Brain v0.9.0 — Code-Aware Staleness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when captured knowledge becomes stale because the source file changed. Compare stored sha256 + commit at capture-time against current filesystem; flag affected sources at session end or on demand. Diff-based: scan only files touched since a git ref, not the whole DB.

**Architecture:** Three layers stacked over the existing bi-temporal model. (1) Migration 014 adds `sources.provenance_meta JSONB` storing `source_files: [{path, sha256_at_capture, line_range}]` + `commit_at_capture`. (2) New `brain.provenance` + `brain.staleness` modules read the live filesystem + run `git diff` to flag potentially-stale sources. (3) SessionEnd hook surfaces the diff-based staleness count into the resume bundle so the next session sees the warning. No LLM call required — staleness is a hash + git-diff signal; semantic invalidation stays with the existing agent-driven `brain-revise` skill.

**Tech Stack:** Python 3.12, Postgres + pgvector, SQLAlchemy 2.0, Click, alembic. Adds no new runtime deps; uses stdlib `hashlib`, `subprocess` for git diff.

**Spec reference:** Conversation 2026-05-28 — user proposed (a) stale-detection on file change, (b) post-work git-diff scan as the trigger, (c) diff-based rather than whole-file scan. This plan implements (a) + (b) + (c) cheaply (no LLM). Layer-3 semantic invalidation deferred to a v0.9.1 `brain-revise --from-diff` extension.

**v0.8.5 prerequisites in place (verified):**
- `sources` table has `uri`, `flags JSONB`, `t_valid_from/to`, `invalidation_reason` — bi-temporal substrate ready.
- `brain.write()` with `auto_embed=True` for substantive kinds (v0.8.4).
- SessionEnd hook records `event_kind='session_end'` (Phase 3a-4); easy to extend.
- `session_resume_bundles` rendered via `BundleSelection` — adds a free section for staleness.
- Stop-hook noise filters (v0.8.5) — clean failure data to compare staleness against.

---

## Empirical findings (locked in via probe)

1. **`sources.uri` is free-form** — captures use various schemes (`note://`, `decision://`, `gotcha://`, etc.). For file-derived captures we'll use `file://<absolute-path>` AND populate `provenance_meta.source_files` separately. The structured field is what staleness queries against.
2. **Repo HEAD detection** — `git rev-parse HEAD` inside `cwd` returns the commit SHA. `git diff --name-only <ref>..HEAD` lists changed files. Both used by the staleness CLI.
3. **Multi-file captures** — a single decision may reference multiple files. `provenance_meta.source_files` is a JSONB array; one source row → 0-N file references.
4. **No new tables needed** — `sources.provenance_meta` + a JSONB GIN index supports the "find sources by file path" query directly via `WHERE provenance_meta @> '{"source_files":[{"path":"X"}]}'::jsonb`.

---

## Scope this plan does NOT cover

- **Semantic invalidation from diff content.** `brain-revise --from-diff` (run the diff through an LLM to decide if the captured claim still holds) is a v0.9.1 add-on.
- **Automatic re-extraction.** If a file changes, the brain flags affected sources but does NOT auto-rewrite the capture. Agent invokes `brain-revise` or `brain write` with new content.
- **Branch tracking.** `provenance_meta.commit_at_capture` is informational. Staleness compares against `HEAD` of the current branch; cross-branch diff is out of scope.
- **Watch mode.** No file-watcher daemon. Staleness is computed on-demand via the CLI or at session boundaries via the hook.
- **Non-git repos.** If `cwd` is not a git working tree, `brain staleness diff` falls back to whole-DB scan (`brain staleness check`).

---

## File structure (v0.9.0)

### Creations

```
src/brain/
  provenance.py                              # file_hash + attach_provenance + list_sources_for_files
  staleness.py                               # scan_db + scan_diff + StalenessReport + StaleSource
  alembic/versions/014_provenance_meta.py
skills/
  brain-staleness/SKILL.md
  brain-staleness/scripts/staleness.sh
tests/
  test_provenance.py                         # file_hash + attach_provenance + list_sources_for_files
  test_staleness.py                          # scan_db + scan_diff with fixtures (real temp git repo)
  test_brain_staleness_cli.py                # subprocess CLI smoke tests
  test_hook_session_end_staleness.py         # end-to-end: changed file → bundle carries the warning
docs/v0.9.0-staleness.md
```

### Modifications

```
src/brain/cli.py                             # brain write --from-file, brain decide --from-file, brain staleness sub-group
src/brain/hooks/cli.py                       # session_end_cmd appends staleness summary into the bundle render path
src/brain/hooks/bundle.py                    # BundleSelection gains a stale_sources list
src/brain/hooks/render.py                    # render the "Potentially stale sources" section
src/brain/schemas.py                         # SourceInput gains optional provenance_meta dict
src/brain/write.py                           # store provenance_meta in the INSERT
.claude-plugin/plugin.json                   # version 0.9.0
.claude-plugin/marketplace.json              # version 0.9.0
.cursor-plugin/plugin.json                   # version 0.9.0
.codex-plugin/plugin.json                    # version 0.9.0
README.md                                    # v0.9.0 section
BUGS.md                                      # if anything surfaces during impl
```

---

## Provenance schema

`sources.provenance_meta` JSONB shape:

```json
{
  "source_files": [
    {"path": "/abs/path/to/file.py", "sha256_at_capture": "abc123...", "line_range": [42, 67]}
  ],
  "commit_at_capture": "f3bf1d4abc...",
  "branch_at_capture": "main",
  "captured_at": "2026-05-28T10:00:00Z"
}
```

Indexed via `CREATE INDEX sources_provenance_files_gin_idx ON sources USING GIN ((provenance_meta->'source_files'))` so `WHERE provenance_meta->'source_files' @> '[{"path":"X"}]'::jsonb` is fast.

`provenance_meta` is NULL for sources captured before v0.9.0 — staleness scan silently skips those (graceful degradation).

---

## Staleness API

`StaleSource` dataclass:

```python
@dataclass(frozen=True)
class StaleSource:
    source_id: int
    kind: str
    uri: str | None
    path: str                        # absolute file path
    sha256_at_capture: str
    current_sha256: str | None       # None if file missing
    status: str                      # "changed" | "missing" | "untracked"
    line_range: tuple[int, int] | None
```

`StalenessReport`:

```python
@dataclass(frozen=True)
class StalenessReport:
    stale_sources: list[StaleSource]
    scanned_files: int               # # files inspected
    scanned_sources: int             # # sources with provenance_meta inspected
```

Two scans:

```python
def scan_db(engine: Engine) -> StalenessReport:
    """Whole-DB sweep: every active source with provenance_meta gets hash-compared
    against the live filesystem. O(sources)."""

def scan_diff(engine: Engine, *, since_ref: str = "HEAD~1", repo_cwd: str | None = None) -> StalenessReport:
    """Diff-based: run git diff --name-only <since_ref>..HEAD, find sources whose
    provenance_meta references any changed file, hash-compare those. O(changed_files)."""
```

Both are pure read — never mutate `sources.t_valid_to`. Mutation is the agent's job via `brain-revise` or `brain.write.invalidate`.

---

## Task 1: Migration 014 — `sources.provenance_meta` + GIN index

**Files:**
- Create: `src/brain/alembic/versions/014_provenance_meta.py`
- Create: `tests/test_provenance_migration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_provenance_migration.py`:

```python
"""Migration 014: sources.provenance_meta JSONB + GIN index on source_files."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope


def test_provenance_meta_column_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'sources' AND column_name = 'provenance_meta'"
            )
        ).first()
    assert row is not None
    assert row.data_type == "jsonb"


def test_provenance_files_gin_index_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "  AND tablename = 'sources' "
                "  AND indexname = 'sources_provenance_files_gin_idx'"
            )
        ).scalar()
    assert n == 1


def test_provenance_meta_defaults_null(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, status) "
                "VALUES ('note', 'no provenance', 'active') RETURNING id"
            )
        )
        row = s.execute(
            text(
                "SELECT provenance_meta FROM sources "
                "WHERE content = 'no provenance' LIMIT 1"
            )
        ).first()
    assert row is not None
    assert row.provenance_meta is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_provenance_migration.py -v`
Expected: FAIL — column doesn't exist yet.

- [ ] **Step 3: Implement the migration**

Create `src/brain/alembic/versions/014_provenance_meta.py`:

```python
"""sources.provenance_meta JSONB + GIN index on source_files for staleness lookups (v0.9.0).

Revision ID: 014_provenance_meta
Revises: 013_drop_event_kind_check
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "014_provenance_meta"
down_revision = "013_drop_event_kind_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("provenance_meta", JSONB(), nullable=True),
    )
    op.execute(
        "CREATE INDEX sources_provenance_files_gin_idx "
        "ON sources USING GIN ((provenance_meta->'source_files'))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sources_provenance_files_gin_idx")
    op.drop_column("sources", "provenance_meta")
```

- [ ] **Step 4: Apply migration**

Run: `.venv/bin/alembic upgrade head`
Expected: applies 014 cleanly. Output mentions `014_provenance_meta`.

Also apply to test DB:

Run: `BRAIN_DB_URL=postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain_test .venv/bin/alembic upgrade head`
Expected: same.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_provenance_migration.py -v`
Expected: PASS — 3 tests green.

- [ ] **Step 6: Commit**

```bash
git add src/brain/alembic/versions/014_provenance_meta.py tests/test_provenance_migration.py
git commit -m "feat(v0.9.0): migration 014 — sources.provenance_meta JSONB + GIN index"
```

---

## Task 2: Provenance helper module

**Files:**
- Create: `src/brain/provenance.py`
- Create: `tests/test_provenance.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_provenance.py`:

```python
"""brain.provenance — file hashing + provenance attachment + reverse lookup."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.provenance import (
    attach_provenance,
    file_hash,
    list_sources_for_files,
)


def test_file_hash_is_sha256_of_bytes(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("hello world\n")
    expected = hashlib.sha256(b"hello world\n").hexdigest()
    assert file_hash(f) == expected


def test_file_hash_returns_none_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.py"
    assert file_hash(missing) is None


def test_attach_provenance_writes_jsonb_to_source(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "f.py"
    f.write_text("body\n")

    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, status) "
                "VALUES ('decision', 'about f.py', 'active') RETURNING id"
            )
        ).scalar()

    attach_provenance(
        engine,
        source_id=int(sid),
        source_files=[{"path": str(f), "line_range": [1, 1]}],
        commit_at_capture="abc123",
        branch_at_capture="main",
    )

    with session_scope(engine) as s:
        meta = s.execute(
            text("SELECT provenance_meta FROM sources WHERE id = :i"), {"i": int(sid)}
        ).scalar()
    assert meta is not None
    assert meta["commit_at_capture"] == "abc123"
    assert meta["branch_at_capture"] == "main"
    assert len(meta["source_files"]) == 1
    sf = meta["source_files"][0]
    assert sf["path"] == str(f)
    assert sf["line_range"] == [1, 1]
    # sha256_at_capture auto-computed from the file contents.
    import hashlib as _h
    assert sf["sha256_at_capture"] == _h.sha256(b"body\n").hexdigest()


def test_attach_provenance_skips_missing_files(pg_url: str, tmp_path: Path) -> None:
    """If a referenced file doesn't exist at capture-time, sha256 is null but the
    entry still records its declared path (lets staleness scan flag it later)."""
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, status) "
                "VALUES ('decision', 'no file', 'active') RETURNING id"
            )
        ).scalar()

    missing = tmp_path / "nope.py"
    attach_provenance(
        engine,
        source_id=int(sid),
        source_files=[{"path": str(missing)}],
    )

    with session_scope(engine) as s:
        meta = s.execute(
            text("SELECT provenance_meta FROM sources WHERE id = :i"), {"i": int(sid)}
        ).scalar()
    assert meta["source_files"][0]["sha256_at_capture"] is None


def test_list_sources_for_files_finds_match(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "g.py"
    f.write_text("g body\n")

    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, status) "
                "VALUES ('gotcha', 'about g.py', 'active') RETURNING id"
            )
        ).scalar()
    attach_provenance(engine, source_id=int(sid), source_files=[{"path": str(f)}])

    matches = list_sources_for_files(engine, paths=[str(f)])
    assert int(sid) in {row.source_id for row in matches}


def test_list_sources_for_files_empty_paths(pg_url: str) -> None:
    engine = get_engine(pg_url)
    assert list_sources_for_files(engine, paths=[]) == []


def test_list_sources_for_files_ignores_invalidated(pg_url: str, tmp_path: Path) -> None:
    engine = get_engine(pg_url)
    f = tmp_path / "h.py"
    f.write_text("h\n")
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, status, t_valid_to) "
                "VALUES ('note', 'invalidated', 'active', NOW()) RETURNING id"
            )
        ).scalar()
    attach_provenance(engine, source_id=int(sid), source_files=[{"path": str(f)}])
    matches = list_sources_for_files(engine, paths=[str(f)])
    assert int(sid) not in {row.source_id for row in matches}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_provenance.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the module**

Create `src/brain/provenance.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_provenance.py -v`
Expected: PASS — 7 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/provenance.py tests/test_provenance.py
git commit -m "feat(v0.9.0): provenance helpers — file_hash + attach + reverse lookup"
```

---

## Task 3: Staleness module

**Files:**
- Create: `src/brain/staleness.py`
- Create: `tests/test_staleness.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_staleness.py`:

```python
"""brain.staleness — DB-wide scan + git-diff-driven scan."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

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
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, status) "
                "VALUES (:k, :c, 'active') RETURNING id"
            ),
            {"k": kind, "c": content},
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
    # Mutate the file post-capture.
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_staleness.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the module**

Create `src/brain/staleness.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_staleness.py -v`
Expected: PASS — 7 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/staleness.py tests/test_staleness.py
git commit -m "feat(v0.9.0): staleness scanner — DB-wide + diff-based modes"
```

---

## Task 4: CLI sub-group + `brain write --from-file` flag

**Files:**
- Modify: `src/brain/cli.py` (add `staleness` sub-group + `--from-file` to `brain write` and `brain decide`)
- Create: `tests/test_brain_staleness_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_brain_staleness_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_brain_staleness_cli.py -v`
Expected: FAIL — `--from-file` and `staleness` sub-group don't exist.

- [ ] **Step 3: Add `--from-file` to `brain write`**

In `src/brain/cli.py`, find the `write` command. Add the option + provenance call.

Add imports at the top alongside other `brain.*` imports:

```python
import subprocess as _subprocess
from brain.provenance import attach_provenance as _attach_provenance
```

Update the `write` command (around line 38):

```python
@main.command()
@click.option("--kind", required=True)
@click.option("--content", required=True)
@click.option("--uri")
@click.option("--project-id", type=int)
@click.option("--bucket", multiple=True, help="Repeatable: --bucket semantic --bucket episodic")
@click.option(
    "--from-file",
    multiple=True,
    help="File this knowledge was extracted from. Format: '/abs/path' or '/abs/path:start-end'. Repeatable.",
)
@click.pass_context
def write(
    ctx: click.Context,
    kind: str,
    content: str,
    uri: str | None,
    project_id: int | None,
    bucket: tuple[str, ...],
    from_file: tuple[str, ...],
) -> None:
    """Capture a source into the brain. Substantive kinds auto-embed (v0.8.4).
    --from-file attaches provenance for staleness tracking (v0.9.0)."""
    result = _write(
        ctx.obj["engine"],
        SourceInput(
            kind=kind,  # type: ignore[arg-type]
            content=content,
            uri=uri,
            project_id=project_id,
            buckets=list(bucket),  # type: ignore[arg-type]
        ),
        auto_embed=True,
    )
    if from_file:
        source_files = []
        for spec in from_file:
            path, _, lines = spec.partition(":")
            entry: dict = {"path": path}
            if lines and "-" in lines:
                a, _, b = lines.partition("-")
                try:
                    entry["line_range"] = [int(a), int(b)]
                except ValueError:
                    pass
            source_files.append(entry)
        commit = None
        try:
            commit = _subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True, stderr=_subprocess.DEVNULL
            ).strip()
        except _subprocess.CalledProcessError:
            pass
        branch = None
        try:
            branch = _subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, stderr=_subprocess.DEVNULL
            ).strip()
        except _subprocess.CalledProcessError:
            pass
        _attach_provenance(
            ctx.obj["engine"],
            source_id=result.source_id,
            source_files=source_files,
            commit_at_capture=commit,
            branch_at_capture=branch,
        )
    click.echo(json.dumps(result.model_dump()))
```

- [ ] **Step 4: Add the `staleness` sub-group**

After the existing `compliance` sub-group, add:

```python
from brain import staleness as _staleness


@main.group()
def staleness() -> None:
    """Detect when captured knowledge has gone stale (file changed since capture)."""


@staleness.command("check")
@click.pass_context
def staleness_check(ctx: click.Context) -> None:
    """Whole-DB sweep — every active source with provenance_meta hash-compared
    against the live filesystem."""
    report = _staleness.scan_db(ctx.obj["engine"])
    click.echo(
        f"scanned {report.scanned_sources} sources / {report.scanned_files} file references"
    )
    if not report.stale_sources:
        click.echo("0 stale sources — all tracked files match capture-time hashes.")
        return
    click.echo(f"{len(report.stale_sources)} stale source(s):")
    for s in report.stale_sources:
        line = f"  [{s.source_id}] kind={s.kind} status={s.status} path={s.path}"
        if s.line_range:
            line += f" lines={s.line_range[0]}-{s.line_range[1]}"
        click.echo(line)


@staleness.command("diff")
@click.option("--since", "since_ref", default="HEAD~1", help="git ref to diff against (default HEAD~1)")
@click.option("--cwd", "repo_cwd", default=None, help="repo cwd (default: current dir)")
@click.pass_context
def staleness_diff(ctx: click.Context, since_ref: str, repo_cwd: str | None) -> None:
    """Diff-based — only inspects files changed since the given git ref. Fast."""
    report = _staleness.scan_diff(
        ctx.obj["engine"], since_ref=since_ref, repo_cwd=repo_cwd
    )
    click.echo(
        f"scanned {report.scanned_files} changed files / {report.scanned_sources} matching sources"
    )
    if not report.stale_sources:
        click.echo("0 stale sources from the diff.")
        return
    click.echo(f"{len(report.stale_sources)} stale source(s):")
    for s in report.stale_sources:
        line = f"  [{s.source_id}] kind={s.kind} status={s.status} path={s.path}"
        if s.line_range:
            line += f" lines={s.line_range[0]}-{s.line_range[1]}"
        click.echo(line)
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_brain_staleness_cli.py -v`
Expected: PASS — 3 tests green.

- [ ] **Step 6: Commit**

```bash
git add src/brain/cli.py tests/test_brain_staleness_cli.py
git commit -m "feat(v0.9.0): brain staleness check/diff CLI + brain write --from-file"
```

---

## Task 5: SessionEnd hook surfaces staleness in resume bundle

**Files:**
- Modify: `src/brain/hooks/cli.py` (extend `session_end_cmd` to compute staleness count)
- Modify: `src/brain/hooks/bundle.py` (add `stale_sources` to `BundleSelection`)
- Modify: `src/brain/hooks/render.py` (render a "Potentially stale" section)
- Create: `tests/test_hook_session_end_staleness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hook_session_end_staleness.py`:

```python
"""SessionEnd hook records stale_sources count in session_events (v0.9.0)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from sqlalchemy import text

from brain.db import get_engine, session_scope


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
    from brain.provenance import attach_provenance
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, status) "
                "VALUES ('gotcha', 'about src.py', 'active') RETURNING id"
            )
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
    assert any(int(sid) == s["source_id"] for s in row.payload["stale_sources"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_hook_session_end_staleness.py -v`
Expected: FAIL — `staleness_detected` event isn't emitted yet.

- [ ] **Step 3: Extend `session_end_cmd`**

In `src/brain/hooks/cli.py`, find `session_end_cmd`. Add a staleness check inside the existing try/except non-fatal guard (just after the compliance check):

Add module imports near top:

```python
from brain.staleness import scan_db as _scan_db_staleness
```

Then inside `session_end_cmd`, AFTER the `if is_under_captured(stats):` block but still inside the try/except:

```python
# v0.9.0: Staleness check — flag sources whose source-files changed since capture.
try:
    sreport = _scan_db_staleness(engine)
    if sreport.stale_sources:
        record_event(
            engine, session_id=int(sid), event_kind="staleness_detected",
            payload={
                "stale_count": len(sreport.stale_sources),
                "scanned_sources": sreport.scanned_sources,
                "scanned_files": sreport.scanned_files,
                "stale_sources": [
                    {
                        "source_id": s.source_id,
                        "kind": s.kind,
                        "path": s.path,
                        "status": s.status,
                    }
                    for s in sreport.stale_sources[:50]  # cap payload size
                ],
            },
        )
except Exception as _exc:  # noqa: BLE001 — hook stays non-fatal
    record_event(
        engine, session_id=int(sid), event_kind="hook_error",
        payload={"hook": "session_end_staleness", "error": str(_exc)[:500]},
    )
```

Place this INSIDE the outer try/except that already wraps the compliance block, just before the `_emit_noop()`. Don't add new outer try blocks — reuse the existing non-fatal pattern.

- [ ] **Step 4: Run test**

Run: `.venv/bin/pytest tests/test_hook_session_end_staleness.py -v`
Expected: PASS — staleness_detected event recorded with the right source_id.

- [ ] **Step 5: Smoke regression**

Run: `.venv/bin/pytest tests/test_hook_session_end_compliance.py tests/test_hook_session_end_staleness.py tests/test_end_to_end_phase3a_1.py -v`
Expected: all green — no Phase 3a-4 regressions.

- [ ] **Step 6: Commit**

```bash
git add src/brain/hooks/cli.py tests/test_hook_session_end_staleness.py
git commit -m "feat(v0.9.0): SessionEnd hook records staleness_detected event"
```

---

## Task 6: Bundle render — surface staleness in the resume bundle

**Files:**
- Modify: `src/brain/hooks/bundle.py` (gather staleness signal from session_events into BundleSelection)
- Modify: `src/brain/hooks/render.py` (new "Potentially stale" section)

- [ ] **Step 1: Read existing bundle render**

Open `src/brain/hooks/bundle.py` and `src/brain/hooks/render.py`. Note how the existing sections (decisions/gotchas/etc.) flow from selection → manifest → markdown render.

- [ ] **Step 2: Extend BundleSelection**

In `src/brain/hooks/bundle.py`, add to the dataclass:

```python
@dataclass
class BundleSelection:
    decisions: list[dict[str, Any]] = field(default_factory=list)
    gotchas: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    subtasks_open: list[dict[str, Any]] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    stale_sources: list[dict[str, Any]] = field(default_factory=list)  # v0.9.0
```

In `gather_bundle_selection(...)` after the existing queries, append:

```python
# v0.9.0: pull the latest staleness_detected event for this session into the
# bundle so the next session sees what's potentially stale.
with session_scope(engine) as s:
    row = s.execute(
        text(
            "SELECT payload FROM session_events "
            "WHERE session_id = :sid AND event_kind = 'staleness_detected' "
            "ORDER BY occurred_at DESC LIMIT 1"
        ),
        {"sid": session_id},
    ).first()
    if row and row.payload:
        sel.stale_sources = list(row.payload.get("stale_sources") or [])[:limit_per_kind]
```

- [ ] **Step 3: Render the section**

In `src/brain/hooks/render.py`, find the section list `sections_in_priority` in `render_bundle(...)`. Add a new tuple BEFORE "Recent activity":

```python
(
    "Potentially stale sources (file changed since capture)",
    [
        f"[id={s['source_id']}] kind={s['kind']} status={s['status']} path={s['path']}"
        for s in selection.stale_sources
    ],
),
```

Also include `stale_sources` in the `manifest["selection"]` dict so the JSON manifest carries it too.

- [ ] **Step 4: Write a render test**

Add to `tests/test_bundle_render.py` (or create `tests/test_bundle_render_staleness.py`):

```python
"""Bundle render surfaces stale_sources when present (v0.9.0)."""

from __future__ import annotations

from datetime import datetime, timezone

from brain.hooks.bundle import BundleSelection
from brain.hooks.render import render_bundle


def test_render_includes_stale_sources_section() -> None:
    sel = BundleSelection(
        stale_sources=[
            {"source_id": 42, "kind": "decision", "path": "/x/y.py", "status": "changed"},
        ],
    )
    out = render_bundle(
        sel,
        cc_session_id="cc-stale-1",
        session_id=1,
        cwd="/tmp/r",
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime.now(timezone.utc),
    )
    assert "Potentially stale" in out.markdown
    assert "42" in out.markdown
    assert "/x/y.py" in out.markdown
    assert out.manifest["selection"]["stale_sources"] == sel.stale_sources


def test_render_omits_stale_section_when_empty() -> None:
    sel = BundleSelection()
    out = render_bundle(
        sel,
        cc_session_id="cc-stale-2",
        session_id=1,
        cwd="/tmp/r",
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime.now(timezone.utc),
    )
    assert "Potentially stale" not in out.markdown
```

- [ ] **Step 5: Run render tests**

Run: `.venv/bin/pytest tests/test_bundle_render.py tests/test_bundle_render_staleness.py -v`
Expected: PASS — staleness rendered when present, omitted when empty.

- [ ] **Step 6: Commit**

```bash
git add src/brain/hooks/bundle.py src/brain/hooks/render.py tests/test_bundle_render_staleness.py
git commit -m "feat(v0.9.0): bundle render surfaces stale sources in resume context"
```

---

## Task 7: `brain-staleness` skill

**Files:**
- Create: `skills/brain-staleness/SKILL.md`
- Create: `skills/brain-staleness/scripts/staleness.sh`

- [ ] **Step 1: Write the skill**

`skills/brain-staleness/SKILL.md`:

```markdown
---
name: brain-staleness
description: Use after editing files in this repo to find captured knowledge that may have gone stale, or before relying on a recall result to confirm the source file hasn't changed since capture. The brain detects file changes; you decide whether the captured claim still holds.
---

# brain-staleness

## When to use

- **After substantive edits to source files.** Run `brain staleness diff` to see which captured sources reference files you just touched.
- **Before relying on a recall result.** If `brain recall` returns a source about `src/foo.py`, optionally check whether `foo.py` has changed since the capture was created.
- **At session end (automatic).** The SessionEnd hook records a `staleness_detected` event into `session_events` and surfaces the count in the next session's resume bundle. You don't have to invoke this skill explicitly for that — but the skill provides the manual triage surface.

## When NOT to use

- The captures don't reference files (no `provenance_meta` — older captures pre-v0.9.0 or non-file captures).
- You haven't edited anything substantive yet (will return empty).

## How

```bash
# Diff-based scan — only the files changed since a git ref.
bash skills/brain-staleness/scripts/staleness.sh diff [--since HEAD~1]

# Whole-DB scan — every source with provenance_meta, hash-compared.
bash skills/brain-staleness/scripts/staleness.sh check
```

## Triage workflow

For each `[source_id]` returned:

1. Read the current file (or its diff vs the capture-time hash).
2. Decide: is the captured claim still true?
   - **Still true:** ignore. Optionally re-capture to refresh the hash (capture-time sha256 will update).
   - **Stale:** invalidate via `brain.write.invalidate(<source_id>, reason='...')`, OR re-capture the new claim and let dedup handle the rest, OR invoke `agent-brain:brain-revise` to propose structured invalidation.
3. If status is `missing`: the file no longer exists. Almost always invalidate.

## Output budget

≤200 tokens per call. The CLI prints one line per stale source — cite by ID in your response, don't paste full paths into prose.
```

`skills/brain-staleness/scripts/staleness.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec brain staleness "$@"
```

- [ ] **Step 2: chmod + smoke**

```bash
chmod +x skills/brain-staleness/scripts/staleness.sh
bash skills/brain-staleness/scripts/staleness.sh check
```

Expected: prints scan results (likely `0 stale sources` on a clean DB).

- [ ] **Step 3: Commit**

```bash
git add skills/brain-staleness/
git commit -m "feat(v0.9.0): brain-staleness skill"
```

---

## Task 8: Plugin manifests + docs + final verification

**Files:**
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`
- Create: `docs/v0.9.0-staleness.md`
- Modify: `README.md`

- [ ] **Step 1: Bump versions**

```bash
sed -i 's/"version": "0.8.5"/"version": "0.9.0"/g' .claude-plugin/plugin.json .claude-plugin/marketplace.json .cursor-plugin/plugin.json .codex-plugin/plugin.json
.venv/bin/python -c "import json; [json.load(open(p)) for p in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json','.cursor-plugin/plugin.json','.codex-plugin/plugin.json']]" && echo OK
```

Update the description lines to reference v0.9.0 staleness.

- [ ] **Step 2: Write `docs/v0.9.0-staleness.md`**

Sections:
- **Overview** — what staleness means, when to use which scan
- **Schema** — provenance_meta JSONB shape
- **Capture-time provenance** — `brain write --from-file` examples
- **Staleness CLIs** — `check` vs `diff`, when to pick each
- **Hook integration** — SessionEnd records `staleness_detected`, bundle surfaces it
- **Known limits** — no automatic re-capture, no LLM-semantic invalidation (use brain-revise), no cross-branch diff
- **Skills** — `brain-staleness`

Mirror the structure of `docs/phase3a_4.md` for consistency.

- [ ] **Step 3: README section**

Add a "Agent Brain v0.9.0 — Code-Aware Staleness" section after the existing 3a-4 section:

```markdown
## Agent Brain v0.9.0 — Code-Aware Staleness

`brain write --from-file path[:lines]` attaches sha256 + commit-at-capture to a source's `provenance_meta`. `brain staleness diff` (cheap, git-driven) and `brain staleness check` (whole-DB) flag sources whose referenced files have changed since capture. SessionEnd hook auto-runs the scan and records a `staleness_detected` event; the next session's resume bundle surfaces the count + a list of source IDs.

```bash
brain write --kind decision --content "..." --from-file src/cli.py:42-67
brain staleness diff --since HEAD~5
brain staleness check
```

Operations: `docs/v0.9.0-staleness.md`. Plan: `docs/superpowers/plans/2026-05-28-agent-brain-v0.9.0-staleness.md`.
```

- [ ] **Step 4: Full test suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: all green (~264 + new ones from this plan = ~285+).

- [ ] **Step 5: End-to-end smoke**

```bash
# Capture a source from a file.
echo "hello" > /tmp/foo.py
brain write --kind decision --content "foo prints hello" --from-file /tmp/foo.py

# Change the file.
echo "goodbye" > /tmp/foo.py

# Scan.
brain staleness check
# Expected: the just-captured source appears as 'changed'.

# Cleanup.
rm /tmp/foo.py
brain staleness check
# Expected: status='missing' for the source now.
```

- [ ] **Step 6: Commit + merge + tag**

```bash
git add .claude-plugin/ .cursor-plugin/ .codex-plugin/ docs/v0.9.0-staleness.md README.md
git commit -m "docs(v0.9.0): operations + README + manifests"

git checkout main
git merge --no-ff <branch-name> -m "Merge v0.9.0-staleness: code-aware staleness detection"
git tag v0.9.0 -m "v0.9.0 — code-aware staleness detection"
git push origin main && git push origin v0.9.0
```

---

## Self-review checklist (post-draft)

1. **Spec coverage** — three layers from the conversation:
   - Layer 1: provenance_meta column + capture-time attachment → Tasks 1, 2, 4 ✓
   - Layer 2: scan_db + scan_diff CLIs → Tasks 3, 4 ✓
   - Layer 3: SessionEnd hook + bundle render → Tasks 5, 6 ✓
   - Skill surface → Task 7 ✓
   - Docs + manifests → Task 8 ✓

2. **Placeholder scan** — no "TBD" / "implement appropriate" / "fill in details". Every code block contains complete, runnable code.

3. **Type consistency:**
   - `StaleSource` defined in Task 3, consumed in Tasks 4-6 with same fields.
   - `StalenessReport` defined in Task 3, consumed in Task 4 + 5.
   - `ProvenanceMatch` defined in Task 2, consumed in Task 3.
   - `attach_provenance(..., source_id, source_files, commit_at_capture, branch_at_capture)` consistent across Tasks 2, 4, 5.
   - `scan_db(engine)` / `scan_diff(engine, *, since_ref, repo_cwd)` consistent across Tasks 3-6.

---

## Risk notes (for reviewer + executor)

- **Performance of scan_db on large DBs.** If there are thousands of sources with provenance_meta, the whole-DB scan does N file reads. Mitigation: prefer scan_diff for routine use. scan_db is intended for manual audits / `brain health` style sweeps.
- **`from-file` path interpretation.** Plan uses absolute paths. Relative paths would be ambiguous when CWD differs at capture vs scan time. CLI should `os.path.abspath()` or refuse relative paths — implementer should pick one and document.
- **Cross-branch staleness.** If the agent captures on branch A, then `git checkout B`, scan_db will hash the B-version of the file. Status may flap. Document as "staleness is computed against current working tree, not branch-at-capture."
- **SessionEnd performance.** scan_db runs synchronously inside the SessionEnd hook. For a brain with 1000+ sources this could add seconds. Mitigation in v0.9.1: switch SessionEnd to scan_diff with `since=session_start_commit`. For v0.9.0 ship scan_db and document the limit.
- **JSON containment query specificity.** `provenance_meta->'source_files' @> '[{"path":"X"}]'` matches if ANY array element has that path. Correct — what we want.
