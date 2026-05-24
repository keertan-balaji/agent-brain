"""brain.ingest_source / ingest_prepare_contexts / ingest_finalize_contexts."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import (
    ChunkContext,
    ContextPreparation,
    IngestSummary,
    ingest_finalize_contexts,
    ingest_prepare_contexts,
    ingest_source,
)
from brain.schemas import SourceInput
from brain.write import write


def _make_text(n: int) -> str:
    return ". ".join(f"This is sentence number {i}" for i in range(n)) + "."


def test_short_source_one_chunk_one_embedding(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    src = SourceInput(kind="note", content="postgres is a relational database")
    res = write(engine, src)
    summary = ingest_source(engine, source_id=res.source_id, embedder=bge_m3_embedder)
    assert isinstance(summary, IngestSummary)
    assert summary.chunks_created == 1
    assert summary.embeddings_inserted == 1
    assert summary.context_summaries_inserted == 0
    with session_scope(engine) as s:
        n_embeddings = s.execute(
            text(
                "SELECT COUNT(*) FROM embeddings_1024 e "
                "JOIN sources s ON s.id = e.source_id "
                "WHERE COALESCE(s.parent_id, s.id) = :pid"
            ),
            {"pid": res.source_id},
        ).scalar()
        assert n_embeddings == 1


def test_long_source_multiple_children_with_embeddings(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    body = _make_text(80)
    src = SourceInput(kind="note", content=body)
    res = write(engine, src)
    summary = ingest_source(
        engine,
        source_id=res.source_id,
        embedder=bge_m3_embedder,
        child_max_tokens=64,
        parent_max_tokens=256,
    )
    assert summary.chunks_created > 1
    assert summary.embeddings_inserted == summary.chunks_created
    with session_scope(engine) as s:
        n_children = s.execute(
            text("SELECT COUNT(*) FROM sources WHERE parent_id = :pid"),
            {"pid": res.source_id},
        ).scalar()
        assert n_children == summary.chunks_created


def test_prepare_contexts_emits_per_chunk_prompts(pg_url: str) -> None:
    engine = get_engine(pg_url)
    body = _make_text(40)
    src = write(engine, SourceInput(kind="note", content=body)).source_id

    prep = ingest_prepare_contexts(
        engine, source_id=src, child_max_tokens=64, parent_max_tokens=256
    )
    assert isinstance(prep, ContextPreparation)
    assert prep.source_id == src
    assert prep.doc_body == body
    assert len(prep.chunks) > 1
    for c in prep.chunks:
        assert isinstance(c.chunk_idx, int)
        assert c.child_text
        # Prompt is the chunk_context template rendered with doc + chunk
        assert "<document>" in c.prompt
        assert body in c.prompt
        assert c.child_text in c.prompt


def test_finalize_contexts_inserts_chunk_context_rows(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    body = _make_text(40)
    src = write(engine, SourceInput(kind="note", content=body)).source_id

    prep = ingest_prepare_contexts(
        engine, source_id=src, child_max_tokens=64, parent_max_tokens=256
    )
    contexts = [
        ChunkContext(chunk_idx=c.chunk_idx, context=f"Context summary number {c.chunk_idx}.")
        for c in prep.chunks
    ]
    summary = ingest_finalize_contexts(
        engine,
        source_id=src,
        embedder=bge_m3_embedder,
        contexts=contexts,
        child_max_tokens=64,
        parent_max_tokens=256,
    )
    assert summary.chunks_created == len(prep.chunks)
    assert summary.context_summaries_inserted == len(prep.chunks)
    assert summary.embeddings_inserted == len(prep.chunks)
    with session_scope(engine) as s:
        n_ctx = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = 'chunk_context' AND :pid = ANY(synthesized_from)"
            ),
            {"pid": src},
        ).scalar()
        assert n_ctx == len(prep.chunks)


def test_finalize_contexts_raises_on_length_mismatch(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    body = _make_text(40)
    src = write(engine, SourceInput(kind="note", content=body)).source_id

    prep = ingest_prepare_contexts(
        engine, source_id=src, child_max_tokens=64, parent_max_tokens=256
    )
    # supply one fewer context than chunks
    contexts = [
        ChunkContext(chunk_idx=c.chunk_idx, context="x")
        for c in prep.chunks[:-1]
    ]
    with pytest.raises(ValueError):
        ingest_finalize_contexts(
            engine,
            source_id=src,
            embedder=bge_m3_embedder,
            contexts=contexts,
            child_max_tokens=64,
            parent_max_tokens=256,
        )
