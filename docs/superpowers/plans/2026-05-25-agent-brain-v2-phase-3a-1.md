# Agent Brain v2 — Phase 3a-1 Implementation Plan (Compaction-Survival Core)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Claude Code hook integration so the brain captures session lifecycle events (start / end / user-prompt / stop / pre-compact) automatically, generates a compaction-survival resume bundle on PreCompact, and re-injects it into the post-compact (or resumed) session via SessionStart's `additionalContext` stdout mechanism. Adds 3 user-facing skills (`brain-session-log`, `brain-session-resume`, `brain-handoff`) and one new CLI sub-group (`brain hook ...`) that the plugin's shell dispatcher delegates to.

**Architecture:** Plugin-shipped hooks under `<plugin-root>/hooks/` with a `hooks.json` config and a `run-hook.sh` dispatcher. Each Claude Code hook event (SessionStart, SessionEnd, UserPromptSubmit, Stop, PreCompact) calls `brain hook <event>`, which reads the hook stdin JSON, writes session/event rows to Postgres, and (for SessionStart + PreCompact) emits stdout that Claude Code consumes — `additionalContext` JSON for SessionStart, plain text for PreCompact (becomes "custom compact instructions"). Bundle generation in PreCompact queries recent captures, decisions, gotchas, failures, and open subtasks, renders both a JSONB manifest and a markdown body, and INSERTs into `session_resume_bundles`. SessionStart on `source=compact|resume` queries the latest unconsumed bundle for the current `cwd`, emits it as `additionalContext`, marks it consumed. No new Python deps — pure stdlib + existing SQLAlchemy.

**Tech Stack:** Same as Phase 2.5. Python 3.12, Postgres + pgvector, SQLAlchemy 2.0, Click, alembic, BGE-M3, mxbai-rerank. Adds no new runtime deps.

**Spec reference:** `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md` § "Phase 3a — Capture fidelity + compaction-survival (the cognition-preservation core)".

---

## Empirical findings (locked in via probe)

Recorded for reviewers:

1. **SessionStart stdin payload** carries `{session_id, transcript_path, cwd, hook_event_name, source, model}` where `source ∈ {startup, resume, compact, clear}`. `transcript_path` is the absolute path to the session's JSONL transcript — load-bearing for richer bundle generation in 3a-2/3.
2. **SessionStart stdout JSON `additionalContext`** lands verbatim in the new session's context as a system reminder. Tested empirically; works on `startup` and `resume`.
3. **PreCompact stdout is NOT next-session context.** Per Claude Code's own `/hooks` help: `"Exit code 0 — stdout appended as custom compact instructions"`. We use this for hints to the compactor ("preserve decisions, gotchas, recent failures") and rely on the DB-mediated bundle for actual handoff.
4. **Plugin-shipped hooks** use `"command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh <event>"` in `hooks.json`. Auto-installed when the plugin is enabled.

---

## Scope this plan does NOT cover

Deferred to follow-on plans:

- **Phase 3a-2:** Failure-memory capture flow (`brain-failure` skill + auto-flag from Stop hook + sanitization minimum: ANSI stripping + instruction-density flagging).
- **Phase 3a-3:** File watcher (Obsidian-side edits → DB with conflict detection).
- **Phase 3a-4:** Compliance subsystem (under-captured session detection, expanded `brain-health` audit).

These build on the `session_events` table and Stop hook landing here.

---

## File structure (Phase 3a-1)

### Creations

```
hooks/
  hooks.json                              # Claude Code hook config (plugin-shipped)
  run-hook.sh                             # Shell dispatcher: ${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh <event>
src/brain/
  alembic/versions/010_session_lifecycle.py
  hooks/
    __init__.py
    contracts.py                          # Pydantic input schemas per hook event
    session.py                            # Session lifecycle helpers (start, end, find_by_cc_id)
    events.py                             # session_events writers
    bundle.py                             # Bundle generation algorithm
    render.py                             # Bundle render (manifest JSON + markdown body)
    cli.py                                # Click sub-group: brain hook <event>
skills/
  brain-session-log/SKILL.md
  brain-session-log/scripts/session-log.sh
  brain-session-resume/SKILL.md
  brain-session-resume/scripts/session-resume.sh
  brain-handoff/SKILL.md
  brain-handoff/scripts/handoff.sh
docs/phase3a_1.md
tests/test_migration_010.py
tests/test_hook_contracts.py
tests/test_hook_session_start.py
tests/test_hook_session_end.py
tests/test_hook_user_prompt_submit.py
tests/test_hook_stop.py
tests/test_hook_pre_compact.py
tests/test_bundle_generation.py
tests/test_bundle_render.py
tests/test_end_to_end_phase3a_1.py
```

### Modifications

```
src/brain/cli.py                          # Wire brain hook + brain session-log/resume/handoff sub-groups
src/brain/models.py                       # SessionEvent ORM, Session ORM additions
.claude-plugin/plugin.json                # Version 0.5.0
README.md                                 # Add Phase 3a-1 section
```

---

## Schema additions (migration 010)

Existing relevant tables (from migrations 002 + 007):

- `sessions(id, project_id, agent, started_at, ended_at, summary_id)` — no cwd, no cc_session_id
- `session_resume_bundles(id, project_id, session_id, trigger, generated_at, superseded_at, token_budget, manifest JSONB, rendered TEXT)` — trigger CHECK already allows `pre_compact|session_end|manual`; missing `consumed_at` and `cwd` for SessionStart lookup

Migration 010 adds:

1. `sessions.cc_session_id TEXT` — Claude Code's session UUID (e.g. `0668cf02-...`). Indexed for hook lookups.
2. `sessions.cwd TEXT` — working directory captured at SessionStart. Indexed.
3. `session_resume_bundles.consumed_at TIMESTAMPTZ NULL` — set by SessionStart when bundle is injected.
4. `session_resume_bundles.cwd TEXT NOT NULL DEFAULT ''` — for SessionStart filter without joining sessions. Backfilled from `sessions.cwd` for existing rows (none in dev; safe).
5. New table `session_events(id, session_id, event_kind, payload JSONB, occurred_at)` for per-event capture from hooks. Indexed on `(session_id, occurred_at)`.

---

## Hook dispatch wiring

Plugin ships `<plugin-root>/hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh session-start",
            "timeout": 15
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh session-end",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh user-prompt-submit",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh stop",
            "timeout": 5
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh pre-compact",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

`hooks/run-hook.sh`:

```bash
#!/usr/bin/env bash
# Plugin hook dispatcher. Reads stdin (Claude Code hook event JSON) and pipes
# it to `brain hook <event>`. brain CLI must be on PATH (symlink from venv to
# ~/.local/bin/brain handles this).
#
# Silent on errors — Claude Code shows stderr to the user only, but we want
# hook failures to be non-fatal to the session. Errors are logged into the
# brain itself (event_kind='hook_error') for later inspection.

set -uo pipefail

EVENT="${1:-unknown}"

if ! command -v brain >/dev/null 2>&1; then
  printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":""}}' "$EVENT"
  exit 0
fi

exec brain hook "$EVENT"
```

Hooks are non-fatal — if `brain` isn't on PATH (e.g. brain not yet installed), they emit an empty JSON shell and exit 0 so the user's session is unaffected.

---

## Bundle data model

`session_resume_bundles.manifest` JSONB shape:

```json
{
  "schema_version": 1,
  "session_id": 42,
  "cc_session_id": "0668cf02-...",
  "cwd": "/home/keertan/codes/brain",
  "trigger": "pre_compact",
  "generated_at": "2026-05-25T13:00:00Z",
  "token_budget": 4000,
  "selection": {
    "decisions": [{"source_id": 101, "kind": "decision", "head": "..."}],
    "gotchas": [{"source_id": 102, "kind": "gotcha", "head": "..."}],
    "patterns": [{"source_id": 103, "kind": "pattern", "head": "..."}],
    "failures": [{"source_id": 104, "target_problem": "...", "approach": "...", "retry_count": 2}],
    "subtasks_open": [{"subtask_id": 7, "title": "...", "goal": "..."}],
    "recent_events": [{"event_kind": "user-prompt-submit", "occurred_at": "...", "head": "..."}]
  }
}
```

`rendered` TEXT is the markdown rendering injected via `additionalContext`:

```markdown
# Agent Brain resume bundle

Project `/home/keertan/codes/brain`, session 42, triggered by `pre_compact` at 2026-05-25T13:00:00Z.

## Decisions
- [id=101] postgres chosen over a dedicated vector DB for ops simplicity.

## Recent gotchas
- [id=102] `::jsonb` parser collision with SQLAlchemy bind params; use `CAST(:x AS jsonb)`.

## Patterns
(none)

## Unresolved failures
- target: get plugin install working; approach: bare `./` source; attempts: 3.

## Open subtasks
- (7) Phase 3a-1 implementation

## Recent activity (last 10 events)
- 2026-05-25T12:58Z user-prompt-submit: ...
```

The renderer enforces a token budget (default 4000 tokens) by truncating sections proportionally.

---

## Task 1: Migration 010 — session_lifecycle

**Files:**
- Create: `src/brain/alembic/versions/010_session_lifecycle.py`
- Create: `tests/test_migration_010.py`

- [ ] **Step 1: Write the failing test**

```python
"""Migration 010 schema additions: sessions.cc_session_id, sessions.cwd,
session_resume_bundles.consumed_at + cwd, new session_events table."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine


def test_sessions_has_cc_session_id(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='sessions'"
            )
        ).fetchall()
    names = {r[0] for r in cols}
    assert "cc_session_id" in names
    assert "cwd" in names


def test_session_resume_bundles_has_consumed_at_and_cwd(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='session_resume_bundles'"
            )
        ).fetchall()
    names = {r[0] for r in cols}
    assert "consumed_at" in names
    assert "cwd" in names


def test_session_events_table_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='session_events'"
            )
        ).fetchall()
    names = {r[0] for r in cols}
    for required in ("id", "session_id", "event_kind", "payload", "occurred_at"):
        assert required in names, f"missing column {required}"


def test_sessions_cc_id_index(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename='sessions'")
        ).fetchall()
    names = {r[0] for r in rows}
    assert "sessions_cc_session_id_idx" in names


def test_session_resume_bundles_cwd_consumed_index(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename='session_resume_bundles'")
        ).fetchall()
    names = {r[0] for r in rows}
    assert "bundles_cwd_unconsumed_idx" in names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_migration_010.py -v
```
Expected: all 5 fail (columns/table/indexes don't exist yet).

- [ ] **Step 3: Write migration 010**

`src/brain/alembic/versions/010_session_lifecycle.py`:

```python
"""Session lifecycle: cc_session_id + cwd on sessions, consumed_at + cwd on
session_resume_bundles, new session_events table.

Revision ID: 010_session_lifecycle
Revises: 009_drop_llm_coupling
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010_session_lifecycle"
down_revision = "009_drop_llm_coupling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("cc_session_id", sa.Text, nullable=True))
    op.add_column("sessions", sa.Column("cwd", sa.Text, nullable=True))
    op.create_index("sessions_cc_session_id_idx", "sessions", ["cc_session_id"])
    op.create_index("sessions_cwd_idx", "sessions", ["cwd"])

    op.add_column(
        "session_resume_bundles",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_resume_bundles",
        sa.Column("cwd", sa.Text, nullable=False, server_default=""),
    )
    op.execute(
        """
        CREATE INDEX bundles_cwd_unconsumed_idx
        ON session_resume_bundles(cwd, generated_at DESC)
        WHERE consumed_at IS NULL AND superseded_at IS NULL
        """
    )

    op.create_table(
        "session_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_kind", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "event_kind IN ('session_start','session_end','user_prompt_submit','stop','pre_compact','hook_error')",
            name="session_events_kind_check",
        ),
    )
    op.create_index(
        "session_events_session_idx",
        "session_events",
        ["session_id", sa.text("occurred_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("session_events_session_idx", table_name="session_events")
    op.drop_table("session_events")
    op.execute("DROP INDEX IF EXISTS bundles_cwd_unconsumed_idx")
    op.drop_column("session_resume_bundles", "cwd")
    op.drop_column("session_resume_bundles", "consumed_at")
    op.drop_index("sessions_cwd_idx", table_name="sessions")
    op.drop_index("sessions_cc_session_id_idx", table_name="sessions")
    op.drop_column("sessions", "cwd")
    op.drop_column("sessions", "cc_session_id")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_migration_010.py -v
```
Expected: 5 pass. Then full suite green at 132 (131 + 1 from new migration tests... actually 5 new — 131 + 5 = 136).

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/010_session_lifecycle.py tests/test_migration_010.py
git commit -m "feat(p3a-1): migration 010 — session lifecycle columns + session_events table"
```

---

## Task 2: Hook stdin contracts

**Files:**
- Create: `src/brain/hooks/__init__.py`
- Create: `src/brain/hooks/contracts.py`
- Create: `tests/test_hook_contracts.py`

- [ ] **Step 1: Write the failing test**

```python
"""Pydantic schemas for hook stdin payloads. Validate Claude Code 2.1.150 shapes."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from brain.hooks.contracts import (
    PreCompactInput,
    SessionEndInput,
    SessionStartInput,
    StopInput,
    UserPromptSubmitInput,
)


def test_session_start_input_parses_real_payload() -> None:
    raw = json.dumps(
        {
            "session_id": "0668cf02-bc9d-4f33-a8ed-a9c16df53222",
            "transcript_path": "/home/keertan/.claude/projects/-home-keertan-codes-brain/0668cf02.jsonl",
            "cwd": "/home/keertan/codes/brain",
            "hook_event_name": "SessionStart",
            "source": "resume",
            "model": "claude-opus-4-7[1m]",
        }
    )
    parsed = SessionStartInput.model_validate_json(raw)
    assert parsed.session_id == "0668cf02-bc9d-4f33-a8ed-a9c16df53222"
    assert parsed.source == "resume"
    assert parsed.cwd == "/home/keertan/codes/brain"


def test_session_start_input_accepts_known_sources() -> None:
    for src in ("startup", "resume", "compact", "clear"):
        SessionStartInput.model_validate({
            "session_id": "x",
            "transcript_path": "/tmp/x.jsonl",
            "cwd": "/tmp",
            "hook_event_name": "SessionStart",
            "source": src,
        })


def test_session_start_input_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        SessionStartInput.model_validate({
            "session_id": "x",
            "transcript_path": "/tmp/x.jsonl",
            "cwd": "/tmp",
            "hook_event_name": "SessionStart",
            "source": "BOGUS",
        })


def test_user_prompt_submit_parses() -> None:
    payload = {
        "session_id": "abc",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "UserPromptSubmit",
        "prompt": "hello there",
    }
    parsed = UserPromptSubmitInput.model_validate(payload)
    assert parsed.prompt == "hello there"


def test_pre_compact_parses() -> None:
    payload = {
        "session_id": "abc",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreCompact",
        "trigger": "manual",
        "custom_instructions": "preserve decisions",
    }
    parsed = PreCompactInput.model_validate(payload)
    assert parsed.trigger == "manual"


def test_stop_and_session_end_parse() -> None:
    base = {
        "session_id": "abc",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
    }
    StopInput.model_validate({**base, "hook_event_name": "Stop", "stop_hook_active": False})
    SessionEndInput.model_validate({**base, "hook_event_name": "SessionEnd", "reason": "clear"})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_hook_contracts.py -v
```
Expected: ImportError on the schema classes.

- [ ] **Step 3: Write the contracts module**

`src/brain/hooks/__init__.py`:

```python
"""Claude Code hook integration for Phase 3a-1.

Plugin-shipped hooks invoke `brain hook <event>`, which dispatches into the
modules here. Stdin = JSON event payload. Stdout (for SessionStart + PreCompact)
flows back into Claude Code via additionalContext / compact instructions.
"""
```

`src/brain/hooks/contracts.py`:

```python
"""Pydantic schemas for Claude Code hook stdin payloads.

Shapes derived empirically from probe in Phase 3a-1 planning. Fields that
Claude Code may add later are tolerated via `model_config = {extra: 'allow'}`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SessionSource = Literal["startup", "resume", "compact", "clear"]
PreCompactTrigger = Literal["manual", "auto"]


class _HookBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str
    transcript_path: str
    cwd: str
    hook_event_name: str


class SessionStartInput(_HookBase):
    source: SessionSource
    model: str | None = None


class SessionEndInput(_HookBase):
    reason: str | None = None


class UserPromptSubmitInput(_HookBase):
    prompt: str


class StopInput(_HookBase):
    stop_hook_active: bool = False


class PreCompactInput(_HookBase):
    trigger: PreCompactTrigger | None = None
    custom_instructions: str | None = None


class SessionStartOutput(BaseModel):
    """Schema for the stdout JSON SessionStart emits."""

    hookSpecificOutput: dict
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_hook_contracts.py -v
```
Expected: 6 pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/hooks/__init__.py src/brain/hooks/contracts.py tests/test_hook_contracts.py
git commit -m "feat(p3a-1): Pydantic schemas for Claude Code hook stdin payloads"
```

---

## Task 3: Session lifecycle helpers

**Files:**
- Create: `src/brain/hooks/session.py`
- Create: `tests/test_session_lifecycle.py`

- [ ] **Step 1: Write the failing test**

```python
"""Session lifecycle: start_session, find_by_cc_id, end_session."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.hooks.session import end_session, find_session_by_cc_id, start_session


def test_start_session_creates_row(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(
        engine,
        cc_session_id="abc-123",
        cwd="/tmp/foo",
        agent="claude-code",
        source="startup",
    )
    assert sid > 0
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT cc_session_id, cwd, ended_at FROM sessions WHERE id = :i"),
            {"i": sid},
        ).one()
    assert row.cc_session_id == "abc-123"
    assert row.cwd == "/tmp/foo"
    assert row.ended_at is None


def test_start_session_returns_existing_when_cc_id_matches(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid_a = start_session(engine, cc_session_id="dup", cwd="/tmp", agent="cc", source="startup")
    sid_b = start_session(engine, cc_session_id="dup", cwd="/tmp", agent="cc", source="resume")
    assert sid_a == sid_b


def test_find_session_by_cc_id(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="findme", cwd="/x", agent="cc", source="startup")
    assert find_session_by_cc_id(engine, "findme") == sid
    assert find_session_by_cc_id(engine, "nope") is None


def test_end_session_sets_ended_at(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="enders", cwd="/x", agent="cc", source="startup")
    end_session(engine, cc_session_id="enders", reason="user_quit")
    with session_scope(engine) as s:
        ended = s.execute(
            text("SELECT ended_at FROM sessions WHERE id = :i"), {"i": sid}
        ).scalar()
    assert ended is not None


def test_end_session_unknown_cc_id_is_noop(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # Should not raise
    end_session(engine, cc_session_id="ghost", reason="ignored")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_session_lifecycle.py -v
```
Expected: ImportError on `brain.hooks.session`.

- [ ] **Step 3: Implement session helpers**

`src/brain/hooks/session.py`:

```python
"""Session row lifecycle: idempotent start/end keyed on Claude Code's session UUID."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, text

from brain.db import session_scope


def find_session_by_cc_id(engine: Engine, cc_session_id: str) -> int | None:
    """Return the brain `sessions.id` for a given Claude Code session UUID, or None."""
    with session_scope(engine) as s:
        return s.execute(
            text("SELECT id FROM sessions WHERE cc_session_id = :cc"),
            {"cc": cc_session_id},
        ).scalar()


def start_session(
    engine: Engine,
    *,
    cc_session_id: str,
    cwd: str,
    agent: str,
    source: str,
) -> int:
    """Idempotent — if a row with this cc_session_id exists, return it.

    Otherwise insert a new row and return its id. `source` is recorded as the
    initial session_events row in caller code (events module); session itself
    only tracks the immutable identity (cc id, cwd, agent, started_at).
    """
    existing = find_session_by_cc_id(engine, cc_session_id)
    if existing is not None:
        return existing
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sessions(cc_session_id, cwd, agent) "
                "VALUES (:cc, :cwd, :agent) RETURNING id"
            ),
            {"cc": cc_session_id, "cwd": cwd, "agent": agent},
        ).scalar()
    assert sid is not None
    return sid


def end_session(engine: Engine, *, cc_session_id: str, reason: str | None = None) -> None:
    """Mark the session as ended. No-op if the cc_session_id is unknown."""
    now = datetime.now(timezone.utc)
    with session_scope(engine) as s:
        s.execute(
            text("UPDATE sessions SET ended_at = :now WHERE cc_session_id = :cc AND ended_at IS NULL"),
            {"now": now, "cc": cc_session_id},
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_session_lifecycle.py -v
```
Expected: 5 pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/hooks/session.py tests/test_session_lifecycle.py
git commit -m "feat(p3a-1): session lifecycle helpers (start/end/find_by_cc_id)"
```

---

## Task 4: session_events writer

**Files:**
- Create: `src/brain/hooks/events.py`
- Create: `tests/test_session_events.py`

- [ ] **Step 1: Write the failing test**

```python
"""session_events writer."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.hooks.events import record_event
from brain.hooks.session import start_session


def test_record_event_inserts_row(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="ev", cwd="/x", agent="cc", source="startup")
    record_event(engine, session_id=sid, event_kind="user_prompt_submit", payload={"prompt": "hello"})
    with session_scope(engine) as s:
        rows = s.execute(
            text("SELECT event_kind, payload FROM session_events WHERE session_id = :i"),
            {"i": sid},
        ).fetchall()
    assert len(rows) == 1
    assert rows[0].event_kind == "user_prompt_submit"
    assert rows[0].payload == {"prompt": "hello"}


def test_record_event_rejects_bad_kind(pg_url: str) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="bad", cwd="/x", agent="cc", source="startup")
    with pytest.raises(IntegrityError):
        record_event(engine, session_id=sid, event_kind="bogus_kind", payload={})


def test_record_event_default_payload_is_empty_dict(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="def", cwd="/x", agent="cc", source="startup")
    record_event(engine, session_id=sid, event_kind="stop")
    with session_scope(engine) as s:
        payload = s.execute(
            text("SELECT payload FROM session_events WHERE session_id = :i"), {"i": sid}
        ).scalar()
    assert payload == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_session_events.py -v
```
Expected: ImportError on `brain.hooks.events`.

- [ ] **Step 3: Implement events writer**

`src/brain/hooks/events.py`:

```python
"""session_events table writer."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, text

from brain.db import session_scope


def record_event(
    engine: Engine,
    *,
    session_id: int,
    event_kind: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Insert a session_events row.

    Raises IntegrityError if event_kind is not in the CHECK constraint
    (session_start | session_end | user_prompt_submit | stop | pre_compact | hook_error).
    """
    body = json.dumps(payload if payload is not None else {})
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO session_events(session_id, event_kind, payload) "
                "VALUES (:sid, :kind, CAST(:p AS jsonb))"
            ),
            {"sid": session_id, "kind": event_kind, "p": body},
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_session_events.py -v
```
Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/hooks/events.py tests/test_session_events.py
git commit -m "feat(p3a-1): session_events writer with CHECK-validated event_kind"
```

---

## Task 5: Bundle generation algorithm

**Files:**
- Create: `src/brain/hooks/bundle.py`
- Create: `tests/test_bundle_generation.py`

The bundle picks recent captured content (decisions, gotchas, patterns), unresolved failures, open subtasks, and the last 10 session events. Selection is bounded by recency, not by token budget — the renderer (Task 6) enforces the budget.

- [ ] **Step 1: Write the failing test**

```python
"""Bundle selection: gather decisions/gotchas/patterns/failures/subtasks/events."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.hooks.bundle import BundleSelection, gather_bundle_selection
from brain.hooks.events import record_event
from brain.hooks.session import start_session
from brain.schemas import SourceInput
from brain.write import write


def test_bundle_selection_picks_recent_kinds(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="b1", cwd="/x", agent="cc", source="startup")

    # Get the project_id for /x — bundle gather scopes by cwd; we don't need
    # a real project row, gather_bundle_selection accepts cwd directly.
    write(engine, SourceInput(kind="decision", content="chose pgvector"))
    write(engine, SourceInput(kind="gotcha", content="::jsonb collides with bind params"))
    write(engine, SourceInput(kind="pattern", content="CAST(:x AS jsonb)"))
    write(engine, SourceInput(kind="note", content="unrelated note"))

    record_event(engine, session_id=sid, event_kind="user_prompt_submit", payload={"prompt": "p1"})
    record_event(engine, session_id=sid, event_kind="stop")

    sel = gather_bundle_selection(engine, session_id=sid, cwd="/x", limit_per_kind=10)
    assert isinstance(sel, BundleSelection)

    decision_heads = [d["head"] for d in sel.decisions]
    assert any("pgvector" in h for h in decision_heads)

    gotcha_heads = [g["head"] for g in sel.gotchas]
    assert any("jsonb" in h for h in gotcha_heads)

    pattern_heads = [p["head"] for p in sel.patterns]
    assert any("CAST" in h for h in pattern_heads)

    # Recent events: 2 of them
    assert len(sel.recent_events) >= 2
    assert any(e["event_kind"] == "stop" for e in sel.recent_events)


def test_bundle_selection_respects_limit(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="b2", cwd="/y", agent="cc", source="startup")
    for i in range(15):
        write(engine, SourceInput(kind="gotcha", content=f"gotcha number {i}"))
    sel = gather_bundle_selection(engine, session_id=sid, cwd="/y", limit_per_kind=5)
    assert len(sel.gotchas) == 5


def test_bundle_selection_empty_when_no_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = start_session(engine, cc_session_id="b3", cwd="/z", agent="cc", source="startup")
    sel = gather_bundle_selection(engine, session_id=sid, cwd="/z", limit_per_kind=10)
    assert sel.decisions == []
    assert sel.gotchas == []
    assert sel.patterns == []
    assert sel.failures == []
    assert sel.subtasks_open == []
    assert sel.recent_events == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bundle_generation.py -v
```
Expected: ImportError on `brain.hooks.bundle`.

- [ ] **Step 3: Implement bundle selection**

`src/brain/hooks/bundle.py`:

```python
"""Bundle selection: gather a snapshot of brain state for compaction-survival.

Picks:
  - Recent captured decisions / gotchas / patterns (last N each, by created_at desc).
  - Unresolved failure_memories (t_valid_to IS NULL).
  - Open subtasks (outcome IS NULL OR outcome='in_progress').
  - Last N session_events for the given session_id.

Selection is bounded only by `limit_per_kind`. Token budget enforcement happens
at render time (Task 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, text

from brain.db import session_scope


@dataclass
class BundleSelection:
    decisions: list[dict[str, Any]] = field(default_factory=list)
    gotchas: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    subtasks_open: list[dict[str, Any]] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)


def _head(content: str, max_chars: int = 200) -> str:
    s = content.strip()
    return s if len(s) <= max_chars else s[: max_chars - 1] + "…"


def _query_kind(engine: Engine, kind: str, limit: int) -> list[dict[str, Any]]:
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, kind, content FROM sources "
                "WHERE kind = :k AND t_valid_to IS NULL "
                "ORDER BY id DESC LIMIT :n"
            ),
            {"k": kind, "n": limit},
        ).fetchall()
    return [{"source_id": r.id, "kind": r.kind, "head": _head(r.content)} for r in rows]


def gather_bundle_selection(
    engine: Engine,
    *,
    session_id: int,
    cwd: str,
    limit_per_kind: int = 10,
) -> BundleSelection:
    """Snapshot recent brain state into a BundleSelection dataclass.

    `cwd` is taken for forward-compat (Phase 3a-1 doesn't scope sources by cwd,
    but later phases may filter on `project.repo_root == cwd`). Currently
    selects across all projects.
    """
    sel = BundleSelection()
    sel.decisions = _query_kind(engine, "decision", limit_per_kind)
    sel.gotchas = _query_kind(engine, "gotcha", limit_per_kind)
    sel.patterns = _query_kind(engine, "pattern", limit_per_kind)

    with session_scope(engine) as s:
        sel.failures = [
            {
                "failure_id": r.id,
                "target_problem": r.target_problem,
                "approach": r.attempted_approach,
                "retry_count": r.retry_count,
            }
            for r in s.execute(
                text(
                    "SELECT id, target_problem, attempted_approach, retry_count "
                    "FROM failure_memories WHERE t_valid_to IS NULL "
                    "ORDER BY last_attempted_at DESC NULLS LAST LIMIT :n"
                ),
                {"n": limit_per_kind},
            ).fetchall()
        ]
        sel.subtasks_open = [
            {"subtask_id": r.id, "title": r.title, "goal": r.goal}
            for r in s.execute(
                text(
                    "SELECT id, title, goal FROM subtasks "
                    "WHERE outcome IS NULL OR outcome = 'in_progress' "
                    "ORDER BY started_at DESC LIMIT :n"
                ),
                {"n": limit_per_kind},
            ).fetchall()
        ]
        sel.recent_events = [
            {"event_kind": r.event_kind, "occurred_at": r.occurred_at.isoformat(), "payload": r.payload}
            for r in s.execute(
                text(
                    "SELECT event_kind, occurred_at, payload "
                    "FROM session_events WHERE session_id = :sid "
                    "ORDER BY occurred_at DESC LIMIT :n"
                ),
                {"sid": session_id, "n": limit_per_kind},
            ).fetchall()
        ]
    return sel
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bundle_generation.py -v
```
Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/hooks/bundle.py tests/test_bundle_generation.py
git commit -m "feat(p3a-1): bundle selection algorithm (decisions/gotchas/patterns/failures/subtasks/events)"
```

---

## Task 6: Bundle render (manifest JSON + markdown body)

**Files:**
- Create: `src/brain/hooks/render.py`
- Create: `tests/test_bundle_render.py`

- [ ] **Step 1: Write the failing test**

```python
"""Bundle render: serializes BundleSelection to (manifest_json, markdown_body)
with a token budget."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brain.hooks.bundle import BundleSelection
from brain.hooks.render import RenderedBundle, render_bundle


def _selection() -> BundleSelection:
    s = BundleSelection()
    s.decisions = [{"source_id": 1, "kind": "decision", "head": "chose pgvector for ops simplicity"}]
    s.gotchas = [{"source_id": 2, "kind": "gotcha", "head": "::jsonb collides with bind params"}]
    s.patterns = [{"source_id": 3, "kind": "pattern", "head": "CAST(:x AS jsonb)"}]
    s.failures = [
        {"failure_id": 4, "target_problem": "install plugin", "approach": "bare ./", "retry_count": 3}
    ]
    s.subtasks_open = [{"subtask_id": 5, "title": "ship 3a-1", "goal": "compaction-survival"}]
    s.recent_events = [
        {"event_kind": "user_prompt_submit", "occurred_at": "2026-05-25T13:00:00+00:00", "payload": {"prompt": "p"}}
    ]
    return s


def test_render_produces_manifest_and_markdown() -> None:
    sel = _selection()
    out = render_bundle(
        sel,
        cc_session_id="abc",
        session_id=42,
        cwd="/tmp/proj",
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime(2026, 5, 25, 13, tzinfo=timezone.utc),
    )
    assert isinstance(out, RenderedBundle)
    assert out.manifest["session_id"] == 42
    assert out.manifest["cc_session_id"] == "abc"
    assert out.manifest["cwd"] == "/tmp/proj"
    assert out.manifest["trigger"] == "pre_compact"
    assert out.manifest["token_budget"] == 4000
    assert "selection" in out.manifest
    assert "Decisions" in out.markdown
    assert "pgvector" in out.markdown
    assert "## Recent activity" in out.markdown


def test_render_omits_empty_sections() -> None:
    sel = BundleSelection()
    sel.decisions = [{"source_id": 1, "kind": "decision", "head": "only decision"}]
    out = render_bundle(
        sel,
        cc_session_id="x",
        session_id=1,
        cwd="/x",
        trigger="manual",
        token_budget=4000,
        generated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )
    assert "Decisions" in out.markdown
    # Empty kinds should NOT appear as empty headers
    assert "Gotchas" not in out.markdown
    assert "Patterns" not in out.markdown


def test_render_respects_token_budget() -> None:
    sel = BundleSelection()
    # 200 entries × 100-char heads >> 4000-token budget (~16000 chars).
    sel.gotchas = [
        {"source_id": i, "kind": "gotcha", "head": "x" * 100} for i in range(200)
    ]
    out = render_bundle(
        sel,
        cc_session_id="x",
        session_id=1,
        cwd="/x",
        trigger="pre_compact",
        token_budget=200,  # ~800 chars
        generated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )
    # 4 chars/token approximation: 200 tokens ≈ 800 chars. Render must stay close.
    assert len(out.markdown) <= 200 * 4 * 1.2  # 20% slack for headers


def test_render_rejects_unknown_trigger() -> None:
    sel = BundleSelection()
    with pytest.raises(ValueError):
        render_bundle(
            sel,
            cc_session_id="x",
            session_id=1,
            cwd="/x",
            trigger="bogus",
            token_budget=4000,
            generated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bundle_render.py -v
```
Expected: ImportError on `brain.hooks.render`.

- [ ] **Step 3: Implement render**

`src/brain/hooks/render.py`:

```python
"""Bundle render: BundleSelection → (manifest JSONB-ready dict, markdown body).

Markdown body is what SessionStart emits as additionalContext. Manifest is what
session_resume_bundles.manifest stores. Render is bounded by `token_budget`
(approximate: 4 chars/token); sections are dropped from least-important to
most-important to fit, with `Decisions` retained longest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from brain.hooks.bundle import BundleSelection

_VALID_TRIGGERS = ("pre_compact", "session_end", "manual")


@dataclass
class RenderedBundle:
    manifest: dict[str, Any]
    markdown: str


def _section_md(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    return f"\n## {title}\n" + "\n".join(f"- {ln}" for ln in lines) + "\n"


def render_bundle(
    selection: BundleSelection,
    *,
    cc_session_id: str,
    session_id: int,
    cwd: str,
    trigger: str,
    token_budget: int,
    generated_at: datetime,
) -> RenderedBundle:
    if trigger not in _VALID_TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}; expected one of {_VALID_TRIGGERS}")

    manifest = {
        "schema_version": 1,
        "session_id": session_id,
        "cc_session_id": cc_session_id,
        "cwd": cwd,
        "trigger": trigger,
        "generated_at": generated_at.isoformat(),
        "token_budget": token_budget,
        "selection": {
            "decisions": selection.decisions,
            "gotchas": selection.gotchas,
            "patterns": selection.patterns,
            "failures": selection.failures,
            "subtasks_open": selection.subtasks_open,
            "recent_events": selection.recent_events,
        },
    }

    # Render sections in priority order; we drop from the tail when over budget.
    sections_in_priority: list[tuple[str, list[str]]] = [
        ("Decisions", [f"[id={d['source_id']}] {d['head']}" for d in selection.decisions]),
        ("Recent gotchas", [f"[id={g['source_id']}] {g['head']}" for g in selection.gotchas]),
        ("Patterns", [f"[id={p['source_id']}] {p['head']}" for p in selection.patterns]),
        (
            "Unresolved failures",
            [
                f"target: {f['target_problem'][:60]}; approach: {f['approach'][:60]}; attempts: {f['retry_count']}"
                for f in selection.failures
            ],
        ),
        (
            "Open subtasks",
            [f"({t['subtask_id']}) {t['title']}" for t in selection.subtasks_open],
        ),
        (
            "Recent activity",
            [
                f"{e['occurred_at']} {e['event_kind']}: {str(e['payload'])[:80]}"
                for e in selection.recent_events
            ],
        ),
    ]

    header = (
        f"# Agent Brain resume bundle\n\n"
        f"Project `{cwd}`, session {session_id}, "
        f"triggered by `{trigger}` at {generated_at.isoformat()}.\n"
    )

    # Greedy assemble within ~4-chars-per-token budget.
    char_budget = token_budget * 4
    out = header
    for title, lines in sections_in_priority:
        block = _section_md(title, lines)
        if not block:
            continue
        if len(out) + len(block) > char_budget:
            # Try truncating the block down to a few lines that fit.
            remaining_chars = char_budget - len(out) - len(f"\n## {title}\n")
            if remaining_chars <= 20:
                continue
            truncated_lines: list[str] = []
            running = 0
            for ln in lines:
                added = len(f"- {ln}\n")
                if running + added > remaining_chars:
                    break
                truncated_lines.append(ln)
                running += added
            block = _section_md(title, truncated_lines)
            out += block
            break
        out += block

    return RenderedBundle(manifest=manifest, markdown=out)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bundle_render.py -v
```
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/hooks/render.py tests/test_bundle_render.py
git commit -m "feat(p3a-1): bundle render (manifest JSON + markdown body, token-budgeted)"
```

---

## Task 7: brain hook session-start CLI

**Files:**
- Create: `src/brain/hooks/cli.py`
- Modify: `src/brain/cli.py` (register the `hook` group)
- Create: `tests/test_hook_session_start.py`

This is where it all comes together: stdin JSON in, session row created, bundle lookup, additionalContext stdout.

- [ ] **Step 1: Write the failing test**

```python
"""brain hook session-start: stdin -> session row + bundle lookup + stdout."""

from __future__ import annotations

import json
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run_hook(event: str, payload: dict, env_db_url: str) -> tuple[int, str, str]:
    """Pipe JSON into `brain hook <event>` via subprocess; capture exit + streams."""
    result = subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": __import__("os").environ["PATH"], "BRAIN_DB_URL": env_db_url},
    )
    return result.returncode, result.stdout, result.stderr


def test_session_start_creates_session_row(pg_url: str) -> None:
    payload = {
        "session_id": "ss-1",
        "transcript_path": "/tmp/ss-1.jsonl",
        "cwd": "/tmp/proj-a",
        "hook_event_name": "SessionStart",
        "source": "startup",
        "model": "claude-opus",
    }
    rc, stdout, stderr = _run_hook("session-start", payload, pg_url)
    assert rc == 0, stderr
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT id, cwd FROM sessions WHERE cc_session_id = :cc"),
            {"cc": "ss-1"},
        ).one()
    assert row.cwd == "/tmp/proj-a"
    # Output is valid JSON with hookSpecificOutput
    obj = json.loads(stdout)
    assert obj["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_session_start_emits_empty_context_when_no_bundle(pg_url: str) -> None:
    payload = {
        "session_id": "ss-2",
        "transcript_path": "/tmp/ss-2.jsonl",
        "cwd": "/tmp/proj-empty",
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    rc, stdout, _ = _run_hook("session-start", payload, pg_url)
    assert rc == 0
    obj = json.loads(stdout)
    # additionalContext is empty (or a minimal "fresh session" marker), not None
    assert obj["hookSpecificOutput"]["additionalContext"] == ""


def test_session_start_injects_unconsumed_bundle(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # Plant a bundle for /tmp/proj-c first
    with session_scope(engine) as s:
        proj_id = s.execute(
            text(
                "INSERT INTO projects(slug, task_type, repo_root) "
                "VALUES ('p3a-test', 'development', '/tmp/proj-c') RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO session_resume_bundles("
                "project_id, trigger, token_budget, manifest, rendered, cwd"
                ") VALUES(:p, 'pre_compact', 4000, CAST('{}' AS jsonb), :r, :c)"
            ),
            {"p": proj_id, "r": "# Resume bundle\n\nplanted content here", "c": "/tmp/proj-c"},
        )

    payload = {
        "session_id": "ss-3",
        "transcript_path": "/tmp/ss-3.jsonl",
        "cwd": "/tmp/proj-c",
        "hook_event_name": "SessionStart",
        "source": "compact",
    }
    rc, stdout, _ = _run_hook("session-start", payload, pg_url)
    assert rc == 0
    obj = json.loads(stdout)
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert "planted content here" in ctx

    # Bundle should now be consumed
    with session_scope(engine) as s:
        consumed = s.execute(
            text(
                "SELECT consumed_at FROM session_resume_bundles WHERE cwd = :c ORDER BY id DESC LIMIT 1"
            ),
            {"c": "/tmp/proj-c"},
        ).scalar()
    assert consumed is not None


def test_session_start_records_event(pg_url: str) -> None:
    payload = {
        "session_id": "ss-4",
        "transcript_path": "/tmp/ss-4.jsonl",
        "cwd": "/tmp/proj-d",
        "hook_event_name": "SessionStart",
        "source": "resume",
    }
    _run_hook("session-start", payload, pg_url)
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(text("SELECT id FROM sessions WHERE cc_session_id = 'ss-4'")).scalar()
        kinds = [
            r.event_kind
            for r in s.execute(
                text("SELECT event_kind FROM session_events WHERE session_id = :i"), {"i": sid}
            ).fetchall()
        ]
    assert "session_start" in kinds
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_hook_session_start.py -v
```
Expected: `brain hook session-start` doesn't exist yet.

- [ ] **Step 3: Implement hook CLI**

`src/brain/hooks/cli.py`:

```python
"""Click sub-group for `brain hook <event>` — dispatches Claude Code hook stdin."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import click

from brain.db import get_engine, session_scope
from brain.hooks.bundle import gather_bundle_selection
from brain.hooks.contracts import (
    PreCompactInput,
    SessionEndInput,
    SessionStartInput,
    StopInput,
    UserPromptSubmitInput,
)
from brain.hooks.events import record_event
from brain.hooks.render import render_bundle
from brain.hooks.session import end_session, start_session
from sqlalchemy import text


@click.group()
@click.pass_context
def hook(ctx: click.Context) -> None:
    """Claude Code hook dispatcher. Reads stdin JSON, writes session state."""


def _read_stdin_json() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _emit_session_start_output(additional_context: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": additional_context,
        }
    }
    click.echo(json.dumps(payload))


def _emit_empty_output(event_name: str) -> None:
    click.echo(json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": ""}}))


@hook.command("session-start")
@click.pass_context
def session_start_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = SessionStartInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine,
        cc_session_id=inp.session_id,
        cwd=inp.cwd,
        agent="claude-code",
        source=inp.source,
    )
    record_event(
        engine,
        session_id=sid,
        event_kind="session_start",
        payload={"source": inp.source, "model": inp.model, "transcript_path": inp.transcript_path},
    )

    # Look for the latest unconsumed, non-superseded bundle for this cwd.
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT id, rendered FROM session_resume_bundles "
                "WHERE cwd = :c AND consumed_at IS NULL AND superseded_at IS NULL "
                "ORDER BY generated_at DESC LIMIT 1"
            ),
            {"c": inp.cwd},
        ).fetchone()
        if row is None:
            _emit_session_start_output("")
            return
        bundle_id, rendered = row.id, row.rendered
        s.execute(
            text("UPDATE session_resume_bundles SET consumed_at = :n WHERE id = :i"),
            {"n": datetime.now(timezone.utc), "i": bundle_id},
        )
    _emit_session_start_output(rendered)


@hook.command("session-end")
@click.pass_context
def session_end_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = SessionEndInput.model_validate(raw)
    engine = ctx.obj["engine"]
    end_session(engine, cc_session_id=inp.session_id, reason=inp.reason)
    # If the session row exists, append an event
    with session_scope(engine) as s:
        sid = s.execute(
            text("SELECT id FROM sessions WHERE cc_session_id = :cc"), {"cc": inp.session_id}
        ).scalar()
    if sid is not None:
        record_event(engine, session_id=sid, event_kind="session_end", payload={"reason": inp.reason})
    _emit_empty_output("SessionEnd")


@hook.command("user-prompt-submit")
@click.pass_context
def user_prompt_submit_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = UserPromptSubmitInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine, cc_session_id=inp.session_id, cwd=inp.cwd, agent="claude-code", source="resume"
    )
    record_event(engine, session_id=sid, event_kind="user_prompt_submit", payload={"prompt": inp.prompt[:1000]})
    _emit_empty_output("UserPromptSubmit")


@hook.command("stop")
@click.pass_context
def stop_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = StopInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine, cc_session_id=inp.session_id, cwd=inp.cwd, agent="claude-code", source="resume"
    )
    record_event(engine, session_id=sid, event_kind="stop", payload={"stop_hook_active": inp.stop_hook_active})
    _emit_empty_output("Stop")


@hook.command("pre-compact")
@click.pass_context
def pre_compact_cmd(ctx: click.Context) -> None:
    raw = _read_stdin_json()
    inp = PreCompactInput.model_validate(raw)
    engine = ctx.obj["engine"]
    sid = start_session(
        engine, cc_session_id=inp.session_id, cwd=inp.cwd, agent="claude-code", source="resume"
    )

    sel = gather_bundle_selection(engine, session_id=sid, cwd=inp.cwd, limit_per_kind=10)
    rendered = render_bundle(
        sel,
        cc_session_id=inp.session_id,
        session_id=sid,
        cwd=inp.cwd,
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime.now(timezone.utc),
    )

    # Find or create the project row for this cwd
    with session_scope(engine) as s:
        project_id = s.execute(
            text("SELECT id FROM projects WHERE repo_root = :r"), {"r": inp.cwd}
        ).scalar()
        if project_id is None:
            # Use basename as slug + default to 'generic' task_type if none exists
            slug = inp.cwd.rstrip("/").rsplit("/", 1)[-1] or "anon"
            project_id = s.execute(
                text(
                    "INSERT INTO projects(slug, task_type, repo_root) "
                    "VALUES (:s, 'generic', :r) ON CONFLICT (slug) DO UPDATE SET repo_root = EXCLUDED.repo_root "
                    "RETURNING id"
                ),
                {"s": slug, "r": inp.cwd},
            ).scalar()
        # Supersede existing unconsumed bundle for this cwd
        s.execute(
            text(
                "UPDATE session_resume_bundles SET superseded_at = NOW() "
                "WHERE cwd = :c AND consumed_at IS NULL AND superseded_at IS NULL"
            ),
            {"c": inp.cwd},
        )
        s.execute(
            text(
                "INSERT INTO session_resume_bundles("
                "project_id, session_id, trigger, token_budget, manifest, rendered, cwd) "
                "VALUES(:p, :s, 'pre_compact', :tb, CAST(:m AS jsonb), :r, :c)"
            ),
            {
                "p": project_id,
                "s": sid,
                "tb": rendered.manifest["token_budget"],
                "m": json.dumps(rendered.manifest),
                "r": rendered.markdown,
                "c": inp.cwd,
            },
        )

    record_event(engine, session_id=sid, event_kind="pre_compact", payload={"trigger": inp.trigger})

    # Stdout becomes "custom compact instructions" — give the compactor a hint.
    click.echo(
        "Compaction note: the brain has persisted a structured resume bundle "
        "for this session. After compaction, the next session's SessionStart "
        "hook will reinject the most recent decisions, gotchas, unresolved "
        "failures, and open subtasks. The compactor may safely shorten chat "
        "scrollback aggressively — durable knowledge is in the brain."
    )
```

Modify `src/brain/cli.py` — add to the imports + register the `hook` group on the `main` command:

```python
from brain.hooks.cli import hook as _hook_group

# After main is defined:
main.add_command(_hook_group)
```

Place this near the other `main.add_command` / `@main.command` definitions.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_hook_session_start.py -v
```
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/hooks/cli.py src/brain/cli.py tests/test_hook_session_start.py
git commit -m "feat(p3a-1): brain hook session-start + dispatcher group wired into CLI"
```

---

## Task 8: brain hook session-end / user-prompt-submit / stop tests

**Files:**
- Create: `tests/test_hook_session_end.py`
- Create: `tests/test_hook_user_prompt_submit.py`
- Create: `tests/test_hook_stop.py`

The CLI commands for these three were all written in Task 7. This task adds dedicated tests for each.

- [ ] **Step 1: Write the failing tests (one per file)**

`tests/test_hook_session_end.py`:

```python
"""brain hook session-end: marks session ended + records event."""

from __future__ import annotations

import json
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(payload: dict, db_url: str) -> tuple[int, str, str]:
    r = subprocess.run(
        ["brain", "hook", "session-end"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": __import__("os").environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode, r.stdout, r.stderr


def test_session_end_sets_ended_at(pg_url: str) -> None:
    # Pre-create the session via session-start
    subprocess.run(
        ["brain", "hook", "session-start"],
        input=json.dumps({
            "session_id": "se-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/se",
            "hook_event_name": "SessionStart", "source": "startup",
        }),
        text=True,
        env={"PATH": __import__("os").environ["PATH"], "BRAIN_DB_URL": pg_url},
    )
    rc, _, err = _run({
        "session_id": "se-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/se",
        "hook_event_name": "SessionEnd", "reason": "user_quit",
    }, pg_url)
    assert rc == 0, err
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        ended = s.execute(
            text("SELECT ended_at FROM sessions WHERE cc_session_id = 'se-1'")
        ).scalar()
    assert ended is not None


def test_session_end_for_unknown_session_is_noop(pg_url: str) -> None:
    rc, _, err = _run({
        "session_id": "ghost", "transcript_path": "/t.jsonl", "cwd": "/tmp",
        "hook_event_name": "SessionEnd", "reason": "ignored",
    }, pg_url)
    assert rc == 0, err  # Must not raise
```

`tests/test_hook_user_prompt_submit.py`:

```python
"""brain hook user-prompt-submit: records prompt event."""

from __future__ import annotations

import json
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(payload: dict, db_url: str) -> int:
    r = subprocess.run(
        ["brain", "hook", "user-prompt-submit"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": __import__("os").environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode


def test_user_prompt_submit_records_event(pg_url: str) -> None:
    rc = _run({
        "session_id": "ups-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/ups",
        "hook_event_name": "UserPromptSubmit", "prompt": "what is the brain?",
    }, pg_url)
    assert rc == 0
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT event_kind, payload FROM session_events "
                "JOIN sessions ON session_events.session_id = sessions.id "
                "WHERE sessions.cc_session_id = 'ups-1'"
            )
        ).fetchall()
    kinds = {r.event_kind for r in rows}
    assert "user_prompt_submit" in kinds
    prompt_row = next(r for r in rows if r.event_kind == "user_prompt_submit")
    assert prompt_row.payload["prompt"] == "what is the brain?"


def test_user_prompt_submit_truncates_long_prompts(pg_url: str) -> None:
    long_prompt = "x" * 5000
    rc = _run({
        "session_id": "ups-2", "transcript_path": "/t.jsonl", "cwd": "/tmp/ups2",
        "hook_event_name": "UserPromptSubmit", "prompt": long_prompt,
    }, pg_url)
    assert rc == 0
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        payload = s.execute(
            text(
                "SELECT payload FROM session_events "
                "JOIN sessions ON session_events.session_id = sessions.id "
                "WHERE sessions.cc_session_id = 'ups-2' AND event_kind = 'user_prompt_submit'"
            )
        ).scalar()
    assert len(payload["prompt"]) == 1000
```

`tests/test_hook_stop.py`:

```python
"""brain hook stop: records turn boundary."""

from __future__ import annotations

import json
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope


def _run(payload: dict, db_url: str) -> int:
    r = subprocess.run(
        ["brain", "hook", "stop"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": __import__("os").environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode


def test_stop_records_event(pg_url: str) -> None:
    rc = _run({
        "session_id": "stop-1", "transcript_path": "/t.jsonl", "cwd": "/tmp/stop",
        "hook_event_name": "Stop", "stop_hook_active": False,
    }, pg_url)
    assert rc == 0
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        kinds = [
            r.event_kind
            for r in s.execute(
                text(
                    "SELECT event_kind FROM session_events "
                    "JOIN sessions ON session_events.session_id = sessions.id "
                    "WHERE sessions.cc_session_id = 'stop-1'"
                )
            ).fetchall()
        ]
    assert "stop" in kinds
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
pytest tests/test_hook_session_end.py tests/test_hook_user_prompt_submit.py tests/test_hook_stop.py -v
```
Expected: 5 pass total (2 + 2 + 1).

- [ ] **Step 3: Commit**

```bash
git add tests/test_hook_session_end.py tests/test_hook_user_prompt_submit.py tests/test_hook_stop.py
git commit -m "test(p3a-1): hook session-end, user-prompt-submit, stop integration tests"
```

---

## Task 9: brain hook pre-compact tests

**Files:**
- Create: `tests/test_hook_pre_compact.py`

The CLI command was written in Task 7. This task adds the integration tests for the full PreCompact flow: bundle generation, INSERT, supersede-prior, stdout.

- [ ] **Step 1: Write the failing tests**

```python
"""brain hook pre-compact: gather + render + insert bundle + emit compact instructions."""

from __future__ import annotations

import json
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
        env={"PATH": __import__("os").environ["PATH"], "BRAIN_DB_URL": db_url},
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
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
pytest tests/test_hook_pre_compact.py -v
```
Expected: 3 pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_hook_pre_compact.py
git commit -m "test(p3a-1): pre-compact hook end-to-end (bundle insert + supersede)"
```

---

## Task 10: Plugin hooks dispatcher (hooks.json + run-hook.sh)

**Files:**
- Create: `hooks/hooks.json`
- Create: `hooks/run-hook.sh`

These ship inside the plugin and activate when the plugin is enabled. Claude Code resolves `${CLAUDE_PLUGIN_ROOT}` to the plugin install path.

- [ ] **Step 1: Write the dispatcher script**

`hooks/run-hook.sh`:

```bash
#!/usr/bin/env bash
# Plugin hook dispatcher for agent-brain.
#
# Claude Code invokes this via:
#   "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh <event>"
#
# We pipe stdin to `brain hook <event>`. Errors are non-fatal — the hook
# emits an empty hookSpecificOutput so the session can proceed.

set -uo pipefail

EVENT="${1:-unknown}"

if ! command -v brain >/dev/null 2>&1; then
  # brain CLI not on PATH — emit empty additionalContext so SessionStart
  # doesn't error. Other events ignore stdout, so the empty JSON is fine.
  cat <<EOF
{"hookSpecificOutput":{"hookEventName":"${EVENT}","additionalContext":""}}
EOF
  exit 0
fi

exec brain hook "$EVENT"
```

- [ ] **Step 2: Write the hooks.json**

`hooks/hooks.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh session-start",
            "timeout": 15
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh session-end",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh user-prompt-submit",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh stop",
            "timeout": 5
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh pre-compact",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Make dispatcher executable + sanity-check JSON**

```bash
chmod +x hooks/run-hook.sh
python -c "import json; json.load(open('hooks/hooks.json')); print('hooks.json valid')"
```

- [ ] **Step 4: Manual smoke test**

```bash
echo '{"session_id":"smoke","transcript_path":"/t.jsonl","cwd":"/tmp","hook_event_name":"SessionStart","source":"startup"}' \
  | bash hooks/run-hook.sh session-start
```
Expected: a JSON object on stdout with `hookSpecificOutput`.

- [ ] **Step 5: Commit**

```bash
git add hooks/hooks.json hooks/run-hook.sh
git commit -m "feat(p3a-1): plugin-shipped hook dispatcher (hooks.json + run-hook.sh)"
```

---

## Task 11: brain-session-log skill

**Files:**
- Create: `skills/brain-session-log/SKILL.md`
- Create: `skills/brain-session-log/scripts/session-log.sh`
- Modify: `src/brain/cli.py` (add `brain session-log` subcommand)

- [ ] **Step 1: Add CLI subcommand**

In `src/brain/cli.py`, add (placed near `brain status`):

```python
@main.command(name="session-log")
@click.option("--limit", default=20, type=int)
@click.option("--cc-session-id", help="Filter to a specific Claude Code session UUID")
@click.pass_context
def session_log_cmd(ctx: click.Context, limit: int, cc_session_id: str | None) -> None:
    """List recent session_events (filterable by Claude Code session UUID)."""
    from sqlalchemy import text as _text
    from brain.db import session_scope as _scope

    engine = ctx.obj["engine"]
    with _scope(engine) as s:
        if cc_session_id is not None:
            rows = s.execute(
                _text(
                    "SELECT se.occurred_at, se.event_kind, se.payload, ses.cc_session_id "
                    "FROM session_events se JOIN sessions ses ON se.session_id = ses.id "
                    "WHERE ses.cc_session_id = :cc "
                    "ORDER BY se.occurred_at DESC LIMIT :n"
                ),
                {"cc": cc_session_id, "n": limit},
            ).fetchall()
        else:
            rows = s.execute(
                _text(
                    "SELECT se.occurred_at, se.event_kind, se.payload, ses.cc_session_id "
                    "FROM session_events se JOIN sessions ses ON se.session_id = ses.id "
                    "ORDER BY se.occurred_at DESC LIMIT :n"
                ),
                {"n": limit},
            ).fetchall()
    t = Table("when", "cc_session", "kind", "payload_head", title="Session events")
    for r in rows:
        head = str(r.payload)[:60]
        t.add_row(r.occurred_at.isoformat(), r.cc_session_id[:8], r.event_kind, head)
    console.print(t)
```

- [ ] **Step 2: Create skill files**

`skills/brain-session-log/SKILL.md`:

```markdown
---
name: brain-session-log
description: Use when you want to see what's been captured this session (or any prior session) — user prompts, turn boundaries, session starts/ends, pre-compact triggers. Helps debug under-capture or replay decision history.
---

# brain-session-log

Inspect what hooks have captured.

## When to use

- "What did I work on this session?" — see the chronological user-prompt + stop event trail.
- Debugging: hook didn't fire as expected; check what made it into session_events.
- Reviewing a prior session by its Claude Code UUID.

## How

```bash
bash skills/brain-session-log/scripts/session-log.sh [--limit 20] [--cc-session-id <uuid>]
```

Prints a rich table of (when, cc_session, kind, payload head).

## Output budget

≤200 tokens. Summarize the table, don't paste the full thing.
```

`skills/brain-session-log/scripts/session-log.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec brain session-log "$@"
```

- [ ] **Step 3: Make script executable**

```bash
chmod +x skills/brain-session-log/scripts/session-log.sh
```

- [ ] **Step 4: Verify**

```bash
brain session-log --help
```
Expected: shows `--limit` and `--cc-session-id`.

- [ ] **Step 5: Commit**

```bash
git add skills/brain-session-log/ src/brain/cli.py
git commit -m "feat(p3a-1): brain-session-log skill + CLI subcommand"
```

---

## Task 12: brain-session-resume skill

**Files:**
- Create: `skills/brain-session-resume/SKILL.md`
- Create: `skills/brain-session-resume/scripts/session-resume.sh`
- Modify: `src/brain/cli.py` (add `brain session-resume`)

`brain session-resume` lets the user manually inspect or regenerate a bundle for a cwd.

- [ ] **Step 1: Add CLI subcommand**

In `src/brain/cli.py`:

```python
@main.command(name="session-resume")
@click.option("--cwd", default=None, help="Working directory (defaults to PWD)")
@click.option(
    "--mode",
    type=click.Choice(["show", "regenerate"]),
    default="show",
    help="show: print latest unconsumed bundle. regenerate: build a fresh one and print.",
)
@click.pass_context
def session_resume_cmd(ctx: click.Context, cwd: str | None, mode: str) -> None:
    """Inspect or regenerate the latest resume bundle for a cwd."""
    import os as _os
    from datetime import datetime as _dt, timezone as _tz
    import json as _json

    from sqlalchemy import text as _text

    from brain.db import session_scope as _scope
    from brain.hooks.bundle import gather_bundle_selection
    from brain.hooks.render import render_bundle
    from brain.hooks.session import start_session

    engine = ctx.obj["engine"]
    cwd_val = cwd or _os.getcwd()

    if mode == "show":
        with _scope(engine) as s:
            row = s.execute(
                _text(
                    "SELECT rendered, generated_at, consumed_at FROM session_resume_bundles "
                    "WHERE cwd = :c ORDER BY generated_at DESC LIMIT 1"
                ),
                {"c": cwd_val},
            ).fetchone()
        if row is None:
            click.echo(f"no bundles for cwd={cwd_val}")
            return
        click.echo(f"# Latest bundle for {cwd_val}")
        click.echo(f"# generated_at: {row.generated_at.isoformat()}")
        click.echo(f"# consumed_at: {row.consumed_at.isoformat() if row.consumed_at else 'unconsumed'}")
        click.echo("---")
        click.echo(row.rendered)
        return

    # regenerate
    sid = start_session(
        engine, cc_session_id=f"manual-regenerate-{_dt.now(_tz.utc).timestamp()}",
        cwd=cwd_val, agent="brain-cli", source="startup",
    )
    sel = gather_bundle_selection(engine, session_id=sid, cwd=cwd_val, limit_per_kind=10)
    rendered = render_bundle(
        sel, cc_session_id="manual", session_id=sid, cwd=cwd_val,
        trigger="manual", token_budget=4000, generated_at=_dt.now(_tz.utc),
    )
    with _scope(engine) as s:
        project_id = s.execute(
            _text("SELECT id FROM projects WHERE repo_root = :r"), {"r": cwd_val},
        ).scalar()
        if project_id is None:
            slug = cwd_val.rstrip("/").rsplit("/", 1)[-1] or "anon"
            project_id = s.execute(
                _text(
                    "INSERT INTO projects(slug, task_type, repo_root) "
                    "VALUES (:s, 'generic', :r) ON CONFLICT (slug) DO UPDATE SET repo_root = EXCLUDED.repo_root "
                    "RETURNING id"
                ),
                {"s": slug, "r": cwd_val},
            ).scalar()
        s.execute(
            _text(
                "UPDATE session_resume_bundles SET superseded_at = NOW() "
                "WHERE cwd = :c AND consumed_at IS NULL AND superseded_at IS NULL"
            ),
            {"c": cwd_val},
        )
        s.execute(
            _text(
                "INSERT INTO session_resume_bundles("
                "project_id, session_id, trigger, token_budget, manifest, rendered, cwd) "
                "VALUES(:p, :s, 'manual', :tb, CAST(:m AS jsonb), :r, :c)"
            ),
            {
                "p": project_id, "s": sid,
                "tb": rendered.manifest["token_budget"],
                "m": _json.dumps(rendered.manifest),
                "r": rendered.markdown, "c": cwd_val,
            },
        )
    click.echo(rendered.markdown)
```

- [ ] **Step 2: Create skill files**

`skills/brain-session-resume/SKILL.md`:

```markdown
---
name: brain-session-resume
description: Use to view the latest compaction-survival bundle for the current project, or regenerate it on demand. Default behavior: show the bundle that will be injected at the next SessionStart.
---

# brain-session-resume

Inspect or refresh the resume bundle.

## When to use

- "What will the next session see when it resumes?" — show mode.
- Just finished an important chunk; force a fresh bundle without waiting for `/compact` — regenerate mode.
- Debugging: bundle injection wasn't useful → check what's in it, then improve capture.

## How

```bash
bash skills/brain-session-resume/scripts/session-resume.sh [--cwd /path] [--mode show|regenerate]
```

Defaults to `--cwd $PWD` and `--mode show`.

## Output budget

The bundle itself is ≤4000 tokens. Don't echo it back to the user verbatim — describe what's there.
```

`skills/brain-session-resume/scripts/session-resume.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec brain session-resume "$@"
```

- [ ] **Step 3: Make script executable + verify**

```bash
chmod +x skills/brain-session-resume/scripts/session-resume.sh
brain session-resume --help
```

- [ ] **Step 4: Commit**

```bash
git add skills/brain-session-resume/ src/brain/cli.py
git commit -m "feat(p3a-1): brain-session-resume skill (show + regenerate modes)"
```

---

## Task 13: brain-handoff skill

**Files:**
- Create: `skills/brain-handoff/SKILL.md`
- Create: `skills/brain-handoff/scripts/handoff.sh`
- Modify: `src/brain/cli.py` (add `brain handoff`)

`brain handoff` exports the current bundle in a portable format for transferring to another agent or persisting outside the brain.

- [ ] **Step 1: Add CLI subcommand**

In `src/brain/cli.py`:

```python
@main.command()
@click.option("--cwd", default=None, help="Working directory (defaults to PWD)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Write to file instead of stdout",
)
@click.pass_context
def handoff(ctx: click.Context, cwd: str | None, fmt: str, out: Path | None) -> None:
    """Export the current resume bundle (markdown or JSON) for handoff to another agent."""
    import os as _os
    import json as _json

    from sqlalchemy import text as _text

    from brain.db import session_scope as _scope

    engine = ctx.obj["engine"]
    cwd_val = cwd or _os.getcwd()
    with _scope(engine) as s:
        row = s.execute(
            _text(
                "SELECT rendered, manifest FROM session_resume_bundles "
                "WHERE cwd = :c ORDER BY generated_at DESC LIMIT 1"
            ),
            {"c": cwd_val},
        ).fetchone()
    if row is None:
        click.echo(f"no bundle for cwd={cwd_val}; run `brain session-resume --mode regenerate` first", err=True)
        ctx.exit(1)
    body = row.rendered if fmt == "markdown" else _json.dumps(row.manifest, indent=2)
    if out is not None:
        out.write_text(body)
        click.echo(f"wrote {len(body)} bytes to {out}")
    else:
        click.echo(body)
```

- [ ] **Step 2: Create skill files**

`skills/brain-handoff/SKILL.md`:

```markdown
---
name: brain-handoff
description: Use when transferring context to another agent, another machine, or saving a checkpoint outside the brain. Exports the current resume bundle as markdown (default) or JSON. Pipe-able.
---

# brain-handoff

Export the current bundle.

## When to use

- Switching agents (Claude Code → Cursor or vice versa).
- Sharing context with a collaborator.
- Archiving a session's state before destructive work.

## How

```bash
bash skills/brain-handoff/scripts/handoff.sh [--cwd /path] [--format markdown|json] [--out file]
```

Defaults: markdown, stdout.

## Output budget

Don't paste the bundle back to the user. Confirm export.
```

`skills/brain-handoff/scripts/handoff.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
exec brain handoff "$@"
```

- [ ] **Step 3: Make script executable + verify**

```bash
chmod +x skills/brain-handoff/scripts/handoff.sh
brain handoff --help
```

- [ ] **Step 4: Commit**

```bash
git add skills/brain-handoff/ src/brain/cli.py
git commit -m "feat(p3a-1): brain-handoff skill (markdown/json bundle export)"
```

---

## Task 14: End-to-end test

**Files:**
- Create: `tests/test_end_to_end_phase3a_1.py`

- [ ] **Step 1: Write the end-to-end test**

```python
"""End-to-end Phase 3a-1: simulate session lifecycle via hook subprocess invocations.

Walks the full path:
  1. SessionStart (startup) - new session
  2. UserPromptSubmit - prompt captured
  3. Several decision/gotcha writes
  4. PreCompact - bundle generated + persisted
  5. SessionStart (compact) on a new cc_session_id - bundle injected via additionalContext
  6. The injected bundle contains the prior decisions/gotchas
"""

from __future__ import annotations

import json
import os
import subprocess

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.schemas import SourceInput
from brain.write import write


def _hook(event: str, payload: dict, db_url: str) -> tuple[int, str]:
    r = subprocess.run(
        ["brain", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BRAIN_DB_URL": db_url},
    )
    return r.returncode, r.stdout


def test_phase3a_1_full_lifecycle(pg_url: str) -> None:
    engine = get_engine(pg_url)
    cwd = "/tmp/e2e-3a1"

    # 1. SessionStart (startup)
    rc, out = _hook("session-start", {
        "session_id": "e2e-startup",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "SessionStart",
        "source": "startup",
    }, pg_url)
    assert rc == 0
    # No bundle yet -> empty additionalContext
    assert json.loads(out)["hookSpecificOutput"]["additionalContext"] == ""

    # 2. UserPromptSubmit
    _hook("user-prompt-submit", {
        "session_id": "e2e-startup",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "UserPromptSubmit",
        "prompt": "let's ship phase 3a-1",
    }, pg_url)

    # 3. Capture some decisions/gotchas
    write(engine, SourceInput(kind="decision", content="ship 3a-1 first; failure capture goes to 3a-2"))
    write(engine, SourceInput(kind="gotcha", content="PreCompact stdout becomes compact instructions, not next-session context"))
    write(engine, SourceInput(kind="pattern", content="DB-mediated bundle handoff via consumed_at flag"))

    # 4. PreCompact
    rc, stdout = _hook("pre-compact", {
        "session_id": "e2e-startup",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "PreCompact",
        "trigger": "manual",
    }, pg_url)
    assert rc == 0
    assert "brain" in stdout.lower()

    # Verify bundle persisted
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT trigger, consumed_at, rendered FROM session_resume_bundles WHERE cwd = :c ORDER BY id DESC LIMIT 1"),
            {"c": cwd},
        ).one()
    assert row.trigger == "pre_compact"
    assert row.consumed_at is None
    assert "ship 3a-1" in row.rendered
    assert "::jsonb" not in row.rendered or "PreCompact" in row.rendered  # one of the planted gotchas

    # 5. New SessionStart with source=compact
    rc, out = _hook("session-start", {
        "session_id": "e2e-postcompact",
        "transcript_path": "/tmp/e2e.jsonl",
        "cwd": cwd,
        "hook_event_name": "SessionStart",
        "source": "compact",
    }, pg_url)
    assert rc == 0
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]

    # 6. Injected bundle contains the planted content
    assert "ship 3a-1" in ctx  # decision survived
    assert "DB-mediated bundle handoff" in ctx  # pattern survived

    # 7. Bundle is now consumed
    with session_scope(engine) as s:
        consumed = s.execute(
            text("SELECT consumed_at FROM session_resume_bundles WHERE cwd = :c ORDER BY id DESC LIMIT 1"),
            {"c": cwd},
        ).scalar()
    assert consumed is not None
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/test_end_to_end_phase3a_1.py -v
```
Expected: 1 pass. Full suite should be at ~150 tests (131 baseline + ~19 new across 3a-1 tasks).

- [ ] **Step 3: Commit**

```bash
git add tests/test_end_to_end_phase3a_1.py
git commit -m "test(p3a-1): end-to-end lifecycle (SessionStart -> PreCompact -> bundle survival -> SessionStart)"
```

---

## Task 15: Docs + plugin v0.5.0 + README

**Files:**
- Create: `docs/phase3a_1.md`
- Modify: `README.md`
- Modify: `.claude-plugin/plugin.json` (version 0.5.0)
- Modify: `.cursor-plugin/plugin.json` (version 0.5.0)
- Modify: `.codex-plugin/plugin.json` (version 0.5.0)
- Modify: `gemini-extension.json` (version 0.5.0)
- Modify: `.claude-plugin/marketplace.json` (version 0.5.0)

- [ ] **Step 1: Create docs/phase3a_1.md**

```markdown
# Agent Brain v2 — Phase 3a-1 Operations

Phase 3a-1 ships the compaction-survival core: Claude Code hooks (5 events), session_resume_bundles auto-generation on PreCompact, automatic injection at SessionStart, and 3 manual-control skills.

## What changed

- **Schema:** migration 010 — `sessions.cc_session_id`, `sessions.cwd`, `session_resume_bundles.consumed_at`, `session_resume_bundles.cwd`, new `session_events` table.
- **Hooks:** `<plugin>/hooks/hooks.json` registers SessionStart, SessionEnd, UserPromptSubmit, Stop, PreCompact. All dispatch to `brain hook <event>`.
- **CLI:** new `brain hook` sub-group (called by hooks; not for direct user invocation) and three user-facing commands: `brain session-log`, `brain session-resume`, `brain handoff`.
- **Skills:** `brain-session-log`, `brain-session-resume`, `brain-handoff`.

## The compaction-survival loop

1. User runs `/compact` (or context fills naturally).
2. `PreCompact` hook fires. `brain hook pre-compact` runs:
   - Queries decisions, gotchas, patterns, failures, open subtasks, recent events.
   - Renders a manifest JSON + markdown body (≤4000 tokens).
   - INSERTs into `session_resume_bundles`, supersedes any prior unconsumed bundle for the same cwd.
   - Emits compact instructions to stdout (becomes the compactor's "custom compact instructions").
3. Claude Code compacts the session.
4. New session starts with `source=compact`.
5. `SessionStart` hook fires. `brain hook session-start` runs:
   - Looks up the latest unconsumed, non-superseded bundle for this cwd.
   - Emits the markdown body as `additionalContext` JSON.
   - Marks the bundle `consumed_at = now()`.
6. The new session sees the bundle as a system reminder in its initial context.

## Migration from Phase 2.5

```bash
source .venv/bin/activate
alembic upgrade head    # runs migration 010
```

Then enable the plugin if not already (it carries the hooks):

```
/plugin install agent-brain@agent-brain
/reload-plugins
```

## Setup verification

Verify hooks are registered:

```
/hooks
```

You should see `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `Stop`, `PreCompact` entries pointing at `${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh`.

Verify the loop end-to-end:

```bash
brain write --kind decision --content "test decision"
# Then trigger /compact in this Claude Code session.
# After compaction, new session should show:
#   "Decisions: [id=N] test decision"
# in its initial context.
```

## Known limitations

- **No transcript replay** in bundles yet. The `transcript_path` from SessionStart stdin is captured in `session_events.payload` but not used for richer bundle content. Phase 3b will add transcript-aware bundle generation.
- **No failure capture flow yet.** `failure_memories` are read into bundles, but auto-population from Stop hooks lands in Phase 3a-2.
- **No file watcher.** Obsidian-side edits don't sync back. Phase 3a-3.
- **No compliance audit yet.** Under-captured session detection lands in Phase 3a-4.
- **Bundle token budget is a heuristic** (4 chars/token). Tighter accounting (tiktoken) is a future tuning.

## Skills

| Skill | When to use |
|---|---|
| `brain-session-log` | "What was captured this session?" — list session_events |
| `brain-session-resume` | View or regenerate the latest bundle |
| `brain-handoff` | Export the bundle for transfer to another agent/machine |
```

- [ ] **Step 2: Update README**

Add a Phase 3a-1 section after the existing Phase 2.5 section:

```markdown
## Agent Brain v2 — Phase 3a-1

Phase 3a-1 ships the compaction-survival core. Claude Code's session lifecycle hooks (SessionStart/End, UserPromptSubmit, Stop, PreCompact) now write to the brain, and on `/compact` a structured resume bundle is persisted and re-injected at the next session's start.

```bash
alembic upgrade head    # migration 010
/plugin install agent-brain@agent-brain   # carries the hooks
/reload-plugins
```

3 new skills:

| Skill | When to use |
|---|---|
| `brain-session-log` | List recent session_events |
| `brain-session-resume` | Inspect or regenerate the latest bundle |
| `brain-handoff` | Export the bundle to markdown/JSON |

Operations: `docs/phase3a_1.md`. Plan: `docs/superpowers/plans/2026-05-25-agent-brain-v2-phase-3a-1.md`.

Follow-on plans queued: 3a-2 (failure capture + sanitization), 3a-3 (file watcher), 3a-4 (compliance subsystem).
```

- [ ] **Step 3: Bump versions**

Update all 5 manifests from `0.4.0` to `0.5.0`:

```bash
sed -i 's/"version": "0.4.0"/"version": "0.5.0"/' \
  .claude-plugin/plugin.json \
  .claude-plugin/marketplace.json \
  .cursor-plugin/plugin.json \
  .codex-plugin/plugin.json \
  gemini-extension.json
```

- [ ] **Step 4: Verify**

```bash
python -c "import json; assert json.load(open('.claude-plugin/plugin.json'))['version'] == '0.5.0'; print('claude ok')"
python -c "import json; assert json.load(open('.claude-plugin/marketplace.json'))['metadata']['version'] == '0.5.0'; print('marketplace ok')"
```

Run the full suite:

```bash
pytest -q
```
Expected: ~150 tests pass.

- [ ] **Step 5: Commit**

```bash
git add docs/phase3a_1.md README.md \
  .claude-plugin/plugin.json .claude-plugin/marketplace.json \
  .cursor-plugin/plugin.json .codex-plugin/plugin.json gemini-extension.json
git commit -m "docs(p3a-1): operations doc + README + plugin manifests v0.5.0"
```

---

## Self-Review

### Spec coverage

| Spec § Phase-3a bullet | Plan task |
|---|---|
| Claude Code hooks (PostToolUse, PreCompact, Stop, SessionStart, SessionEnd) — opt-in | Tasks 2, 7, 8, 9, 10 (PostToolUse deferred to 3a-2) |
| `session_resume_bundles` generator + selection algorithm + token-budget | Tasks 5, 6 |
| `SessionStart` delivers bundle via `additionalContext` | Task 7 |
| `PreCompact` only *persists* the bundle (no stdout-injection channel) | Task 7 — uses DB mediation per empirical finding |
| `brain-session-log`, `brain-session-resume`, `brain-handoff` skills | Tasks 11, 12, 13 |
| Failure-memory capture flow + `brain-failure` skill | **Deferred to 3a-2** |
| File-watcher (Obsidian → DB) | **Deferred to 3a-3** |
| Compliance subsystem | **Deferred to 3a-4** |
| Sanitization minimum | **Deferred to 3a-2** |

### Type consistency

- `BundleSelection` dataclass defined in Task 5, consumed by Task 6, 7, 12 — fields stable.
- `RenderedBundle` defined in Task 6, returned to Task 7 and Task 12 callers.
- `SessionStartInput` / etc. Pydantic schemas defined in Task 2, consumed throughout.
- `record_event` defined in Task 4 with signature `(engine, *, session_id, event_kind, payload)` — every caller in tasks 7, 8, 9 uses this exact shape.
- Schema column names: `cc_session_id`, `cwd`, `consumed_at` consistent everywhere.

### No placeholders

- Every code step has the complete code.
- Every command step has the exact command + expected output.
- No "TBD", "similar to Task N" without repeating, or "add appropriate error handling" appearing.
- 4 places call out empirical findings explicitly (PreCompact stdout, SessionStart matcher, plugin hook path syntax) to avoid future confusion.

### Dependency ordering

- T1 (migration) before T3 (which writes to sessions.cc_session_id, sessions.cwd).
- T2 (contracts) before T3-T9 (which parse contracts).
- T3 (session helpers) before T4 (events writer references session_id from start_session).
- T5 (bundle gather) and T6 (render) before T7 (pre-compact hook combines them).
- T7 (hook CLI) before T8/T9/T14 (which subprocess-exec the brain CLI).
- T10 (plugin dispatcher) is standalone — could ship anywhere from T7 onward.
- T11/T12/T13 (skills) require T7 (CLI is wired into main).
- T14 (e2e) last.
- T15 (docs/version) last.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-25-agent-brain-v2-phase-3a-1.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, fast iteration. Same pattern that shipped Phase 2 + Phase 2.5.
2. **Inline Execution** — execute in this session via executing-plans with checkpoints.

Which approach?
