"""pgvector kNN retrieval against embeddings_1024 (halfvec + HNSW cosine).

Returns chunks ranked by cosine distance; caller maps to parent source ids and
fuses with other ranked lists (FTS, future sparse/colbert legs) via RRF.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder


@dataclass
class VectorHit:
    chunk_id: int
    parent_source_id: int
    distance: float
    rank: int


def _halfvec_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]"


def knn_search(
    engine: Engine,
    *,
    query_text: str,
    embedder: BgeM3Embedder,
    k: int = 100,
    model_id: str | None = None,
    model_ver: str | None = None,
) -> list[VectorHit]:
    vec = embedder.embed_one(query_text)
    mid = model_id or embedder.model_id
    mver = model_ver or embedder.model_ver

    with session_scope(engine) as s:
        rows = s.execute(
            text(
                """
                SELECT
                    e.source_id AS chunk_id,
                    COALESCE(s.parent_id, s.id) AS parent_source_id,
                    e.vec <=> CAST(:vec AS halfvec) AS distance
                FROM embeddings_1024 e
                JOIN sources s ON s.id = e.source_id
                WHERE e.model_id = :mid AND e.model_ver = :mver
                  AND s.t_valid_to IS NULL
                ORDER BY distance ASC
                LIMIT :k
                """
            ),
            {"vec": _halfvec_literal(vec), "mid": mid, "mver": mver, "k": k},
        ).fetchall()

    return [
        VectorHit(chunk_id=r[0], parent_source_id=r[1], distance=float(r[2]), rank=i + 1)
        for i, r in enumerate(rows)
    ]
