"""Deep-tier recall (Phase 3b).

Composes:
  Self-Query (filter extraction) -> Multi-query expansion -> Fast-tier recall
  per-variant -> RRF fusion -> CRAG verification (gated by trigger conditions)

The trigger conditions for CRAG (spec §Retrieval hardening):
  1. Reranker top-1 score in [0.5, 0.7) — confidence-band where verification helps
  2. Caller explicitly passed --deep (always-on for this entry point)
  3. Query is in the failure bucket — over-eager near-miss recall

The Fast-tier helpers (embedder, reranker) are reused without reload.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.read import RecallHit, recall
from brain.reasoning.multi_query import MultiQueryExpander
from brain.reasoning.self_query import QueryFilterExtractor
from brain.reasoning.crag_verify import CragVerdict, CragVerifier
from brain.retrieval.rrf import rrf_fuse


@dataclass
class DeepRecallTrace:
    """Diagnostics returned alongside the hits (for eval + debugging)."""
    variants_used: list[str]
    filters_applied: dict
    crag_triggered: bool
    crag_verdicts: list[dict] | None


def recall_deep(
    engine: Engine,
    query: str,
    *,
    k: int = 10,
    project_id: int | None = None,
    embedder=None,
    reranker=None,
    tau: float | None = None,
    return_trace: bool = False,
) -> list[RecallHit] | tuple[list[RecallHit], DeepRecallTrace]:
    """Deep-tier recall. Falls back to Fast-tier recall when LLM caches are
    cold (the helpers' prepare() returns bundle.cached=None and the caller
    short-circuits with the original query)."""

    # ---- Self-Query filter extraction ------------------------------------
    sq = QueryFilterExtractor(engine=engine)
    sq_bundle = sq.prepare(query)
    if sq_bundle.cached is not None:
        residual = sq_bundle.cached.residual_query
        kinds = sq_bundle.cached.kinds or None
        since_iso = sq_bundle.cached.since_iso
        until_iso = sq_bundle.cached.until_iso
    else:
        # Cache miss — use the original query as residual, no filters.
        residual = query
        kinds = None
        since_iso = None
        until_iso = None

    # ---- Multi-query expansion -------------------------------------------
    mq = MultiQueryExpander(engine=engine)
    mq_bundle = mq.prepare(residual)
    if mq_bundle.cached is not None:
        variants = mq_bundle.cached.variants
    else:
        # Cache miss — single-variant degraded to Fast-tier recall.
        variants = [residual]

    # ---- Per-variant Fast-tier recall + RRF fusion -----------------------
    # rrf_fuse expects Sequence[Iterable[int]] (plain doc IDs, not tuples).
    # When no reranker is present tau=None triggers per-bucket abstain on raw
    # RRF scores (which are not calibrated).  Default to tau=0 so all results
    # pass through; callers that want abstain should pass a reranker explicitly.
    effective_tau = tau if tau is not None else (None if reranker is not None else 0.0)
    per_variant_id_lists: list[list[int]] = []
    for v in variants:
        hits = recall(
            engine, v, k=k * 3,  # wider per-variant pool so fusion can reorder
            project_id=project_id, kinds=kinds,
            embedder=embedder, reranker=reranker, tau=effective_tau,
        )
        per_variant_id_lists.append([h.id for h in hits])

    fused = rrf_fuse(per_variant_id_lists)  # list[(id, rrf_score)]
    fused = fused[:max(k * 3, 30)]  # rerank pool for CRAG step

    # Apply temporal post-filter from Self-Query (since/until) if present.
    if since_iso or until_iso:
        fused = _filter_by_time(engine, fused, since_iso=since_iso, until_iso=until_iso)

    if not fused:
        if return_trace:
            return [], DeepRecallTrace(
                variants_used=variants,
                filters_applied={"kinds": kinds, "since_iso": since_iso, "until_iso": until_iso},
                crag_triggered=False,
                crag_verdicts=None,
            )
        return []

    # Hydrate top-pool source content for CRAG.
    top_pool = _hydrate(engine, fused[: max(k * 3, 20)])

    # ---- CRAG verification gate (always-on at deep tier) ----------------
    crag = CragVerifier(engine=engine)
    candidates = [{"id": h.id, "kind": h.kind, "content": h.content} for h in top_pool]
    crag_bundle = crag.prepare(query=query, candidates=candidates)
    if crag_bundle.cached is not None:
        kept_ids: set[int] = set()
        verdicts_meta = []
        for v in crag_bundle.cached.verdicts:
            verdicts_meta.append({
                "source_id": v.source_id,
                "score": v.score,
                "verdict": v.verdict.value,
                "reason": v.reason,
            })
            if v.verdict == CragVerdict.KEEP:
                kept_ids.add(v.source_id)
            elif v.verdict == CragVerdict.MERGE:
                # Merge band: keep but with rank softened. We surface them
                # AFTER all keeps in the final order.
                kept_ids.add(v.source_id)
        # Apply: keeps first (in fused order), then merges, then truncate to k.
        keep_set = {v.source_id for v in crag_bundle.cached.verdicts if v.verdict == CragVerdict.KEEP}
        merge_set = {v.source_id for v in crag_bundle.cached.verdicts if v.verdict == CragVerdict.MERGE}
        keeps_ordered = [h for h in top_pool if h.id in keep_set]
        merges_ordered = [h for h in top_pool if h.id in merge_set]
        final = (keeps_ordered + merges_ordered)[:k]
        if return_trace:
            return final, DeepRecallTrace(
                variants_used=variants,
                filters_applied={"kinds": kinds, "since_iso": since_iso, "until_iso": until_iso},
                crag_triggered=True,
                crag_verdicts=verdicts_meta,
            )
        return final

    # CRAG cache miss: skip verification, return fused top-k.
    final = top_pool[:k]
    if return_trace:
        return final, DeepRecallTrace(
            variants_used=variants,
            filters_applied={"kinds": kinds, "since_iso": since_iso, "until_iso": until_iso},
            crag_triggered=False,
            crag_verdicts=None,
        )
    return final


def _filter_by_time(
    engine: Engine,
    ids: list[tuple[int, float]],
    *,
    since_iso: str | None,
    until_iso: str | None,
) -> list[tuple[int, float]]:
    raw_ids = [d for d, _ in ids]
    if not raw_ids:
        return ids
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id FROM sources WHERE id = ANY(:ids) "
                "  AND (:since::timestamptz IS NULL OR created_at >= :since::timestamptz) "
                "  AND (:until::timestamptz IS NULL OR created_at <= :until::timestamptz)"
            ),
            {"ids": raw_ids, "since": since_iso, "until": until_iso},
        ).all()
        keep = {int(r.id) for r in rows}
    return [(d, s) for d, s in ids if d in keep]


def _hydrate(engine: Engine, ids_with_scores: list[tuple[int, float]]) -> list[RecallHit]:
    if not ids_with_scores:
        return []
    raw_ids = [d for d, _ in ids_with_scores]
    score_by_id = {d: s for d, s in ids_with_scores}
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, kind, content, project_id FROM sources "
                "WHERE id = ANY(:ids) AND t_valid_to IS NULL"
            ),
            {"ids": raw_ids},
        ).all()
    by_id = {int(r.id): r for r in rows}
    out: list[RecallHit] = []
    for sid, score in ids_with_scores:
        r = by_id.get(sid)
        if r is None:
            continue
        out.append(RecallHit(
            id=int(r.id),
            kind=r.kind,
            content=r.content,
            score=float(score),
            project_id=r.project_id,
        ))
    return out
