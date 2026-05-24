"""End-to-end Phase 2 pipeline: write -> ingest -> recall (hybrid+rerank) -> summarize.

Verifies the full chain works together: BGE-M3 embeddings persist, kNN finds the
right hit, RRF + rerank surfaces it on top, retrieval_log captures metrics, and
a mocked reasoning helper produces a structured cited synthesis.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.llm.client import HAIKU_MODEL_ID, HAIKU_MODEL_VER, LlmResult
from brain.read import recall
from brain.reasoning.summarize import summarize
from brain.retrieval.rerank import MxbaiReranker
from brain.schemas import SourceInput
from brain.write import write


def test_phase2_full_pipeline(
    pg_url: str,
    bge_m3_embedder: BgeM3Embedder,
    mxbai_reranker: MxbaiReranker,
) -> None:
    engine = get_engine(pg_url)

    # 1. Write 3 sources of different kinds + 1 longer paper-style.
    sources = []
    for kind, body in (
        ("note", "postgres has full text search using to_tsvector and ts_rank_cd."),
        ("decision", "We chose pgvector over a dedicated vector DB for ops simplicity."),
        ("gotcha", "halfvec saves 50% storage vs float vector with negligible recall loss."),
        (
            "note",
            "Postgres pgvector supports both HNSW and IVFFlat indexes. HNSW is "
            "preferred for read-heavy workloads with low write rates. Use halfvec "
            "to reduce storage by half with minimal recall impact for embeddings "
            "above 768 dimensions. Cosine, L2, and inner-product distance ops "
            "are all supported.",
        ),
    ):
        res = write(engine, SourceInput(kind=kind, content=body))  # type: ignore[arg-type]
        sources.append(res.source_id)

    # 2. Ingest each (no contextual flow — keep test fast)
    for sid in sources:
        ingest_source(engine, source_id=sid, embedder=bge_m3_embedder)

    # 3. Recall via hybrid (FTS + vector + RRF + provenance + rerank)
    hits = recall(
        engine,
        "postgres pgvector HNSW",
        k=3,
        embedder=bge_m3_embedder,
        reranker=mxbai_reranker,
    )
    assert hits, "expected at least one hit from the hybrid pipeline"
    # The long pgvector source should be in the top-3.
    assert sources[3] in [h.id for h in hits]

    # 4. retrieval_log row was written
    with session_scope(engine) as s:
        log = s.execute(
            text(
                "SELECT query, candidates, top1_score, abstained, "
                "synthesized_ratio, captured_ratio "
                "FROM retrieval_log ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
    assert log.query == "postgres pgvector HNSW"
    assert log.abstained is False
    assert log.top1_score is not None
    assert log.candidates  # non-empty

    # 5. Summarize the hits via a mocked Haiku client
    hit_ids = [h.id for h in hits]
    fake_summary = (
        '{"summary": "Postgres pgvector supports HNSW indexes and halfvec storage.", '
        f'"citations": {hit_ids}}}'
    )
    client = MagicMock()
    client.haiku.return_value = LlmResult(
        text=fake_summary,
        tokens_in=300,
        tokens_out=120,
        usd=0.0001,
        model_id=HAIKU_MODEL_ID,
        model_ver=HAIKU_MODEL_VER,
    )
    out = summarize(engine, source_ids=hit_ids, llm_client=client)
    assert "pgvector" in out.summary.lower()
    assert set(out.citations) == set(hit_ids)

    # 6. Cache check: second summarize call hits cache
    out2 = summarize(engine, source_ids=hit_ids, llm_client=client)
    assert out2.summary == out.summary
    assert client.haiku.call_count == 1
