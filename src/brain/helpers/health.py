"""brain-health basic audit (Phase 1). Generative-lint mode lands Phase 4."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, text

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

        rows = s.execute(
            text(
                """
                SELECT sess.id, sess.project_id, COUNT(ev.id) AS event_count
                FROM sessions sess
                LEFT JOIN events ev ON ev.session_id = sess.id
                WHERE sess.ended_at IS NOT NULL
                GROUP BY sess.id, sess.project_id
                HAVING COUNT(ev.id) < :thresh
                ORDER BY sess.ended_at DESC
                """
            ),
            {"thresh": undercapture_threshold},
        ).fetchall()
        report.undercaptured_sessions = [
            UndercapturedSession(
                session_id=r[0], project_id=r[1], event_count=int(r[2])
            )
            for r in rows
        ]

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

    return report
