"""entity_timeline(entity_id, from?, to?) — chronological events/decisions/failures
referencing an entity. Pure SQL, no LLM dependency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, text

from brain.db import session_scope


@dataclass(frozen=True)
class TimelineItem:
    occurred_at: datetime
    kind: str  # event kind (tool_call, decision, ...) or 'failure' / 'source'
    source_id: int | None
    role: str  # 'event' | 'failure' | 'source'
    summary: str


def entity_timeline(
    engine: Engine,
    entity_id: int,
    *,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> list[TimelineItem]:
    """Return chronological timeline of activity referencing the given entity.

    Walks three sources:
      - events.source_id pointing at sources referenced by the entity
      - failure_memories whose source_id matches
      - sources directly authored about the entity (via entities.source_id)
    """
    sql = """
        WITH entity_sources AS (
            SELECT s.id AS source_id
            FROM sources s
            JOIN entities e ON e.source_id = s.id
            WHERE e.id = :entity_id
        )
        SELECT
            ev.occurred_at AS occurred_at,
            ev.kind AS kind,
            ev.source_id AS source_id,
            'event' AS role,
            COALESCE(LEFT(src.content, 200), '') AS summary
        FROM events ev
        LEFT JOIN sources src ON src.id = ev.source_id
        WHERE ev.source_id IN (SELECT source_id FROM entity_sources)
          AND (CAST(:from_ts AS TIMESTAMPTZ) IS NULL OR ev.occurred_at >= CAST(:from_ts AS TIMESTAMPTZ))
          AND (CAST(:to_ts AS TIMESTAMPTZ) IS NULL OR ev.occurred_at <= CAST(:to_ts AS TIMESTAMPTZ))

        UNION ALL

        SELECT
            fm.last_attempted_at AS occurred_at,
            'failure' AS kind,
            fm.source_id AS source_id,
            'failure' AS role,
            COALESCE(LEFT(fm.target_problem, 200), '') AS summary
        FROM failure_memories fm
        WHERE fm.source_id IN (SELECT source_id FROM entity_sources)
          AND (CAST(:from_ts AS TIMESTAMPTZ) IS NULL OR fm.last_attempted_at >= CAST(:from_ts AS TIMESTAMPTZ))
          AND (CAST(:to_ts AS TIMESTAMPTZ) IS NULL OR fm.last_attempted_at <= CAST(:to_ts AS TIMESTAMPTZ))

        UNION ALL

        SELECT
            s.created_at AS occurred_at,
            s.kind AS kind,
            s.id AS source_id,
            'source' AS role,
            COALESCE(LEFT(s.content, 200), '') AS summary
        FROM sources s
        WHERE s.id IN (SELECT source_id FROM entity_sources)
          AND (CAST(:from_ts AS TIMESTAMPTZ) IS NULL OR s.created_at >= CAST(:from_ts AS TIMESTAMPTZ))
          AND (CAST(:to_ts AS TIMESTAMPTZ) IS NULL OR s.created_at <= CAST(:to_ts AS TIMESTAMPTZ))

        ORDER BY occurred_at ASC
    """
    with session_scope(engine) as s:
        rows = s.execute(
            text(sql), {"entity_id": entity_id, "from_ts": from_ts, "to_ts": to_ts}
        ).fetchall()
    return [
        TimelineItem(
            occurred_at=r[0], kind=r[1], source_id=r[2], role=r[3], summary=r[4]
        )
        for r in rows
    ]
