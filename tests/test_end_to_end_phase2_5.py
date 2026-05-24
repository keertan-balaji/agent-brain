"""End-to-end Phase 2.5: write -> ingest -> recall (hybrid+rerank) -> summarize agent-driven."""

from __future__ import annotations

import json

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.read import recall
from brain.reasoning.summarize import SummarizeOutput, summarize_finalize, summarize_prepare
from brain.retrieval.rerank import MxbaiReranker
from brain.schemas import SourceInput
from brain.write import write


def test_phase2_5_full_pipeline_agent_driven(
    pg_url: str, bge_m3_embedder: BgeM3Embedder, mxbai_reranker: MxbaiReranker
) -> None:
    engine = get_engine(pg_url)
    ids = []
    for kind, body in (
        ("note", "postgres has full text search."),
        ("decision", "we chose pgvector for ops simplicity."),
        ("note", "postgres pgvector supports HNSW with halfvec storage."),
    ):
        r = write(engine, SourceInput(kind=kind, content=body))
        ingest_source(engine, source_id=r.source_id, embedder=bge_m3_embedder)
        ids.append(r.source_id)

    hits = recall(
        engine,
        "postgres pgvector HNSW",
        k=3,
        embedder=bge_m3_embedder,
        reranker=mxbai_reranker,
    )
    assert hits
    assert ids[2] in [h.id for h in hits]

    hit_ids = [h.id for h in hits]
    bundle = summarize_prepare(engine, source_ids=hit_ids)
    assert bundle.cached is None
    assert all(f"[id={sid}]" in bundle.prompt for sid in hit_ids)

    # Agent would synthesize here. Test stand-in:
    fake_output = json.dumps({"summary": "pgvector supports HNSW + halfvec.", "citations": hit_ids})
    out = summarize_finalize(engine, cache_key=bundle.cache_key, raw_output=fake_output)
    assert isinstance(out, SummarizeOutput)
    assert "pgvector" in out.summary

    # Second prepare returns cached
    bundle2 = summarize_prepare(engine, source_ids=hit_ids)
    assert bundle2.cached is not None
    assert bundle2.cached.summary == out.summary

    # retrieval_log captured the recall
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT query, abstained, top1_score "
                "FROM retrieval_log ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
    assert row[0] == "postgres pgvector HNSW"
    assert row[1] is False
    assert row[2] is not None
