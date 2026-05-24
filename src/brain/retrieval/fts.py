"""Phase 1 FTS query, extracted from read.py so recall() can fuse it with vector.

Returns FtsHit rows ordered by ts_rank_cd descending. Caller fuses via RRF.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text

from brain.db import session_scope


@dataclass(frozen=True)
class FtsHit:
    source_id: int
    score: float
    rank: int


_FTS_SQL = """
    SELECT
        s.id AS source_id,
        ts_rank_cd(f.tsv, plainto_tsquery('english', :q)) AS score
    FROM sources s
    JOIN sources_fts f ON f.source_id = s.id
    WHERE s.t_valid_to IS NULL
      AND (CAST(:include_archived AS boolean) OR s.status = 'active')
      AND f.tsv @@ plainto_tsquery('english', :q)
      AND (
            CAST(:project_id AS bigint) IS NULL
         OR s.project_id = CAST(:project_id AS bigint)
         OR EXISTS (
                SELECT 1 FROM source_projects sp
                WHERE sp.source_id = s.id
                  AND sp.project_id = CAST(:project_id AS bigint)
            )
      )
      AND (
            CAST(:buckets AS text[]) IS NULL
         OR EXISTS (
                SELECT 1 FROM memory_classifications mc
                WHERE mc.source_id = s.id
                  AND mc.bucket = ANY(CAST(:buckets AS text[]))
            )
      )
      AND (
            CAST(:kinds AS text[]) IS NULL
         OR s.kind = ANY(CAST(:kinds AS text[]))
      )
    ORDER BY score DESC
    LIMIT :k
"""


def fts_search(
    engine: Engine,
    *,
    query: str,
    k: int,
    project_id: int | None = None,
    buckets: list[str] | None = None,
    kinds: list[str] | None = None,
    include_archived: bool = False,
) -> list[FtsHit]:
    with session_scope(engine) as s:
        rows = s.execute(
            text(_FTS_SQL),
            {
                "q": query,
                "k": k,
                "project_id": project_id,
                "buckets": buckets,
                "kinds": kinds,
                "include_archived": include_archived,
            },
        ).fetchall()
    return [FtsHit(source_id=r[0], score=float(r[1]), rank=i + 1) for i, r in enumerate(rows)]
