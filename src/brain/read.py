"""brain.recall() — hybrid retrieval (FTS + vector kNN, fused via RRF).

Phase 1 (FTS-only) behavior is preserved: callers that don't pass embedder get
identical results. When embedder is provided, runs both FTS and pgvector kNN,
maps chunk hits to parent source ids, fuses by RRF, hydrates top-k.

When a reranker is provided, the fused list (up to rerank_candidate_pool)
is rehydrated and rescored by the cross-encoder; the top-k of those scores
becomes the final order. Per-bucket tau/abstain is added in Task 11.

Every recall() call writes a row to retrieval_log with the query, filters,
top-K candidates (per-stage scores), abstain flag, top1 score, provenance
ratios, and the agent identity (from BRAIN_AGENT env). session_id is NULL
until Phase 3a session hooks land.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.retrieval.fts import fts_search
from brain.retrieval.provenance import apply_diversity_cap, downweight_synthesized
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


def _load_provenance(engine: Engine, ids: list[int]) -> dict[int, tuple[str, int]]:
    if not ids:
        return {}
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, provenance_kind, generation_depth FROM sources "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": ids},
        ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


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


def _log_recall(
    engine: Engine,
    *,
    query: str,
    filters: dict,
    candidates: list[dict],
    abstained: bool,
    top1_score: float | None,
    synthesized_ratio: float | None,
    captured_ratio: float | None,
) -> None:
    with session_scope(engine) as s:
        s.execute(
            text(
                """
                INSERT INTO retrieval_log(
                    query, filters, candidates, abstained,
                    top1_score, synthesized_ratio, captured_ratio, agent
                ) VALUES (
                    :q, CAST(:f AS jsonb), CAST(:c AS jsonb), :a,
                    :t, :sr, :cr, :ag
                )
                """
            ),
            {
                "q": query,
                "f": json.dumps(filters),
                "c": json.dumps(candidates),
                "a": abstained,
                "t": top1_score,
                "sr": synthesized_ratio,
                "cr": captured_ratio,
                "ag": os.environ.get("BRAIN_AGENT"),
            },
        )


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

    Always writes a row to retrieval_log (see _log_recall).
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

    filters = {
        "project_id": project_id,
        "buckets": buckets,
        "kinds": kinds,
        "include_archived": include_archived,
    }

    if embedder is None:
        pre_tau = [(h.source_id, h.score) for h in fts_hits[:k]]
        # FTS-only path: only apply tau when caller explicitly set it
        post_tau = pre_tau if tau is None else _tau_or_abstain(pre_tau, buckets=buckets, tau=tau)
        hits = _hydrate(engine, post_tau)
        # abstained iff tau filtering emptied a non-empty list
        abstained = bool(pre_tau) and not post_tau
        _log_recall(
            engine,
            query=query,
            filters=filters,
            candidates=[{"id": d, "score": s, "stage": "fts"} for d, s in pre_tau],
            abstained=abstained,
            top1_score=(pre_tau[0][1] if pre_tau else None),
            synthesized_ratio=None,
            captured_ratio=None,
        )
        return hits

    vec_hits = knn_search(engine, query_text=query, embedder=embedder, k=over_k)
    vec_ids = [h.parent_source_id for h in vec_hits]

    fused = rrf_fuse([fts_ids, vec_ids])

    # Load provenance for the top expanded pool + a wider expansion pool used by diversity cap
    top_pool_size = max(rerank_candidate_pool, k * 3)
    top_pool = fused[:top_pool_size]
    expansion_pool = fused[top_pool_size : top_pool_size + 50]
    all_ids = [d for d, _ in top_pool] + [d for d, _ in expansion_pool]
    prov = _load_provenance(engine, all_ids)
    top_prov = {d: prov[d] for d, _ in top_pool if d in prov}
    pool_prov = {d: prov[d] for d, _ in expansion_pool if d in prov}

    fused = downweight_synthesized(top_pool, top_prov)
    fused = apply_diversity_cap(
        fused[:k] if reranker is None else fused[:rerank_candidate_pool],
        provenance=top_prov,
        expansion_pool=expansion_pool,
        pool_provenance=pool_prov,
    )

    if reranker is None:
        pre_tau = fused[:k]
        candidate_records = [{"id": d, "score": s, "stage": "rrf"} for d, s in pre_tau]
    else:
        hydrated_pool = _hydrate(engine, fused)
        cands = [(h.id, h.content) for h in hydrated_pool]
        reranked = reranker.rerank(query, cands, top_k=k)
        pre_tau = [(h.doc_id, h.score) for h in reranked]
        candidate_records = [{"id": d, "score": s, "stage": "rerank"} for d, s in pre_tau]

    # Per-reranker default tau (different rerankers output different score scales).
    # Only fall back to bucket-based default if no reranker is in play.
    effective_tau = tau
    if effective_tau is None and reranker is not None:
        effective_tau = getattr(reranker, "DEFAULT_TAU", None)
    post_tau = _tau_or_abstain(pre_tau, buckets=buckets, tau=effective_tau)
    hits = _hydrate(engine, post_tau)

    # Compute provenance ratios over the actual hits (use already-loaded prov when possible).
    if hits:
        hit_ids = [h.id for h in hits]
        missing = [i for i in hit_ids if i not in prov]
        if missing:
            prov.update(_load_provenance(engine, missing))
        synth_n = sum(
            1 for i in hit_ids if prov.get(i, ("captured", 0))[0] == "synthesized"
        )
        synth_ratio = synth_n / len(hit_ids)
        cap_ratio = 1.0 - synth_ratio
    else:
        synth_ratio = None
        cap_ratio = None

    _log_recall(
        engine,
        query=query,
        filters=filters,
        candidates=candidate_records,
        abstained=(len(post_tau) == 0),
        top1_score=(pre_tau[0][1] if pre_tau else None),
        synthesized_ratio=synth_ratio,
        captured_ratio=cap_ratio,
    )

    return hits
