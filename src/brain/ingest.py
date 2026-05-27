"""brain.ingest: chunk + embed sources.

Three entry points:

  ingest_source(engine, *, source_id, embedder, ...) -> IngestSummary
      Plain ingest. Chunks + embeds without per-chunk context summaries.
      Default for most ingests.

  ingest_prepare_contexts(engine, *, source_id, ...) -> ContextPreparation
      Step 1 of agent-driven Contextual Retrieval. Renders per-chunk prompts
      so the calling agent can fulfill them inline (no embedded LLM call).

  ingest_finalize_contexts(engine, *, source_id, embedder, contexts, ...) -> IngestSummary
      Step 2. Takes the agent's per-chunk context summaries and inserts them
      as `chunk_context` source rows (provenance_kind='synthesized'), then
      embeds the (context + child) text via BGE-M3.

The chunker runs again in finalize (deterministic given identical params +
content) so the agent doesn't pass back chunk text — chunk_idx is the only
linkage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.embed.chunker import chunk_document
from brain.schemas import SourceInput
from brain.write import write

_PROMPT_PATH = Path(__file__).parent / "ingest_prompts" / "chunk_context.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()


@dataclass
class IngestSummary:
    parent_source_id: int
    chunks_created: int
    context_summaries_inserted: int
    embeddings_inserted: int


@dataclass
class ChunkPrep:
    chunk_idx: int
    child_text: str
    prompt: str


@dataclass
class ContextPreparation:
    source_id: int
    doc_body: str
    chunks: list[ChunkPrep]


@dataclass
class ChunkContext:
    chunk_idx: int
    context: str


def _halfvec_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]"


def _load_source(engine: Engine, source_id: int) -> tuple[str, str, int | None]:
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT kind, content, project_id FROM sources "
                "WHERE id = :id AND t_valid_to IS NULL"
            ),
            {"id": source_id},
        ).one()
    return row[0], row[1], row[2]


def _load_source_with_uri(engine: Engine, source_id: int) -> tuple[str, str, int | None, str | None]:
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT kind, content, project_id, uri FROM sources "
                "WHERE id = :id AND t_valid_to IS NULL"
            ),
            {"id": source_id},
        ).one()
    return row[0], row[1], row[2], row[3]


def _nearest_markdown_header(parent_content: str, span_start: int) -> str | None:
    """For a chunk starting at span_start, walk backwards in the parent content
    to find the nearest preceding '#' / '##' / '###' header line."""
    if span_start <= 0:
        return None
    prefix = parent_content[:span_start]
    # Iterate lines in reverse, return the first that looks like a markdown header.
    for line in reversed(prefix.splitlines()):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            # Strip leading '#' marks and whitespace; cap length.
            header = stripped.lstrip("#").strip()
            if header:
                return header[:120]
    return None


def heuristic_contexts(
    parent_content: str,
    chunks,
    *,
    parent_kind: str,
    parent_uri: str | None,
) -> list[str]:
    """Generate deterministic per-chunk context prefixes for multi-chunk sources.

    Strategy:
      - Always prepend a source-level tag: "[From <kind>[ at <uri>]]"
      - For chunks landing inside markdown content, append the nearest preceding
        section header: "[Section: <header>]"
      - The same source-level tag repeats across chunks (cheap framing); the
        section header provides per-chunk disambiguation.

    Cheap, no LLM. For higher-quality per-chunk summaries use the agent-driven
    prepare-contexts / finalize-contexts flow (Phase 2.5).
    """
    source_tag = f"[From {parent_kind}{f' at {parent_uri}' if parent_uri else ''}]"
    contexts: list[str] = []
    for ch in chunks:
        header = _nearest_markdown_header(parent_content, ch.span_start)
        section_tag = f" [Section: {header}]" if header else ""
        contexts.append(f"{source_tag}{section_tag}")
    return contexts


def _insert_chunks_and_embeddings(
    engine: Engine,
    *,
    source_id: int,
    parent_kind: str,
    parent_project_id: int | None,
    parent_content: str,
    embedder: BgeM3Embedder,
    chunks,
    contexts: list[str] | None,
) -> IngestSummary:
    """Shared writer used by ingest_source (contexts=None) and ingest_finalize_contexts."""
    chunk_ids: list[int] = []
    embed_inputs: list[str] = []
    context_count = 0

    for i, ch in enumerate(chunks):
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
        if contexts is not None:
            ctx = contexts[i]
            ctx_src = SourceInput(
                kind="chunk_context",
                content=ctx,
                project_id=parent_project_id,
                provenance_kind="synthesized",
                synthesized_from=[source_id],
            )
            write(engine, ctx_src)
            context_count += 1
            embed_text = f"{ctx}\n\n{ch.child_text}"

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


def ingest_source(
    engine: Engine,
    *,
    source_id: int,
    embedder: BgeM3Embedder,
    child_max_tokens: int = 256,
    parent_max_tokens: int = 1024,
    contextual: bool = True,
) -> IngestSummary:
    """Chunk + embed a source.

    contextual=True (default): when the chunker emits >1 chunks, prepend a
    deterministic heuristic context to each chunk before embedding — source-kind
    tag plus the nearest preceding markdown header. Single-chunk sources skip
    contextual (chunk == whole doc, nothing to disambiguate). This is the cheap
    contextual variant; for LLM-generated per-chunk summaries use the agent-
    driven prepare-contexts / finalize-contexts flow.
    """
    parent_kind, parent_content, parent_project_id, parent_uri = _load_source_with_uri(
        engine, source_id
    )
    chunks = chunk_document(
        parent_content,
        child_max_tokens=child_max_tokens,
        parent_max_tokens=parent_max_tokens,
    )
    contexts: list[str] | None = None
    if contextual and len(chunks) > 1:
        contexts = heuristic_contexts(
            parent_content,
            chunks,
            parent_kind=parent_kind,
            parent_uri=parent_uri,
        )
    return _insert_chunks_and_embeddings(
        engine,
        source_id=source_id,
        parent_kind=parent_kind,
        parent_project_id=parent_project_id,
        parent_content=parent_content,
        embedder=embedder,
        chunks=chunks,
        contexts=contexts,
    )


def ingest_prepare_contexts(
    engine: Engine,
    *,
    source_id: int,
    child_max_tokens: int = 256,
    parent_max_tokens: int = 1024,
) -> ContextPreparation:
    _, parent_content, _ = _load_source(engine, source_id)
    chunks = chunk_document(
        parent_content,
        child_max_tokens=child_max_tokens,
        parent_max_tokens=parent_max_tokens,
    )
    rendered_chunks = [
        ChunkPrep(
            chunk_idx=i,
            child_text=ch.child_text,
            prompt=_PROMPT_TEMPLATE.format(document=parent_content, chunk=ch.child_text),
        )
        for i, ch in enumerate(chunks)
    ]
    return ContextPreparation(
        source_id=source_id,
        doc_body=parent_content,
        chunks=rendered_chunks,
    )


def ingest_finalize_contexts(
    engine: Engine,
    *,
    source_id: int,
    embedder: BgeM3Embedder,
    contexts: list[ChunkContext],
    child_max_tokens: int = 256,
    parent_max_tokens: int = 1024,
) -> IngestSummary:
    parent_kind, parent_content, parent_project_id = _load_source(engine, source_id)
    chunks = chunk_document(
        parent_content,
        child_max_tokens=child_max_tokens,
        parent_max_tokens=parent_max_tokens,
    )
    if len(contexts) != len(chunks):
        raise ValueError(
            f"contexts count mismatch: chunker produced {len(chunks)} chunks "
            f"but caller supplied {len(contexts)} contexts"
        )
    # Align by chunk_idx (order preserved by the chunker)
    contexts_sorted = sorted(contexts, key=lambda c: c.chunk_idx)
    if any(c.chunk_idx != i for i, c in enumerate(contexts_sorted)):
        raise ValueError("contexts chunk_idx values must cover 0..N-1 contiguously")
    context_strs = [c.context for c in contexts_sorted]
    return _insert_chunks_and_embeddings(
        engine,
        source_id=source_id,
        parent_kind=parent_kind,
        parent_project_id=parent_project_id,
        parent_content=parent_content,
        embedder=embedder,
        chunks=chunks,
        contexts=context_strs,
    )
