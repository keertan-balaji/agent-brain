"""reasoning.propose_links: suggest related sources via FTS + vector + entity graph.

Three retrieval legs, fused via RRF:
  1. Vector similarity: kNN search using the source's existing embedding
     (computed on the fly if missing).
  2. FTS overlap: full-text search using the first 100 chars of the source's
     content as the query.
  3. Shared-entity traversal: for each entity attached to this source, follow
     edges (relation graph) to neighbor entities, collect their source ids.

Pure SQL + vector — no LLM. The source itself is filtered out of the final
list. Rationale is the leg that contributed each candidate's highest rank.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.retrieval.fts import fts_search
from brain.retrieval.rrf import rrf_fuse
from brain.retrieval.vector import knn_search


class Proposal(BaseModel):
    target_source_id: int
    score: float
    rationale_kind: str


class LinkProposalList(BaseModel):
    proposals: list[Proposal]


def _load_source_content(engine: Engine, source_id: int) -> str:
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT content FROM sources WHERE id = :id"), {"id": source_id}
        ).one()
    return row[0]


def _entity_neighbor_sources(engine: Engine, source_id: int) -> list[int]:
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                """
                SELECT DISTINCT e2.source_id
                FROM entities e1
                JOIN edges ed ON ed.src_id = e1.id OR ed.dst_id = e1.id
                JOIN entities e2 ON e2.id = CASE
                    WHEN ed.src_id = e1.id THEN ed.dst_id
                    ELSE ed.src_id
                END
                WHERE e1.source_id = :sid
                  AND e2.source_id IS NOT NULL
                  AND e2.source_id <> :sid
                  AND e1.t_valid_to IS NULL
                  AND e2.t_valid_to IS NULL
                  AND ed.t_valid_to IS NULL
                """
            ),
            {"sid": source_id},
        ).fetchall()
    return [r[0] for r in rows]


def propose_links(
    engine: Engine,
    *,
    source_id: int,
    embedder: BgeM3Embedder,
    top_k: int = 10,
) -> LinkProposalList:
    content = _load_source_content(engine, source_id)

    # Leg 1: vector
    vec_hits = knn_search(engine, query_text=content, embedder=embedder, k=top_k * 5)
    vec_ids = [h.parent_source_id for h in vec_hits if h.parent_source_id != source_id]

    # Leg 2: FTS over first 100 chars (rough "title" surrogate)
    fts_query = content[:100]
    fts_hits = fts_search(engine, query=fts_query, k=top_k * 5)
    fts_ids = [h.source_id for h in fts_hits if h.source_id != source_id]

    # Leg 3: shared entities
    ent_ids = [i for i in _entity_neighbor_sources(engine, source_id) if i != source_id]

    # Fuse
    fused = rrf_fuse([vec_ids, fts_ids, ent_ids])
    # Build per-doc rationale: which leg ranked this doc highest (lowest rank)
    rank_by_leg = {
        "vector_similarity": {d: i for i, d in enumerate(vec_ids)},
        "fts_overlap": {d: i for i, d in enumerate(fts_ids)},
        "shared_entity": {d: i for i, d in enumerate(ent_ids)},
    }
    proposals: list[Proposal] = []
    for doc_id, score in fused[:top_k]:
        best_leg = "vector_similarity"
        best_rank = float("inf")
        for leg, ranks in rank_by_leg.items():
            if doc_id in ranks and ranks[doc_id] < best_rank:
                best_rank = ranks[doc_id]
                best_leg = leg
        proposals.append(
            Proposal(target_source_id=doc_id, score=score, rationale_kind=best_leg)
        )
    return LinkProposalList(proposals=proposals)
