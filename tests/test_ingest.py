"""brain.ingest_source: chunk + (optionally) contextualize + embed + persist."""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import IngestSummary, ingest_source
from brain.llm.client import HAIKU_MODEL_ID, HAIKU_MODEL_VER, LlmResult
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


def test_contextualize_inserts_chunk_context_rows(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    body = _make_text(40)
    src = SourceInput(kind="note", content=body)
    res = write(engine, src)
    client = MagicMock()
    # Distinct summary per call so each chunk_context row dedups uniquely.
    counter = {"n": 0}

    def _haiku(**_kwargs):
        counter["n"] += 1
        return LlmResult(
            text=f"Context summary number {counter['n']} for a long doc.",
            tokens_in=80,
            tokens_out=20,
            usd=0.0001,
            model_id=HAIKU_MODEL_ID,
            model_ver=HAIKU_MODEL_VER,
        )

    client.haiku.side_effect = _haiku
    summary = ingest_source(
        engine,
        source_id=res.source_id,
        embedder=bge_m3_embedder,
        llm_client=client,
        child_max_tokens=64,
        parent_max_tokens=256,
    )
    assert summary.chunks_created > 1
    assert summary.context_summaries_inserted == summary.chunks_created
    assert summary.embeddings_inserted == summary.chunks_created
    with session_scope(engine) as s:
        n_ctx = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = 'chunk_context' AND :pid = ANY(synthesized_from)"
            ),
            {"pid": res.source_id},
        ).scalar()
        assert n_ctx == summary.chunks_created
