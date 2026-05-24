"""brain.recall() — hybrid retrieval (FTS + vector kNN, fused via RRF).

Phase 1 (FTS-only) behavior is preserved: callers that don't pass embedder get
identical results. When embedder is provided, runs both FTS and pgvector kNN,
maps chunk hits to parent source ids, fuses by RRF, hydrates top-k.

When a reranker is provided, the fused list (up to rerank_candidate_pool)
is rehydrated and rescored by the cross-encoder; the top-k of those scores
becomes the final order. Per-bucket tau/abstain is added in Task 11.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.retrieval.fts import fts_search
from brain.retrieval.rrf import rrf_fuse
from brain.retrieval.tau import default_tau_for, should_abstain
from brain.retrieval.vector import knn_search
from brain.schemas import Bucket

if TYPE_CHECKING:
    from brain.retrieval.rerank import MxbaiReranker


@dataclass(frozen=True)
class RecallHit:
    id: int
    kind: str
    content: str
    score: float
    project_id: int | None


def _hydrate(engine: Engine, ids_with_scores: list[tuple[int, float]]) -> list[RecallHit]:
    if not ids_with_scores:
        return []
    ids = [i for i, _ in ids_with_scores]
    score_map = dict(ids_with_scores)
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, kind, content, project_id FROM sources "
                "WHERE id = ANY(:ids) AND t_valid_to IS NULL"
            ),
            {"ids": ids},
        ).fetchall()
    by_id = {r[0]: r for r in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    return [
        RecallHit(id=r[0], kind=r[1], content=r[2], project_id=r[3], score=score_map[r[0]])
        for r in ordered
    ]


def _tau_or_abstain(
    scored: list[tuple[int, float]],
    *,
    buckets: list[Bucket] | None,
    tau: float | None,
) -> list[tuple[int, float]]:
    effective = tau if tau is not None else default_tau_for(buckets[0] if buckets else None)
    top = scored[0][1] if scored else None
    if should_abstain(top_score=top, tau=effective):
        return []
    return scored


def recall(
    engine: Engine,
    query: str,
    *,
    k: int = 10,
    project_id: int | None = None,
    buckets: list[Bucket] | None = None,
    kinds: list[str] | None = None,
    include_archived: bool = False,
    embedder: BgeM3Embedder | None = None,
    reranker: "MxbaiReranker | None" = None,
    rerank_candidate_pool: int = 50,
    tau: float | None = None,
) -> list[RecallHit]:
    """Hybrid retrieval. embedder=None -> FTS-only (Phase 1 behavior).
    reranker=None -> RRF fused order; reranker set -> cross-encoder finalizes.

    tau: per-bucket score floor. If None, derived from first bucket (or
    conservative default). FTS-only branch only enforces tau when caller
    sets it explicitly (ts_rank scores are unbounded and small, so the
    calibrated defaults would always abstain on Phase 1 results).
    """
    over_k = max(100, k * 10)
    fts_hits = fts_search(
        engine,
        query=query,
        k=over_k,
        project_id=project_id,
        buckets=buckets,
        kinds=kinds,
        include_archived=include_archived,
    )
    fts_ids = [h.source_id for h in fts_hits]

    if embedder is None:
        scored = [(h.source_id, h.score) for h in fts_hits[:k]]
        # FTS-only path: tau abstain only applied if caller explicitly set tau
        if tau is None:
            return _hydrate(engine, scored)
        return _hydrate(engine, _tau_or_abstain(scored, buckets=buckets, tau=tau))

    vec_hits = knn_search(engine, query_text=query, embedder=embedder, k=over_k)
    vec_ids = [h.parent_source_id for h in vec_hits]

    fused = rrf_fuse([fts_ids, vec_ids])

    if reranker is None:
        return _hydrate(engine, _tau_or_abstain(fused[:k], buckets=buckets, tau=tau))

    pool = fused[:rerank_candidate_pool]
    hydrated_pool = _hydrate(engine, pool)
    cands = [(h.id, h.content) for h in hydrated_pool]
    reranked = reranker.rerank(query, cands, top_k=k)
    scored = [(h.doc_id, h.score) for h in reranked]
    return _hydrate(engine, _tau_or_abstain(scored, buckets=buckets, tau=tau))
