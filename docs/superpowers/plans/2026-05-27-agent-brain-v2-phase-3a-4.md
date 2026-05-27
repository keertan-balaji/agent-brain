# Agent Brain v2 — Phase 3a-4 Implementation Plan (Compliance Subsystem)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make non-capture visible. Add a compliance subsystem that detects under-captured sessions (≥5 user turns + <3 substantive captures), flags "thin" resume bundles (no decisions / gotchas / failures / open subtasks), surfaces both in `brain health` + `brain status`, and optionally fails the SessionEnd hook hard via `brain_config.strict_mode`. The existing `health.audit` query counts the wrong table (`events` instead of session-scoped substantive captures) — Phase 3a-4 fixes it.

**Architecture:** One new pure module — `src/brain/compliance.py` — exposes `session_capture_stats(engine, session_id) -> CaptureStats`, `is_under_captured(stats, ...) -> bool`, and `is_thin_bundle(selection) -> bool`. The SessionEnd hook (already wired in 3a-1) calls `session_capture_stats` after the bundle is generated, records a `session_events(event_kind='under_captured')` row if applicable, and exits non-zero IFF `brain_config.strict_mode='true'`. The PreCompact / session-end bundle path additionally writes a `session_events(event_kind='thin_session')` row when the bundle selection is empty. `brain.helpers.health.audit()` is rewritten to use the new compliance helper instead of its current naive `events` LEFT JOIN. `brain status` gets a thin-session-count line. Tests cover each helper purely and one end-to-end test drives the SessionEnd hook through subprocess with both strict + permissive modes.

**Tech Stack:** Python 3.12, Postgres, SQLAlchemy 2.0, Click. No new runtime deps; no new tables; no migration. `brain_config` already has the `(key, value, updated_at)` shape we need.

**Spec reference:** `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md` § "Compliance (enforcement of 'the agent must comply')" — three teeth: (1) SessionEnd capture-completeness check, (2) thin-session auto-flag, (3) optional strict mode.

**Phase 3a-1/2/3 prerequisites in place (verified live):**
- `sessions` table has `cc_session_id`, `cwd`, `started_at`, `ended_at` columns.
- `session_events` table is the hook-side per-session log (event_kinds: `session_start`, `user_prompt_submit`, `stop`, `session_end`, `hook_error`, `pre_compact`).
- `brain_config(key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMPTZ)` already exists.
- `helpers/health.py` audit + `brain health` CLI already exist (current undercapture logic is broken — see below).
- `session_end_cmd` in `src/brain/hooks/cli.py` already calls `end_session` and `record_event(event_kind='session_end')`. We extend it.
- `gather_bundle_selection` returns a `BundleSelection` dataclass with 6 list fields (decisions/gotchas/patterns/failures/subtasks_open/recent_events) — the thin-check is `all(len(getattr(sel, k)) == 0 for k in [...])` on the substantive subset.

---

## Empirical findings (locked in, verified live)

1. **`helpers/health.py:58-71` query is wrong.** It counts rows in the canonical `events` table (subtask-scoped episodic stream) joined on `sessions.id`. But Claude Code sessions never write to `events` — they write to `session_events` (lifecycle hooks) and to `sources` (substantive captures via `brain.write`). Result: every real Claude Code session shows `event_count = 0` and gets filtered out by `HAVING COUNT(ev.id) > 0`, so the audit reports zero under-captured sessions even when nothing was captured. Phase 3a-4 fixes this by querying the right surfaces.

2. **`session_events` already carries the per-turn signal.** Every `UserPromptSubmit` hook fires `record_event(event_kind='user_prompt_submit', ...)`. Counting those rows for a session gives the turn count without parsing the transcript.

3. **Substantive capture-worthy kinds** per the spec's memory taxonomy + existing classifier: `decision`, `gotcha`, `pattern`, `note`, `subtask_summary`, `session_summary`. These are captured via `brain.write` during a session; we look them up by `created_at` falling within `sessions.started_at` ≤ ts < `COALESCE(sessions.ended_at, NOW())` for the right `project_id` (or `project_id IS NULL` if no project row exists for the cwd yet).

4. **`brain_config` is queryable today.** A row `('strict_mode', 'true')` reads as `'true'` (string) — comparison must be against the literal string, not Python `True`.

---

## Scope this plan does NOT cover

- **Phase 3a-3** (file watcher: Obsidian → DB conflict detection). Independent from 3a-4; can land before or after.
- **Phase 4** (`brain-health --lint` generative pass over top-k similar chunks for contradiction surfacing). 3a-4 ships the audit and the compliance counters; Phase 4 layers LLM-driven lint on top.
- **`brain-schema-evolve`** skill (proposes AGENTS.md amendments from compliance signal). Spec lists it under Phase 4.
- **Turn-count tightening.** The spec says "≥5 Claude turns (detectable from session transcript metadata)" — we use `session_events.event_kind='user_prompt_submit' count` as the proxy. If a future plan wants transcript-derived turn count (richer signal — counts assistant turns too), it can extend `session_capture_stats`. The dataclass leaves `turn_count` extensible.
- **Auto-remediation.** Compliance is observability + nudges. We do not synthesize captures the agent failed to make. The agent reads the warning at next session start and is expected to behave.

---

## File structure (Phase 3a-4)

### Creations

```
src/brain/
  compliance.py                              # CaptureStats + is_under_captured + is_thin_bundle (pure)
skills/
  brain-compliance/SKILL.md
  brain-compliance/scripts/compliance.sh
tests/
  test_compliance.py                         # 6-8 unit tests on the helpers
  test_hook_session_end_compliance.py        # end-to-end SessionEnd hook flow (permissive + strict)
  test_health_undercapture_query.py          # regression test: health audit now reports real sessions
docs/phase3a_4.md
```

### Modifications

```
src/brain/hooks/cli.py                       # session_end_cmd: compute stats, record under_captured event, gate exit on strict_mode
src/brain/hooks/bundle.py                    # gather_bundle_selection: also return bool for is_thin (or use is_thin_bundle on result)
src/brain/helpers/health.py                  # audit: replace events-join query with compliance.under_captured_sessions(engine)
src/brain/cli.py                             # brain compliance CLI sub-group (check, list-thin); extend brain status with thin-session count
.claude-plugin/plugin.json                   # version 0.7.0, description update
.claude-plugin/marketplace.json              # version 0.7.0, description + skill count update
.cursor-plugin/plugin.json                   # version 0.7.0
.codex-plugin/plugin.json                    # version 0.7.0, description update
README.md                                    # Phase 3a-4 section
docs/operations.md                           # Compliance triage subsection
```

No new migration. `brain_config` and `session_events` already exist.

---

## Compliance helper design (`src/brain/compliance.py`)

### `CaptureStats` dataclass

```python
@dataclass(frozen=True)
class CaptureStats:
    session_id: int
    cc_session_id: str | None
    project_id: int | None
    turn_count: int              # COUNT(session_events WHERE event_kind='user_prompt_submit')
    capture_count: int           # COUNT(sources in capture-worthy kinds, created during session)
    decision_count: int          # subset of capture_count, kind='decision'
    gotcha_count: int            # subset, kind='gotcha'
    subtask_summary_count: int   # subset, kind='subtask_summary'
    failure_count: int           # COUNT(failure_memories created during session)
```

### Public API

```python
_CAPTURE_KINDS: frozenset[str] = frozenset({
    "decision", "gotcha", "pattern", "note", "subtask_summary", "session_summary"
})


def session_capture_stats(engine: Engine, *, session_id: int) -> CaptureStats:
    """Pure SQL aggregation. Single round-trip. No external state."""

def is_under_captured(
    stats: CaptureStats,
    *,
    turn_threshold: int = 5,
    capture_threshold: int = 3,
) -> bool:
    """True iff turn_count >= turn_threshold AND capture_count < capture_threshold.
       Below the turn threshold = exploratory / one-shot work, not under-captured."""

def is_thin_bundle(selection: BundleSelection) -> bool:
    """True iff selection has no decisions, gotchas, failures, AND no open subtasks.
       Patterns and recent_events alone don't save a bundle from being thin."""

def under_captured_sessions(
    engine: Engine,
    *,
    turn_threshold: int = 5,
    capture_threshold: int = 3,
    since: datetime | None = None,
) -> list[CaptureStats]:
    """Audit query: all ended sessions matching the under-captured predicate.
       `since=None` means scan all history; pass a datetime to bound the report."""

def is_strict_mode(engine: Engine) -> bool:
    """Read brain_config WHERE key='strict_mode'. Compare value literally to 'true'."""
```

### `session_capture_stats` SQL

Single query, four counts via subqueries:

```sql
SELECT
  sess.id, sess.cc_session_id, sess.project_id,
  (SELECT COUNT(*) FROM session_events
     WHERE session_id = sess.id AND event_kind = 'user_prompt_submit') AS turn_count,
  (SELECT COUNT(*) FROM sources s
     WHERE s.kind = ANY(:capture_kinds)
       AND s.project_id IS NOT DISTINCT FROM sess.project_id
       AND s.created_at >= sess.started_at
       AND s.created_at < COALESCE(sess.ended_at, NOW())) AS capture_count,
  (SELECT COUNT(*) FROM sources s
     WHERE s.kind = 'decision'
       AND s.project_id IS NOT DISTINCT FROM sess.project_id
       AND s.created_at >= sess.started_at
       AND s.created_at < COALESCE(sess.ended_at, NOW())) AS decision_count,
  (SELECT COUNT(*) FROM sources s
     WHERE s.kind = 'gotcha'
       AND s.project_id IS NOT DISTINCT FROM sess.project_id
       AND s.created_at >= sess.started_at
       AND s.created_at < COALESCE(sess.ended_at, NOW())) AS gotcha_count,
  (SELECT COUNT(*) FROM sources s
     WHERE s.kind = 'subtask_summary'
       AND s.project_id IS NOT DISTINCT FROM sess.project_id
       AND s.created_at >= sess.started_at
       AND s.created_at < COALESCE(sess.ended_at, NOW())) AS subtask_summary_count,
  (SELECT COUNT(*) FROM failure_memories fm
     WHERE fm.project_id IS NOT DISTINCT FROM sess.project_id
       AND fm.first_attempted_at >= sess.started_at
       AND fm.first_attempted_at < COALESCE(sess.ended_at, NOW())) AS failure_count
FROM sessions sess
WHERE sess.id = :sid
```

`IS NOT DISTINCT FROM` handles the `NULL = NULL` semantics — when a session has no project_id, only project-less sources count toward it.

### `under_captured_sessions` query

```sql
SELECT
  sess.id, sess.cc_session_id, sess.project_id, sess.started_at, sess.ended_at,
  (SELECT COUNT(*) FROM session_events
     WHERE session_id = sess.id AND event_kind = 'user_prompt_submit') AS turn_count,
  (SELECT COUNT(*) FROM sources s
     WHERE s.kind = ANY(:kinds)
       AND s.project_id IS NOT DISTINCT FROM sess.project_id
       AND s.created_at >= sess.started_at
       AND s.created_at < COALESCE(sess.ended_at, NOW())) AS capture_count
FROM sessions sess
WHERE sess.ended_at IS NOT NULL
  AND (:since IS NULL OR sess.ended_at >= :since)
HAVING turn_count >= :turn_t AND capture_count < :cap_t
ORDER BY sess.ended_at DESC
LIMIT 50
```

(Postgres lets `HAVING` reference subquery columns by alias inside the outer `SELECT`'s context when the query is reshaped — if the parser rejects this in 16+, fall back to a CTE that materializes turn_count/capture_count then filters.)

---

## SessionEnd flow change

Current (3a-1) `session_end_cmd`:
1. `end_session(engine, cc_session_id, reason)` — sets `sessions.ended_at`.
2. `record_event(session_id=sid, event_kind='session_end', payload={'reason': reason})`.
3. `_emit_noop()`.

Phase 3a-4 inserts between steps 2 and 3:

```python
stats = session_capture_stats(engine, session_id=sid)
if is_under_captured(stats):
    record_event(
        engine, session_id=sid, event_kind='under_captured',
        payload={
            'turn_count': stats.turn_count,
            'capture_count': stats.capture_count,
            'decision_count': stats.decision_count,
            'gotcha_count': stats.gotcha_count,
            'subtask_summary_count': stats.subtask_summary_count,
        },
    )
    if is_strict_mode(engine):
        _emit_noop()
        ctx.exit(2)   # non-zero exit surfaces a system-reminder in the next session
```

Wrapped in `try/except Exception` so the compliance check is non-fatal (the SessionEnd hook itself never propagates exceptions — matches the Stop hook precedent from 3a-2).

---

## Thin-bundle flow change

In the PreCompact path (existing `pre_compact_cmd`) AND the SessionEnd path (which currently doesn't generate a bundle — Phase 3a-1 only writes a bundle on PreCompact, so this is structurally pre-compact-only):

```python
sel = gather_bundle_selection(...)
if is_thin_bundle(sel):
    record_event(
        engine, session_id=sid, event_kind='thin_session',
        payload={'cwd': inp.cwd, 'trigger': 'pre_compact'},
    )
# ... existing render + insert path ...
```

For SessionEnd in 3a-4 scope: skip thin-bundle emission (no bundle generated). The under-captured signal already covers SessionEnd. PreCompact gets the thin-session emission since that's where bundles are born.

---

## `brain status` extension

Add one line after the existing tables:

```
Compliance: under-captured sessions (last 30 days): N | thin sessions (last 30 days): M
```

Both numbers come from `session_events` aggregation — no extra joins.

---

## `brain compliance` CLI sub-group

```bash
brain compliance check --session-id <N>     # print stats + verdict for a specific session
brain compliance list --limit 20            # recent under-captured sessions
brain compliance list-thin --limit 20       # recent thin sessions
```

Mirrors `brain failure` shape from 3a-2.

---

## Task 1: Compliance helper module — stats + predicates

**Files:**
- Create: `src/brain/compliance.py`
- Create: `tests/test_compliance.py`

### Repo conventions

Tests use `pg_url: str` fixture, NOT `engine`. Construct `engine = get_engine(pg_url)` inside each test. The `_truncate_tables` fixture truncates between tests. `session_events` is included in the truncate list — confirm before writing tests that reference it across tests.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_compliance.py`:

```python
"""src/brain/compliance.py — capture stats + under-captured + thin-bundle helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.compliance import (
    CaptureStats,
    is_strict_mode,
    is_thin_bundle,
    is_under_captured,
    session_capture_stats,
    under_captured_sessions,
)
from brain.db import get_engine, session_scope
from brain.hooks.bundle import BundleSelection
from brain.schemas import SourceInput
from brain.write import write


def _make_session(engine, *, project_id=None, started_at=None, ended_at=None) -> int:
    started = started_at or (datetime.now(timezone.utc) - timedelta(hours=1))
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent, started_at, ended_at, cwd) "
                "VALUES (:p, 'claude-code', :st, :en, '/tmp/x') RETURNING id"
            ),
            {"p": project_id, "st": started, "en": ended_at},
        ).scalar()
    return int(sid)


def _record_turns(engine, *, session_id: int, n: int) -> None:
    with session_scope(engine) as s:
        for i in range(n):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload, occurred_at) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb, NOW() - (:i * INTERVAL '1 minute'))"
                ),
                {"sid": session_id, "i": i},
            )


def test_session_capture_stats_empty_session(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _make_session(engine)
    stats = session_capture_stats(engine, session_id=sid)
    assert stats.session_id == sid
    assert stats.turn_count == 0
    assert stats.capture_count == 0
    assert stats.decision_count == 0
    assert stats.failure_count == 0


def test_session_capture_stats_counts_turns_and_captures(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _make_session(engine, ended_at=datetime.now(timezone.utc) + timedelta(hours=1))
    _record_turns(engine, session_id=sid, n=6)
    write(engine, SourceInput(kind="decision", content="we picked Postgres"))
    write(engine, SourceInput(kind="gotcha", content="halfvec needs ::halfvec cast"))
    write(engine, SourceInput(kind="note", content="nb on the migration order"))
    stats = session_capture_stats(engine, session_id=sid)
    assert stats.turn_count == 6
    assert stats.capture_count == 3
    assert stats.decision_count == 1
    assert stats.gotcha_count == 1


def test_session_capture_stats_excludes_captures_outside_window(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # Session window: 2h ago -> 1h ago.
    now = datetime.now(timezone.utc)
    sid = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
    # NOW() created_at is OUTSIDE the [started_at, ended_at) window.
    write(engine, SourceInput(kind="decision", content="late-arriving decision"))
    stats = session_capture_stats(engine, session_id=sid)
    assert stats.capture_count == 0


def test_is_under_captured_true_when_many_turns_few_captures() -> None:
    stats = CaptureStats(
        session_id=1, cc_session_id="x", project_id=None,
        turn_count=6, capture_count=2,
        decision_count=0, gotcha_count=0, subtask_summary_count=0, failure_count=0,
    )
    assert is_under_captured(stats) is True


def test_is_under_captured_false_below_turn_threshold() -> None:
    stats = CaptureStats(
        session_id=1, cc_session_id="x", project_id=None,
        turn_count=3, capture_count=0,
        decision_count=0, gotcha_count=0, subtask_summary_count=0, failure_count=0,
    )
    assert is_under_captured(stats) is False  # exploratory / one-shot, not under-captured


def test_is_under_captured_false_when_capture_threshold_met() -> None:
    stats = CaptureStats(
        session_id=1, cc_session_id="x", project_id=None,
        turn_count=10, capture_count=3,
        decision_count=1, gotcha_count=1, subtask_summary_count=1, failure_count=0,
    )
    assert is_under_captured(stats) is False  # exactly at threshold, NOT under-captured (strict <)


def test_is_thin_bundle_true_when_all_substantive_empty() -> None:
    sel = BundleSelection()
    assert is_thin_bundle(sel) is True


def test_is_thin_bundle_false_with_open_subtask() -> None:
    sel = BundleSelection(subtasks_open=[{"subtask_id": 1, "title": "x", "goal": "y"}])
    assert is_thin_bundle(sel) is False


def test_is_thin_bundle_false_with_decision() -> None:
    sel = BundleSelection(decisions=[{"source_id": 1, "kind": "decision", "head": "..."}])
    assert is_thin_bundle(sel) is False


def test_is_thin_bundle_patterns_alone_still_thin() -> None:
    sel = BundleSelection(patterns=[{"source_id": 1, "kind": "pattern", "head": "..."}])
    # Patterns alone don't save a bundle — must have at least one of decisions/gotchas/failures/subtasks.
    assert is_thin_bundle(sel) is True


def test_under_captured_sessions_returns_only_qualifying(pg_url: str) -> None:
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)

    # Sess A: 6 turns, 0 captures, ended → under-captured.
    a = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
    _record_turns(engine, session_id=a, n=6)

    # Sess B: 6 turns, 5 captures within window → NOT under-captured.
    b = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now + timedelta(hours=1))
    _record_turns(engine, session_id=b, n=6)
    for i in range(5):
        write(engine, SourceInput(kind="decision", content=f"d{i}"))

    # Sess C: 3 turns, 0 captures → below turn threshold, NOT under-captured.
    c = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
    _record_turns(engine, session_id=c, n=3)

    # Sess D: 6 turns, 0 captures, NOT ENDED → excluded (only ended sessions audited).
    d = _make_session(engine, started_at=now - timedelta(hours=2), ended_at=None)
    _record_turns(engine, session_id=d, n=6)

    rows = under_captured_sessions(engine)
    ids = {r.session_id for r in rows}
    assert a in ids
    assert b not in ids
    assert c not in ids
    assert d not in ids


def test_is_strict_mode_false_when_unset(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # brain_config has no strict_mode key by default.
    assert is_strict_mode(engine) is False


def test_is_strict_mode_true_when_set_true(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO brain_config(key, value, updated_at) "
                "VALUES ('strict_mode', 'true', NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value"
            )
        )
    assert is_strict_mode(engine) is True


def test_is_strict_mode_false_when_set_false(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO brain_config(key, value, updated_at) "
                "VALUES ('strict_mode', 'false', NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value"
            )
        )
    assert is_strict_mode(engine) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_compliance.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the module**

Create `src/brain/compliance.py`:

```python
"""Compliance helpers (Phase 3a-4).

Three teeth (spec §Compliance):
1. session_capture_stats + is_under_captured — surface non-capture.
2. is_thin_bundle — surface near-empty resume bundles.
3. is_strict_mode — gate the SessionEnd hook's non-zero exit.

Pure: SQL aggregation + dataclass predicates. No I/O outside the supplied engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.hooks.bundle import BundleSelection


_CAPTURE_KINDS: frozenset[str] = frozenset({
    "decision", "gotcha", "pattern", "note", "subtask_summary", "session_summary"
})


@dataclass(frozen=True)
class CaptureStats:
    session_id: int
    cc_session_id: str | None
    project_id: int | None
    turn_count: int
    capture_count: int
    decision_count: int
    gotcha_count: int
    subtask_summary_count: int
    failure_count: int


def session_capture_stats(engine: Engine, *, session_id: int) -> CaptureStats:
    """Aggregate per-session capture counts in a single round-trip."""
    sql = text(
        """
        SELECT
          sess.id AS sid,
          sess.cc_session_id,
          sess.project_id,
          (SELECT COUNT(*) FROM session_events
             WHERE session_id = sess.id AND event_kind = 'user_prompt_submit') AS turn_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = ANY(:capture_kinds)
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS capture_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = 'decision'
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS decision_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = 'gotcha'
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS gotcha_count,
          (SELECT COUNT(*) FROM sources s
             WHERE s.kind = 'subtask_summary'
               AND s.project_id IS NOT DISTINCT FROM sess.project_id
               AND s.created_at >= sess.started_at
               AND s.created_at < COALESCE(sess.ended_at, NOW())) AS subtask_summary_count,
          (SELECT COUNT(*) FROM failure_memories fm
             WHERE fm.project_id IS NOT DISTINCT FROM sess.project_id
               AND fm.first_attempted_at >= sess.started_at
               AND fm.first_attempted_at < COALESCE(sess.ended_at, NOW())) AS failure_count
        FROM sessions sess
        WHERE sess.id = :sid
        """
    )
    with session_scope(engine) as s:
        row = s.execute(
            sql, {"capture_kinds": list(_CAPTURE_KINDS), "sid": session_id}
        ).first()
    if row is None:
        raise ValueError(f"session {session_id} not found")
    return CaptureStats(
        session_id=row.sid,
        cc_session_id=row.cc_session_id,
        project_id=row.project_id,
        turn_count=int(row.turn_count),
        capture_count=int(row.capture_count),
        decision_count=int(row.decision_count),
        gotcha_count=int(row.gotcha_count),
        subtask_summary_count=int(row.subtask_summary_count),
        failure_count=int(row.failure_count),
    )


def is_under_captured(
    stats: CaptureStats,
    *,
    turn_threshold: int = 5,
    capture_threshold: int = 3,
) -> bool:
    """Sessions below the turn threshold are exploratory, not under-captured."""
    return stats.turn_count >= turn_threshold and stats.capture_count < capture_threshold


def is_thin_bundle(selection: BundleSelection) -> bool:
    """A bundle is thin when no substantive content survives compaction.
    Patterns and recent_events alone don't qualify a bundle as non-thin —
    they're support material, not durable decisions/failures."""
    return (
        not selection.decisions
        and not selection.gotchas
        and not selection.failures
        and not selection.subtasks_open
    )


def under_captured_sessions(
    engine: Engine,
    *,
    turn_threshold: int = 5,
    capture_threshold: int = 3,
    since: datetime | None = None,
    limit: int = 50,
) -> list[CaptureStats]:
    """Audit query: ended sessions matching the under-captured predicate."""
    sql = text(
        """
        WITH per_session AS (
          SELECT
            sess.id AS sid,
            sess.cc_session_id,
            sess.project_id,
            sess.started_at,
            sess.ended_at,
            (SELECT COUNT(*) FROM session_events
               WHERE session_id = sess.id AND event_kind = 'user_prompt_submit') AS tc,
            (SELECT COUNT(*) FROM sources s
               WHERE s.kind = ANY(:kinds)
                 AND s.project_id IS NOT DISTINCT FROM sess.project_id
                 AND s.created_at >= sess.started_at
                 AND s.created_at < COALESCE(sess.ended_at, NOW())) AS cc
          FROM sessions sess
          WHERE sess.ended_at IS NOT NULL
            AND (:since IS NULL OR sess.ended_at >= :since)
        )
        SELECT sid, cc_session_id, project_id, tc, cc
        FROM per_session
        WHERE tc >= :turn_t AND cc < :cap_t
        ORDER BY ended_at DESC NULLS LAST
        LIMIT :lim
        """
    )
    with session_scope(engine) as s:
        rows = s.execute(
            sql,
            {
                "kinds": list(_CAPTURE_KINDS),
                "since": since,
                "turn_t": turn_threshold,
                "cap_t": capture_threshold,
                "lim": limit,
            },
        ).all()
    # The audit-list shape carries only the headline counts. Detail fields stay 0
    # — callers wanting full detail per row call session_capture_stats by id.
    return [
        CaptureStats(
            session_id=r.sid,
            cc_session_id=r.cc_session_id,
            project_id=r.project_id,
            turn_count=int(r.tc),
            capture_count=int(r.cc),
            decision_count=0,
            gotcha_count=0,
            subtask_summary_count=0,
            failure_count=0,
        )
        for r in rows
    ]


def is_strict_mode(engine: Engine) -> bool:
    """Read brain_config WHERE key='strict_mode'. Literal string compare against 'true'."""
    with session_scope(engine) as s:
        val = s.execute(
            text("SELECT value FROM brain_config WHERE key = 'strict_mode'")
        ).scalar()
    return val == "true"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_compliance.py -v`
Expected: PASS — all 13 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/compliance.py tests/test_compliance.py
git commit -m "feat(p3a-4): compliance module (capture stats + thin-bundle + strict-mode)"
```

---

## Task 2: Replace `health.audit` undercapture query with compliance helper

**Files:**
- Modify: `src/brain/helpers/health.py`
- Create: `tests/test_health_undercapture_query.py`

### Context

The current `health.audit` query at `src/brain/helpers/health.py:58-77` LEFT JOINs `sessions` to the `events` table (episodic stream). Claude Code sessions never write to `events` — they write to `session_events` (lifecycle) and `sources` (substantive captures). The audit reports zero under-captured sessions even when nothing was captured. We swap it for `under_captured_sessions` from Task 1.

- [ ] **Step 1: Write the failing regression test**

Create `tests/test_health_undercapture_query.py`:

```python
"""brain health audit reports under-captured sessions correctly (Phase 3a-4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.helpers.health import audit


def _make_session(engine, *, ended_at) -> int:
    started = datetime.now(timezone.utc) - timedelta(hours=2)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, ended_at, cwd) "
                "VALUES ('claude-code', :st, :en, '/tmp/x') RETURNING id"
            ),
            {"st": started, "en": ended_at},
        ).scalar()
    return int(sid)


def _record_turns(engine, *, session_id, n):
    with session_scope(engine) as s:
        for _ in range(n):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb)"
                ),
                {"sid": session_id},
            )


def test_audit_reports_undercaptured_via_session_events_not_events_table(pg_url: str) -> None:
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    sid = _make_session(engine, ended_at=now - timedelta(minutes=10))
    _record_turns(engine, session_id=sid, n=6)
    # Zero captures during the window.
    report = audit(engine)
    ids = {u.session_id for u in report.undercaptured_sessions}
    assert sid in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_health_undercapture_query.py -v`
Expected: FAIL — current `audit()` uses the `events` table, doesn't surface this session.

- [ ] **Step 3: Rewrite the undercapture section of `audit()`**

In `src/brain/helpers/health.py`, replace the existing undercapture query block (lines ~58-77) with a delegation to the compliance helper:

```python
from brain.compliance import under_captured_sessions

# ... inside audit() ...
# Remove the lines that execute the old session/events LEFT JOIN.
rows = under_captured_sessions(
    engine,
    turn_threshold=5,
    capture_threshold=undercapture_threshold,
    limit=50,
)
report.undercaptured_sessions = [
    UndercapturedSession(
        session_id=r.session_id,
        project_id=r.project_id,
        event_count=r.capture_count,  # rename in the field's meaning; see note below
    )
    for r in rows
]
```

The `UndercapturedSession.event_count` field's NAME stays for back-compat with `brain health` table rendering, but its MEANING shifts from "events table count" to "substantive captures count". Acceptable rename — the column header in the audit table doesn't promise an events.id count, it promises a capture-completeness count.

Adjust the `audit()` signature to accept `turn_threshold` if you want CLI override later — for this phase, hardcode 5 inside the call site. Keep `undercapture_threshold` as the existing-named parameter that maps to `capture_threshold` of the new helper.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_health_undercapture_query.py tests/test_compliance.py -v`
Expected: PASS — both files green. Then:

Run: `.venv/bin/pytest tests/ -q -k "health or compliance"`
Expected: All green, no regression.

- [ ] **Step 5: Commit**

```bash
git add src/brain/helpers/health.py tests/test_health_undercapture_query.py
git commit -m "fix(p3a-4): health audit uses substantive captures (was counting wrong table)"
```

---

## Task 3: SessionEnd hook — compute stats, record under_captured, gate exit on strict_mode

**Files:**
- Modify: `src/brain/hooks/cli.py`
- Create: `tests/test_hook_session_end_compliance.py`

### Read first

- `src/brain/hooks/cli.py` `session_end_cmd` (around line 113). It currently calls `end_session(...)`, `record_event(... event_kind='session_end')`, then `_emit_noop()`.
- Phase 3a-2 already established the `try/except Exception` non-fatal pattern in `stop_cmd` — mirror it.

### Step 1: Write the failing test

Create `tests/test_hook_session_end_compliance.py`:

```python
"""SessionEnd hook records under_captured + honors strict_mode (Phase 3a-4)."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run_hook(event, payload, env_db_url):
    return subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )


def _seed_undercaptured_session(engine, cc_id: str) -> int:
    """Create an ended session with 6 turns and 0 captures."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, :cc, '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1), "cc": cc_id},
        ).scalar()
        for _ in range(6):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb)"
                ),
                {"sid": sid},
            )
    return int(sid)


def test_session_end_records_under_captured_event(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_undercaptured_session(engine, "se-uc-1")

    payload = {
        "session_id": "se-uc-1",
        "transcript_path": "/tmp/se-uc-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 0, res.stderr

    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT payload FROM session_events "
                "WHERE session_id = :sid AND event_kind = 'under_captured'"
            ),
            {"sid": sid},
        ).first()
    assert row is not None
    assert row.payload["turn_count"] == 6
    assert row.payload["capture_count"] == 0


def test_session_end_no_under_captured_event_for_compliant_session(pg_url: str) -> None:
    """A session with 3 captures should NOT record under_captured."""
    engine = get_engine(pg_url)
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, 'se-ok-1', '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1)},
        ).scalar()
        for _ in range(6):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb)"
                ),
                {"sid": sid},
            )

    # Seed 3 capture-worthy sources within window.
    from brain.schemas import SourceInput
    from brain.write import write
    write(engine, SourceInput(kind="decision", content="d1"))
    write(engine, SourceInput(kind="gotcha", content="g1"))
    write(engine, SourceInput(kind="note", content="n1"))

    payload = {
        "session_id": "se-ok-1",
        "transcript_path": "/tmp/se-ok-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 0

    with session_scope(engine) as s:
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM session_events "
                "WHERE session_id = :sid AND event_kind = 'under_captured'"
            ),
            {"sid": int(sid)},
        ).scalar()
    assert n == 0


def test_session_end_strict_mode_exits_non_zero(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO brain_config(key, value, updated_at) "
                "VALUES ('strict_mode', 'true', NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value='true'"
            )
        )
    sid = _seed_undercaptured_session(engine, "se-strict-1")

    payload = {
        "session_id": "se-strict-1",
        "transcript_path": "/tmp/se-strict-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    assert res.returncode == 2, f"expected exit 2, got {res.returncode} stderr={res.stderr}"


def test_session_end_silent_on_missing_session_row(pg_url: str) -> None:
    """If no sessions row exists for the cc_session_id, hook must not crash."""
    payload = {
        "session_id": "se-absent-1",
        "transcript_path": "/tmp/se-absent-1.jsonl",
        "cwd": "/tmp/x",
        "hook_event_name": "SessionEnd",
        "reason": "clear",
    }
    res = _run_hook("session-end", payload, pg_url)
    # `start_session` (called inside session_end_cmd via end_session path) auto-creates
    # missing rows. The downstream compliance check on a freshly-created row sees
    # turn_count=0, so under_captured is false. Hook exits cleanly.
    assert res.returncode == 0, res.stderr
```

### Step 2: Run tests

Run: `.venv/bin/pytest tests/test_hook_session_end_compliance.py -v`
Expected: FAIL — the SessionEnd hook doesn't yet emit `under_captured` events.

### Step 3: Modify `session_end_cmd`

In `src/brain/hooks/cli.py`, find `session_end_cmd` (around line 100). Add imports at top alongside other `brain.*` imports:

```python
from brain.compliance import (
    is_strict_mode,
    is_under_captured,
    session_capture_stats,
)
```

Then extend the handler. Final shape:

```python
@hook.command("session-end")
@click.pass_context
def session_end_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = SessionEndInput.model_validate(raw)
    engine = ctx.obj["engine"]
    end_session(engine, cc_session_id=inp.session_id, reason=inp.reason)
    with session_scope(engine) as s:
        sid = s.execute(
            text("SELECT id FROM sessions WHERE cc_session_id = :cc"), {"cc": inp.session_id}
        ).scalar()
    if sid is not None:
        record_event(engine, session_id=sid, event_kind="session_end", payload={"reason": inp.reason})

        # Phase 3a-4: compliance check.
        try:
            stats = session_capture_stats(engine, session_id=int(sid))
            if is_under_captured(stats):
                record_event(
                    engine, session_id=int(sid), event_kind="under_captured",
                    payload={
                        "turn_count": stats.turn_count,
                        "capture_count": stats.capture_count,
                        "decision_count": stats.decision_count,
                        "gotcha_count": stats.gotcha_count,
                        "subtask_summary_count": stats.subtask_summary_count,
                    },
                )
                if is_strict_mode(engine):
                    _emit_noop()
                    ctx.exit(2)
        except SystemExit:
            raise  # ctx.exit raises this — let it propagate
        except Exception as exc:  # noqa: BLE001 — hook must be non-fatal
            record_event(
                engine, session_id=int(sid), event_kind="hook_error",
                payload={"hook": "session_end", "error": str(exc)[:500]},
            )

    _emit_noop()
```

Note the `except SystemExit: raise` line — `ctx.exit(2)` raises `SystemExit`, which we must NOT swallow with the bare `except Exception` non-fatal guard. (`Exception` doesn't catch `SystemExit` in Python — it inherits from `BaseException` — but the explicit re-raise makes the intent unambiguous and protects against future Python changes.)

### Step 4: Run tests

Run: `.venv/bin/pytest tests/test_hook_session_end_compliance.py -v`
Expected: PASS — 4/4.

Run: `.venv/bin/pytest tests/test_hook_session_start.py tests/test_end_to_end_phase3a_1.py tests/test_hook_stop_failure_capture.py tests/test_hook_session_end_compliance.py -v`
Expected: All green — no Phase 3a-1/3a-2 regressions.

### Step 5: Commit

```bash
git add src/brain/hooks/cli.py tests/test_hook_session_end_compliance.py
git commit -m "feat(p3a-4): SessionEnd computes capture stats + records under_captured + honors strict_mode"
```

---

## Task 4: PreCompact thin-session flag

**Files:**
- Modify: `src/brain/hooks/cli.py` (`pre_compact_cmd`)
- Create: `tests/test_hook_pre_compact_thin.py`

### Step 1: Write the failing test

Create `tests/test_hook_pre_compact_thin.py`:

```python
"""PreCompact emits thin_session event when bundle has no substantive content."""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


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
    from brain.schemas import SourceInput
    from brain.write import write
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
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/pytest tests/test_hook_pre_compact_thin.py -v`
Expected: FAIL — `thin_session` event is not yet emitted.

### Step 3: Modify `pre_compact_cmd`

In `src/brain/hooks/cli.py`, find `pre_compact_cmd`. After the `sel = gather_bundle_selection(...)` line and BEFORE the render call, add:

```python
from brain.compliance import is_thin_bundle  # add to module imports

# ... inside pre_compact_cmd, after sel = gather_bundle_selection(...) ...
if is_thin_bundle(sel):
    record_event(
        engine, session_id=sid, event_kind="thin_session",
        payload={"cwd": inp.cwd, "trigger": "pre_compact"},
    )
```

The event is recorded regardless of whether the bundle is persisted (the existing render + INSERT path proceeds unchanged for both thin and substantive bundles).

### Step 4: Run tests

Run: `.venv/bin/pytest tests/test_hook_pre_compact_thin.py -v`
Expected: PASS — 2/2.

Run: `.venv/bin/pytest tests/test_end_to_end_phase3a_1.py tests/test_hook_pre_compact_thin.py -v`
Expected: All green.

### Step 5: Commit

```bash
git add src/brain/hooks/cli.py tests/test_hook_pre_compact_thin.py
git commit -m "feat(p3a-4): PreCompact records thin_session event when bundle has no substance"
```

---

## Task 5: `brain compliance` CLI sub-group

**Files:**
- Modify: `src/brain/cli.py` (add sub-group after `failure` group)
- Create: `tests/test_brain_compliance_cli.py`

### Step 1: Write the failing test

Create `tests/test_brain_compliance_cli.py`:

```python
"""brain compliance check/list/list-thin CLI."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(args, pg_url):
    return subprocess.run(
        ["brain", *args],
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": pg_url},
    )


def _seed_undercaptured(engine) -> int:
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, ended_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, :en, 'cli-uc-1', '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1), "en": now - timedelta(minutes=5)},
        ).scalar()
        for _ in range(6):
            s.execute(
                text(
                    "INSERT INTO session_events(session_id, event_kind, payload) "
                    "VALUES (:sid, 'user_prompt_submit', '{}'::jsonb)"
                ),
                {"sid": sid},
            )
    return int(sid)


def test_compliance_check_prints_stats(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_undercaptured(engine)
    res = _run(["compliance", "check", "--session-id", str(sid)], pg_url)
    assert res.returncode == 0, res.stderr
    assert "turn_count=6" in res.stdout
    assert "capture_count=0" in res.stdout
    assert "under_captured=True" in res.stdout


def test_compliance_list_returns_recent_undercaptured(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_undercaptured(engine)
    res = _run(["compliance", "list"], pg_url)
    assert res.returncode == 0, res.stderr
    assert str(sid) in res.stdout


def test_compliance_list_thin_shows_thin_sessions(pg_url: str) -> None:
    engine = get_engine(pg_url)
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(agent, started_at, cc_session_id, cwd) "
                "VALUES ('claude-code', :st, 'cli-thin-1', '/tmp/x') RETURNING id"
            ),
            {"st": now - timedelta(hours=1)},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO session_events(session_id, event_kind, payload) "
                "VALUES (:sid, 'thin_session', '{\"trigger\": \"pre_compact\"}'::jsonb)"
            ),
            {"sid": sid},
        )
    res = _run(["compliance", "list-thin"], pg_url)
    assert res.returncode == 0
    assert str(sid) in res.stdout
```

### Step 2: Run tests to verify they fail

Run: `.venv/bin/pytest tests/test_brain_compliance_cli.py -v`
Expected: FAIL — `brain compliance` doesn't exist.

### Step 3: Add the sub-group

In `src/brain/cli.py`, after the `failure` sub-group, add:

```python
from brain import compliance as _compliance


@main.group()
def compliance() -> None:
    """Compliance audits (under-captured sessions + thin bundles)."""


@compliance.command("check")
@click.option("--session-id", type=int, required=True)
@click.pass_context
def compliance_check(ctx: click.Context, session_id: int) -> None:
    """Print capture stats + verdict for one session."""
    stats = _compliance.session_capture_stats(ctx.obj["engine"], session_id=session_id)
    verdict = _compliance.is_under_captured(stats)
    click.echo(
        f"session_id={stats.session_id} "
        f"turn_count={stats.turn_count} "
        f"capture_count={stats.capture_count} "
        f"decision_count={stats.decision_count} "
        f"gotcha_count={stats.gotcha_count} "
        f"failure_count={stats.failure_count} "
        f"under_captured={verdict}"
    )


@compliance.command("list")
@click.option("--limit", type=int, default=20)
@click.pass_context
def compliance_list(ctx: click.Context, limit: int) -> None:
    """List recent under-captured sessions (most recent first)."""
    rows = _compliance.under_captured_sessions(ctx.obj["engine"], limit=limit)
    if not rows:
        click.echo("(no under-captured sessions)")
        return
    for r in rows:
        click.echo(
            f"[{r.session_id}] cc={r.cc_session_id or '-'} "
            f"project={r.project_id or '-'} "
            f"turns={r.turn_count} captures={r.capture_count}"
        )


@compliance.command("list-thin")
@click.option("--limit", type=int, default=20)
@click.pass_context
def compliance_list_thin(ctx: click.Context, limit: int) -> None:
    """List sessions with at least one thin_session event."""
    from sqlalchemy import text as _text
    from brain.db import session_scope as _scope

    with _scope(ctx.obj["engine"]) as s:
        rows = s.execute(
            _text(
                "SELECT DISTINCT ON (se.session_id) "
                "  se.session_id, se.occurred_at, se.payload, sess.cc_session_id, sess.project_id "
                "FROM session_events se JOIN sessions sess ON sess.id = se.session_id "
                "WHERE se.event_kind = 'thin_session' "
                "ORDER BY se.session_id, se.occurred_at DESC "
                "LIMIT :n"
            ),
            {"n": limit},
        ).all()
    if not rows:
        click.echo("(no thin sessions)")
        return
    for r in rows:
        click.echo(
            f"[{r.session_id}] cc={r.cc_session_id or '-'} "
            f"project={r.project_id or '-'} at={r.occurred_at:%Y-%m-%d %H:%M}"
        )
```

### Step 4: Run tests

Run: `.venv/bin/pytest tests/test_brain_compliance_cli.py -v`
Expected: PASS — 3/3.

### Step 5: Commit

```bash
git add src/brain/cli.py tests/test_brain_compliance_cli.py
git commit -m "feat(p3a-4): brain compliance CLI (check/list/list-thin)"
```

---

## Task 6: Extend `brain status` with compliance counters

**Files:**
- Modify: `src/brain/cli.py` `status` command (around line 685)

### Step 1: Read current `status`

Look at lines 683-727. The function prints three tables (active projects, recent captures, recent failures) then echoes a misleading "tasks tracking lands Phase 3a" trailer. Replace the trailer with a compliance summary.

### Step 2: Add compliance counters to the status output

Replace the existing `click.echo("tasks tracking lands Phase 3a")` line with:

```python
with session_scope(engine) as s:
    uc_count = s.execute(
        text(
            "SELECT COUNT(DISTINCT session_id) FROM session_events "
            "WHERE event_kind = 'under_captured' "
            "  AND occurred_at > NOW() - INTERVAL '30 days'"
        )
    ).scalar()
    thin_count = s.execute(
        text(
            "SELECT COUNT(DISTINCT session_id) FROM session_events "
            "WHERE event_kind = 'thin_session' "
            "  AND occurred_at > NOW() - INTERVAL '30 days'"
        )
    ).scalar()
console.print(
    f"[yellow]Compliance (last 30d): under-captured sessions = {uc_count or 0}, "
    f"thin sessions = {thin_count or 0}[/]"
)
```

(`text` and `session_scope` are already imported inside the `status` function — confirm in the current file.)

### Step 3: Smoke-test manually

```bash
brain status
```

Expected: prints the three existing tables, then the compliance summary line. Both counts will be 0 on a clean DB — that's fine.

### Step 4: Commit

```bash
git add src/brain/cli.py
git commit -m "feat(p3a-4): brain status surfaces under-captured + thin session counts (last 30d)"
```

(No new test for this — the underlying queries are exercised in Task 5; the status command is a thin wrapper.)

---

## Task 7: `brain-compliance` skill

**Files:**
- Create: `skills/brain-compliance/SKILL.md`
- Create: `skills/brain-compliance/scripts/compliance.sh`

### Step 1: Write the skill manifest

`skills/brain-compliance/SKILL.md`:

```markdown
---
name: brain-compliance
description: Use to inspect whether sessions are capturing enough, or to audit recent under-captured / thin sessions. Compliance is observability — the brain can't compel capture, but it can make non-capture visible.
---

# brain-compliance

## When to use

- Reviewing why the brain doesn't seem to "remember" — check whether prior sessions were actually capturing.
- Onboarding a new agent or project — confirm capture cadence is healthy.
- Debugging a "thin" resume bundle — find sessions where the bundle generator had nothing substantive to save.

## How

```bash
# Check one session's capture stats by id.
bash skills/brain-compliance/scripts/compliance.sh check --session-id <N>

# Recent under-captured sessions (≥5 user turns + <3 substantive captures).
bash skills/brain-compliance/scripts/compliance.sh list [--limit N]

# Recent sessions that produced thin (no-substantive-content) resume bundles.
bash skills/brain-compliance/scripts/compliance.sh list-thin [--limit N]
```

## Strict mode (opt-in)

```sql
INSERT INTO brain_config(key, value, updated_at)
VALUES ('strict_mode', 'true', NOW())
ON CONFLICT (key) DO UPDATE SET value = 'true';
```

With strict mode on, the SessionEnd hook exits non-zero (code 2) when the session is under-captured. The next session's SessionStart hook surfaces this as a visible system reminder. Set `value = 'false'` to turn it back off.

## Output budget

≤200 tokens per call. Reference sessions by id; do not paste full counts in your prose.
```

### Step 2: Write the dispatcher

`skills/brain-compliance/scripts/compliance.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec brain compliance "$@"
```

### Step 3: chmod + smoke-test

```bash
chmod +x skills/brain-compliance/scripts/compliance.sh
bash skills/brain-compliance/scripts/compliance.sh list
```

Expected: `(no under-captured sessions)` or a brief list.

### Step 4: Commit

```bash
git add skills/brain-compliance/
git commit -m "feat(p3a-4): brain-compliance skill"
```

---

## Task 8: Plugin manifests bump to 0.7.0

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `.cursor-plugin/plugin.json`
- Modify: `.codex-plugin/plugin.json`

### Step 1: Bump version + update descriptions

In each manifest:
- Change `"version": "0.6.0"` → `"0.7.0"`.
- Update the description string to reflect Phase 3a-4 additions ("compliance subsystem: under-captured session detection, thin-session flagging, opt-in strict mode").
- Bump skill count: brain-* skills are now 17 (added `brain-compliance`); total stays "21 + 1 = 22" or "17 + 5 = 22".

For `.claude-plugin/marketplace.json` the plugin description line should become roughly:

```
Phase 3a-4: compliance subsystem — under-captured + thin-session detection, opt-in strict_mode. 17 brain-* skills + 5 obsidian-* skills (22 total).
```

### Step 2: Validate JSON

```bash
python -c "import json; [json.load(open(p)) for p in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json','.cursor-plugin/plugin.json','.codex-plugin/plugin.json']]" && echo OK
```

Expected: `OK`.

### Step 3: Commit

```bash
git add .claude-plugin/ .cursor-plugin/ .codex-plugin/
git commit -m "chore(p3a-4): plugin manifests 0.7.0 — register brain-compliance skill"
```

---

## Task 9: Docs — phase3a_4.md + README + operations.md

**Files:**
- Create: `docs/phase3a_4.md`
- Modify: `README.md`
- Modify: `docs/operations.md`

### Step 1: Write `docs/phase3a_4.md`

Sections:
- **Overview** — what compliance means in this codebase (observability + nudges, not a hard block).
- **What changed** — new compliance module, fixed health audit query, SessionEnd / PreCompact extensions, new CLI + skill.
- **The compliance loop** — turn counter → SessionEnd check → under_captured event → strict_mode gate (optional) → next session's SessionStart sees a system reminder via the bundle.
- **Thresholds and how to tune them** — turn ≥5, captures <3, both adjustable via the CLI `--turn-threshold` / `--capture-threshold` if exposed (in this plan they are hardcoded; document them as constants).
- **Strict mode** — opt-in via `brain_config('strict_mode', 'true')`; exit code 2 from SessionEnd; off by default because exploratory sessions would otherwise be punished.
- **Known limitations** — turn count comes from `session_events.user_prompt_submit` only (no assistant-turn signal); the thin-session flag is event-only (no `sessions.summary_id` write — that's a Phase 4 promotion); no auto-remediation.
- **Skills** — one-row table for `brain-compliance`.

Mirror the structure of `docs/phase3a_2.md` for consistency.

### Step 2: Add a Phase 3a-4 section to `README.md`

Insert after the existing Phase 3a-2 section. Brief — 2 short paragraphs, the skill row, and a link to the ops doc + plan.

### Step 3: Extend `docs/operations.md`

Add a "Compliance triage" subsection covering:
- How to audit recent under-captured sessions: `brain compliance list`.
- How to inspect one session in detail: `brain compliance check --session-id N`.
- How to enable / disable strict mode (SQL snippet from the skill doc).
- What thin sessions mean and how to find them.

### Step 4: Commit

```bash
git add docs/phase3a_4.md README.md docs/operations.md
git commit -m "docs(p3a-4): operations doc + README + phase3a_4 ops note"
```

---

## Task 10: End-to-end verification + merge

- [ ] **Step 1: Full test suite**

Run: `.venv/bin/pytest -q`
Expected: All passing (216 from prior phases + the new tests from 3a-4 — roughly 240 total).

- [ ] **Step 2: Manual hook smoke-test (optional but recommended)**

Open a fresh Claude Code session in this repo, run a few non-capturing turns (≥5 prompts), then `/exit`. After exit:

```bash
brain compliance list --limit 5
```

Expected: the session you just exited appears with `turns≥5 captures=0`.

Then turn on strict mode:

```sql
INSERT INTO brain_config(key, value, updated_at)
VALUES ('strict_mode', 'true', NOW())
ON CONFLICT (key) DO UPDATE SET value='true';
```

Repeat the under-capturing session + exit cycle. The SessionEnd hook should now exit non-zero, and the next SessionStart bundle should carry the recent `under_captured` event in its `recent_events` section (verify via the bundle render).

Turn strict mode back off:

```sql
UPDATE brain_config SET value='false' WHERE key='strict_mode';
```

- [ ] **Step 3: Merge + tag**

```bash
git checkout main
git merge --no-ff phase-3a-4-impl -m "Merge phase-3a-4-impl: compliance subsystem (v0.7.0)"
git tag v0.7.0 -m "Phase 3a-4: compliance subsystem"
git branch -d phase-3a-4-impl
```

---

## Self-review checklist (post-draft)

1. **Spec coverage** — three teeth from §Compliance:
   - SessionEnd capture-completeness check → Task 3 ✓
   - Bundle-generator thin-session signal → Task 4 ✓
   - Optional strict mode (`brain_config.strict_mode`) → Task 3 + Task 7 (skill docs the SQL) ✓
   - `brain health` surfaces under-captured → Task 2 ✓
   - `brain status` warning for thin sessions → Task 6 ✓
2. **Placeholder scan** — no "TBD" / "add appropriate error handling" / "fill in details" instances. Each task carries complete code blocks. Docs in Task 9 specify sections concretely rather than dictating prose verbatim — acceptable because doc-writing is structurally adaptive to the surrounding repo, and the section list is exhaustive.
3. **Type consistency** —
   - `CaptureStats` defined in Task 1, consumed unchanged in Tasks 3, 5.
   - `is_under_captured(stats, *, turn_threshold=5, capture_threshold=3)` signature consistent across Tasks 1, 3, 5.
   - `under_captured_sessions(engine, *, ...)` signature consistent across Tasks 1, 2, 5.
   - `is_thin_bundle(BundleSelection)` signature consistent across Tasks 1, 4.
   - `is_strict_mode(engine)` consistent across Tasks 1, 3.

---

## Risk notes (for reviewer + executor)

- **False positives on exploratory sessions.** The turn-threshold of 5 should filter most one-shot work, but a session that asks 6 quick questions and gets answers (no captures expected) will be flagged. Mitigation: strict mode is opt-in. Document this in the phase doc.
- **`sessions.ended_at` may not get set if Claude Code dies without firing SessionEnd.** Such sessions show `ended_at IS NULL` and are excluded from `under_captured_sessions`. That's the right behavior — we don't audit incomplete sessions.
- **The `HAVING` clause in `under_captured_sessions` references columns from the CTE.** Postgres 16+ accepts this in the outer SELECT's WHERE. If a future engine version rejects it, the CTE pattern in the implementation is already correct (WHERE filters happen on materialized CTE columns).
- **Renaming `UndercapturedSession.event_count` semantics in Task 2.** The field name is preserved for back-compat with the `brain health` render code, but its meaning shifts from "events table row count" to "substantive captures count". A future task could rename to `capture_count` for clarity; out of scope here.
- **Thin-session detection runs on PreCompact only.** SessionEnd doesn't generate a bundle in 3a-1, so the thin signal can't fire there. If a future plan adds bundle generation to SessionEnd, mirror the thin-check there.
