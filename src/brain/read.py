"""brain.read() — Phase 1 FTS-only retrieval with metadata pre-filter.

No embeddings, RRF, or rerank in Phase 1. The interface stays stable; Phase 2 adds
those stages behind the same recall() signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.schemas import Bucket


@dataclass(frozen=True)
class RecallHit:
    id: int
    kind: str
    content: str
    score: float
    project_id: int | None


def recall(
    engine: Engine,
    query: str,
    *,
    k: int = 10,
    project_id: int | None = None,
    buckets: list[Bucket] | None = None,
    kinds: list[str] | None = None,
    include_archived: bool = False,
) -> list[RecallHit]:
    """FTS retrieval with metadata pre-filter. Returns up to k ranked hits.

    Pre-filter contract matches spec §Retrieval step 1:
        WHERE s.t_valid_to IS NULL
          AND (include_archived OR s.status = 'active')
          AND optional project_id (primary or via source_projects M2M)
          AND optional buckets (via memory_classifications)
          AND optional kinds
    """
    sql = """
        SELECT
            s.id, s.kind, s.content, s.project_id,
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
    with session_scope(engine) as s:
        rows = s.execute(
            text(sql),
            {
                "q": query,
                "k": k,
                "project_id": project_id,
                "buckets": buckets,
                "kinds": kinds,
                "include_archived": include_archived,
            },
        ).fetchall()
    return [
        RecallHit(id=r[0], kind=r[1], content=r[2], project_id=r[3], score=float(r[4]))
        for r in rows
    ]
