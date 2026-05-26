"""brain.write() — the single entry point for capturing a source into the brain.

Implements:
- scoped dedup via (kind, uri, content_hash) unique index
- bi-temporal re-assertion (invalidated rows free the slot)
- generation_depth computation for provenance discipline (max=3, depth-4 rejected)
- FTS row materialization (sources_fts)
- optional memory_classifications inserts
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, text

from brain.content_hash import sha256_bytes
from brain.db import session_scope
from brain.sanitize import sanitize_for_ingest
from brain.schemas import SourceInput, WriteResult


def _compute_generation_depth(
    engine: Engine, synthesized_from: list[int] | None, provenance_kind: str
) -> int:
    if provenance_kind != "synthesized" or not synthesized_from:
        return 0
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT generation_depth FROM sources WHERE id = ANY(:ids)"
            ),
            {"ids": synthesized_from},
        ).fetchall()
    if not rows:
        return 1  # synthesized but no traceable inputs — still depth-1 by definition
    return 1 + max(r[0] for r in rows)


def write(engine: Engine, source: SourceInput) -> WriteResult:
    """Insert a source, dedup-scoped to (kind, uri, content_hash) within active rows.

    Returns the resulting source_id and whether a new row was created.
    """
    source = sanitize_for_ingest(source)  # Phase 3a-2: ANSI strip + suspicious-flag for high-risk kinds
    depth = _compute_generation_depth(
        engine, source.synthesized_from, source.provenance_kind
    )
    if depth > 3:
        raise ValueError(
            f"generation_depth would be {depth} (>3); consolidate inputs before writing"
        )

    content_hash = sha256_bytes(source.content)
    uri_for_dedup = source.uri or ""  # COALESCE in the index

    with session_scope(engine) as s:
        existing = s.execute(
            text(
                "SELECT id FROM sources "
                "WHERE kind = :k AND COALESCE(uri,'') = :u AND content_hash = :h "
                "AND t_valid_to IS NULL"
            ),
            {"k": source.kind, "u": uri_for_dedup, "h": content_hash},
        ).scalar()
        if existing is not None:
            return WriteResult(
                source_id=existing, created=False, generation_depth=depth
            )

        result = s.execute(
            text(
                """
                INSERT INTO sources(
                    kind, uri, content, content_hash, mime, lang,
                    project_id, status, provenance_kind, synthesized_from,
                    generation_depth, parent_id, span_start, span_end, flags
                ) VALUES (
                    :kind, :uri, :content, :content_hash, :mime, :lang,
                    :project_id, :status, :provenance_kind, :synthesized_from,
                    :generation_depth, :parent_id, :span_start, :span_end, CAST(:flags AS jsonb)
                ) RETURNING id
                """
            ),
            {
                "kind": source.kind,
                "uri": source.uri,
                "content": source.content,
                "content_hash": content_hash,
                "mime": source.mime,
                "lang": source.lang,
                "project_id": source.project_id,
                "status": source.status,
                "provenance_kind": source.provenance_kind,
                "synthesized_from": source.synthesized_from,
                "generation_depth": depth,
                "parent_id": source.parent_id,
                "span_start": source.span_start,
                "span_end": source.span_end,
                "flags": __import__("json").dumps(source.flags),
            },
        )
        sid = result.scalar()
        assert sid is not None

        # Materialize FTS row.
        s.execute(
            text(
                "INSERT INTO sources_fts(source_id, tsv) "
                "VALUES (:s, to_tsvector('english', :content))"
            ),
            {"s": sid, "content": source.content},
        )

        # Memory classifications.
        for bucket in source.buckets:
            s.execute(
                text(
                    "INSERT INTO memory_classifications(source_id, bucket, classifier) "
                    "VALUES (:s, :b, :c) ON CONFLICT DO NOTHING"
                ),
                {"s": sid, "b": bucket, "c": source.classifier},
            )

    return WriteResult(source_id=sid, created=True, generation_depth=depth)


def invalidate(engine: Engine, source_id: int, *, reason: str) -> None:
    """Mark a source as no longer valid. Bi-temporal — row stays, t_valid_to set."""
    with session_scope(engine) as s:
        s.execute(
            text(
                "UPDATE sources SET t_valid_to = :now, invalidation_reason = :r "
                "WHERE id = :id AND t_valid_to IS NULL"
            ),
            {"now": datetime.now(timezone.utc), "r": reason, "id": source_id},
        )
