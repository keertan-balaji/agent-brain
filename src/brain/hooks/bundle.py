"""Bundle selection: gather a snapshot of brain state for compaction-survival.

Picks:
  - Recent captured decisions / gotchas / patterns (last N each, by id desc).
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
