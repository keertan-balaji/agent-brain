"""pgvector kNN retrieval over halfvec(1024) + HNSW (cosine)."""

from __future__ import annotations

from brain.db import get_engine
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.retrieval.vector import VectorHit, knn_search
from brain.schemas import SourceInput
from brain.write import write


def test_semantic_match_ranks_relevant_chunk_higher(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    pg_src = write(
        engine,
        SourceInput(kind="note", content="postgres is a relational database management system."),
    )
    fr_src = write(
        engine,
        SourceInput(kind="note", content="bananas are a yellow fruit grown in tropical climates."),
    )
    ingest_source(engine, source_id=pg_src.source_id, embedder=bge_m3_embedder)
    ingest_source(engine, source_id=fr_src.source_id, embedder=bge_m3_embedder)

    hits = knn_search(
        engine,
        query_text="which database engine should I use?",
        embedder=bge_m3_embedder,
        k=10,
    )
    assert len(hits) >= 1
    assert isinstance(hits[0], VectorHit)
    # postgres source should rank above banana source by parent_source_id
    pg_rank = next((h.rank for h in hits if h.parent_source_id == pg_src.source_id), None)
    fr_rank = next((h.rank for h in hits if h.parent_source_id == fr_src.source_id), None)
    assert pg_rank is not None, f"postgres source missing from hits: {hits}"
    if fr_rank is not None:
        assert pg_rank < fr_rank


def test_nonexistent_model_returns_empty(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    src = write(engine, SourceInput(kind="note", content="anything"))
    ingest_source(engine, source_id=src.source_id, embedder=bge_m3_embedder)

    hits = knn_search(
        engine,
        query_text="anything",
        embedder=bge_m3_embedder,
        k=10,
        model_id="nonexistent",
        model_ver="v0",
    )
    assert hits == []


def test_distance_is_monotone(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    for body in ("postgres database", "react frontend", "kubernetes pods"):
        src = write(engine, SourceInput(kind="note", content=body))
        ingest_source(engine, source_id=src.source_id, embedder=bge_m3_embedder)
    hits = knn_search(engine, query_text="postgres", embedder=bge_m3_embedder, k=10)
    for i in range(len(hits) - 1):
        assert hits[i].distance <= hits[i + 1].distance
        assert hits[i].rank < hits[i + 1].rank
