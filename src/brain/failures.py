"""Failure-memory helpers (Phase 3a-2).

Public API:
- record(): upsert with retry_count bump and invalidation-clear on re-occurrence.
- list_active(): t_valid_to IS NULL rows, optionally project-scoped.
- invalidate(): mark a row as superseded.

Every failure has a backing sources row (kind='gotcha') so the narrative
participates in FTS + retrieval down the line. The typed columns on
failure_memories are what makes "have we tried this?" a structured lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.schemas import SourceInput
from brain.write import write


@dataclass(frozen=True)
class FailureRow:
    id: int
    target_problem: str
    attempted_approach: str
    outcome_evidence: str | None
    retry_count: int
    last_attempted_at: datetime
    first_attempted_at: datetime
    project_id: int | None


def record(
    engine: Engine,
    *,
    target_problem: str,
    attempted_approach: str,
    outcome_evidence: str | None = None,
    project_id: int | None = None,
    auto_flagged_by: str | None = None,
) -> tuple[int, int]:
    """Upsert a failure_memories row. Returns (failure_id, retry_count_after)."""
    flags: dict[str, object] = {}
    if auto_flagged_by:
        flags["auto_flagged_by"] = auto_flagged_by

    narrative = outcome_evidence or f"{target_problem} :: {attempted_approach}"
    src_input = SourceInput(
        kind="gotcha",
        content=narrative,
        project_id=project_id,
        flags=flags,
    )
    src_result = write(engine, src_input)

    with session_scope(engine) as s:
        row = s.execute(
            text(
                """
                INSERT INTO failure_memories(
                    source_id, target_problem, attempted_approach, outcome_evidence,
                    project_id, retry_count, first_attempted_at, last_attempted_at
                ) VALUES (
                    :sid, :tp, :aa, :oe, :pid, 1, NOW(), NOW()
                )
                ON CONFLICT (target_problem, attempted_approach) DO UPDATE
                SET retry_count = failure_memories.retry_count + 1,
                    last_attempted_at = NOW(),
                    t_valid_to = NULL,
                    invalidation_reason = NULL,
                    outcome_evidence = COALESCE(EXCLUDED.outcome_evidence,
                                                failure_memories.outcome_evidence)
                RETURNING id, retry_count
                """
            ),
            {
                "sid": src_result.source_id,
                "tp": target_problem,
                "aa": attempted_approach,
                "oe": outcome_evidence,
                "pid": project_id,
            },
        ).first()
    assert row is not None
    return int(row.id), int(row.retry_count)


def list_active(
    engine: Engine,
    *,
    project_id: int | None = None,
    limit: int = 20,
) -> list[FailureRow]:
    sql = (
        "SELECT id, target_problem, attempted_approach, outcome_evidence, "
        "retry_count, last_attempted_at, first_attempted_at, project_id "
        "FROM failure_memories "
        "WHERE t_valid_to IS NULL "
    )
    params: dict[str, object] = {"lim": limit}
    if project_id is not None:
        sql += "AND project_id = :pid "
        params["pid"] = project_id
    sql += "ORDER BY last_attempted_at DESC LIMIT :lim"

    with session_scope(engine) as s:
        rows = s.execute(text(sql), params).all()
    return [
        FailureRow(
            id=r.id,
            target_problem=r.target_problem,
            attempted_approach=r.attempted_approach,
            outcome_evidence=r.outcome_evidence,
            retry_count=r.retry_count,
            last_attempted_at=r.last_attempted_at,
            first_attempted_at=r.first_attempted_at,
            project_id=r.project_id,
        )
        for r in rows
    ]


def invalidate(engine: Engine, *, failure_id: int, reason: str) -> None:
    with session_scope(engine) as s:
        s.execute(
            text(
                "UPDATE failure_memories "
                "SET t_valid_to = NOW(), invalidation_reason = :r "
                "WHERE id = :i AND t_valid_to IS NULL"
            ),
            {"i": failure_id, "r": reason},
        )
