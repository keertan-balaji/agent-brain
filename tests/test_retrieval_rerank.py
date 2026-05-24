"""mxbai cross-encoder reranker: pair scoring + final top_k selection."""

from __future__ import annotations

from brain.db import get_engine
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.read import recall
from brain.retrieval.rerank import MxbaiReranker, RerankedHit
from brain.schemas import SourceInput
from brain.write import write


def test_reranker_scores_relevant_pair_higher(mxbai_reranker: MxbaiReranker) -> None:
    scores = mxbai_reranker.score(
        [
            ("which database engine should i use?", "postgres is a relational database"),
            ("which database engine should i use?", "bananas are a yellow fruit"),
        ]
    )
    assert len(scores) == 2
    assert scores[0] > scores[1]


def test_rerank_returns_top_k_in_score_order(mxbai_reranker: MxbaiReranker) -> None:
    cands = [
        (1, "bananas grow in tropical climates"),
        (2, "postgres is a relational database"),
        (3, "react is a frontend library"),
    ]
    hits = mxbai_reranker.rerank("which database engine?", cands, top_k=2)
    assert len(hits) == 2
    assert isinstance(hits[0], RerankedHit)
    assert hits[0].doc_id == 2
    assert hits[0].score >= hits[1].score


def test_recall_with_reranker_finalizes_order(
    pg_url: str, bge_m3_embedder: BgeM3Embedder, mxbai_reranker: MxbaiReranker
) -> None:
    engine = get_engine(pg_url)
    for body in (
        "postgres is a relational database with mvcc",
        "bananas grow in tropical climates and are yellow",
        "react is a frontend ui library by meta",
    ):
        src = write(engine, SourceInput(kind="note", content=body))
        ingest_source(engine, source_id=src.source_id, embedder=bge_m3_embedder)
    hits = recall(
        engine,
        "which database engine should I use?",
        k=2,
        embedder=bge_m3_embedder,
        reranker=mxbai_reranker,
    )
    assert len(hits) >= 1
    assert "postgres" in hits[0].content
