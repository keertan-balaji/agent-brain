"""brain-health basic audit (Phase 1). Generative-lint mode lands Phase 4."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, text

from brain.compliance import under_captured_sessions
from brain.db import session_scope


@dataclass(frozen=True)
class UndercapturedSession:
    session_id: int
    project_id: int | None
    event_count: int


@dataclass
class HealthReport:
    table_row_counts: dict[str, int] = field(default_factory=dict)
    undercaptured_sessions: list[UndercapturedSession] = field(default_factory=list)
    orphan_classification_count: int = 0
    stale_active_count: int = 0
    tau_rolling_ratios: dict[str, float | None] = field(default_factory=dict)


_BUCKETS = ("semantic", "episodic", "procedural", "failure")


_TRACKED_TABLES = (
    "sources",
    "sources_fts",
    "source_projects",
    "memory_classifications",
    "projects",
    "sessions",
    "subtasks",
    "events",
    "failure_memories",
    "procedures",
    "entities",
    "edges",
    "retrieval_log",
    "session_resume_bundles",
)


def audit(engine: Engine, *, undercapture_threshold: int = 3) -> HealthReport:
    """Run all Phase-1 audit queries and return a structured report."""
    report = HealthReport()

    with session_scope(engine) as s:
        for table in _TRACKED_TABLES:
            n = s.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            report.table_row_counts[table] = int(n or 0)

        orphan = s.execute(
            text(
                "SELECT COUNT(*) FROM memory_classifications mc "
                "WHERE NOT EXISTS (SELECT 1 FROM sources s WHERE s.id = mc.source_id)"
            )
        ).scalar()
        report.orphan_classification_count = int(orphan or 0)

        stale = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE status = 'active' AND t_valid_from < NOW() - INTERVAL '90 days' "
                "AND t_valid_to IS NULL"
            )
        ).scalar()
        report.stale_active_count = int(stale or 0)

        for bucket in _BUCKETS:
            ratio = s.execute(
                text(
                    """
                    SELECT AVG(
                        cardinality(selected)::float
                        / NULLIF(jsonb_array_length(candidates), 0)
                    )
                    FROM (
                        SELECT selected, candidates
                        FROM retrieval_log
                        WHERE filters -> 'buckets' ? :bucket
                          AND selected IS NOT NULL
                          AND candidates IS NOT NULL
                        ORDER BY occurred_at DESC
                        LIMIT 100
                    ) recent
                    """
                ),
                {"bucket": bucket},
            ).scalar()
            report.tau_rolling_ratios[bucket] = (
                float(ratio) if ratio is not None else None
            )

    # Delegate to compliance helper which uses session_events (turn count) and
    # sources (substantive captures) — the correct surfaces for Claude Code sessions.
    # event_count now holds the substantive capture count (not events.id rows).
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
            event_count=r.capture_count,
        )
        for r in rows
    ]

    return report
