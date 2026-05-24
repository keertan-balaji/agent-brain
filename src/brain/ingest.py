"""brain.ingest_source(): chunk + (optionally) contextualize + embed + persist.

Assumes the parent source row was already written via brain.write(). For each
child window produced by the chunker:
  1. Reuse brain.write() to insert a child source row (kind == parent.kind,
     parent_id, span offsets) — dedup-scoped and FTS-materialized automatically.
  2. If llm_client is provided, run Contextual Retrieval (Haiku) and persist the
     context summary as a separate `chunk_context` source row
     (provenance_kind='synthesized', synthesized_from=[parent_source_id]).
  3. Embed the (optionally contextualized) child text via BGE-M3 and INSERT into
     embeddings_1024 as a halfvec literal.

Returns IngestSummary with the counts to make tests + audit logs simple.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.embed.chunker import chunk_document
from brain.llm.client import AnthropicClient
from brain.llm.contextual import contextualize_chunk
from brain.schemas import SourceInput
from brain.write import write


@dataclass
class IngestSummary:
    parent_source_id: int
    chunks_created: int
    context_summaries_inserted: int
    embeddings_inserted: int


def _halfvec_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]"


def ingest_source(
    engine: Engine,
    *,
    source_id: int,
    embedder: BgeM3Embedder,
    llm_client: AnthropicClient | None = None,
    child_max_tokens: int = 256,
    parent_max_tokens: int = 1024,
) -> IngestSummary:
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT kind, content, project_id FROM sources "
                "WHERE id = :id AND t_valid_to IS NULL"
            ),
            {"id": source_id},
        ).one()
    parent_kind, parent_content, parent_project_id = row

    chunks = chunk_document(
        parent_content,
        child_max_tokens=child_max_tokens,
        parent_max_tokens=parent_max_tokens,
    )

    chunk_ids: list[int] = []
    embed_inputs: list[str] = []
    context_count = 0

    for ch in chunks:
        child_src = SourceInput(
            kind=parent_kind,
            content=ch.child_text,
            parent_id=source_id,
            project_id=parent_project_id,
            span_start=ch.span_start,
            span_end=ch.span_end,
        )
        child_res = write(engine, child_src)
        chunk_ids.append(child_res.source_id)

        embed_text = ch.child_text
        if llm_client is not None:
            ctx = contextualize_chunk(
                llm_client, document=parent_content, chunk=ch.child_text
            )
            ctx_src = SourceInput(
                kind="chunk_context",
                content=ctx.context_summary,
                project_id=parent_project_id,
                provenance_kind="synthesized",
                synthesized_from=[source_id],
            )
            write(engine, ctx_src)
            context_count += 1
            embed_text = ctx.contextualized_text

        embed_inputs.append(embed_text)

    vecs = embedder.embed_many(embed_inputs) if embed_inputs else np.zeros((0, embedder.dim))

    inserted = 0
    with session_scope(engine) as s:
        for cid, v in zip(chunk_ids, vecs):
            s.execute(
                text(
                    "INSERT INTO embeddings_1024(source_id, model_id, model_ver, vec) "
                    "VALUES (:sid, :mid, :mver, CAST(:vec AS halfvec)) "
                    "ON CONFLICT (source_id, model_id, model_ver) DO NOTHING"
                ),
                {
                    "sid": cid,
                    "mid": embedder.model_id,
                    "mver": embedder.model_ver,
                    "vec": _halfvec_literal(v),
                },
            )
            inserted += 1

    return IngestSummary(
        parent_source_id=source_id,
        chunks_created=len(chunks),
        context_summaries_inserted=context_count,
        embeddings_inserted=inserted,
    )
