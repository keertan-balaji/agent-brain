"""cite_prepare / cite_finalize: prompt rendering + cache + excerpt validation."""

from __future__ import annotations

import json

from brain.db import get_engine
from brain.reasoning.cite import CiteOutput, Support, cite_finalize, cite_prepare
from brain.schemas import SourceInput
from brain.write import write


def test_prepare_emits_prompt_with_claim_and_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    body = "Postgres supports MVCC concurrency control."
    sid = write(engine, SourceInput(kind="note", content=body)).source_id
    bundle = cite_prepare(
        engine, claim_text="postgres uses MVCC", candidate_source_ids=[sid]
    )
    assert bundle.cached is None
    assert "postgres uses MVCC" in bundle.prompt
    assert f"id={sid}" in bundle.prompt
    assert "supporting_sources" in bundle.schema_json["properties"]


def test_finalize_returns_validated_support_when_excerpt_matches(pg_url: str) -> None:
    engine = get_engine(pg_url)
    body = "Postgres supports MVCC concurrency control out of the box."
    sid = write(engine, SourceInput(kind="note", content=body)).source_id
    excerpt = "Postgres supports MVCC concurrency control"
    bundle = cite_prepare(
        engine, claim_text="postgres uses MVCC", candidate_source_ids=[sid]
    )
    raw = json.dumps(
        {
            "supporting_sources": [
                {"source_id": sid, "span_start": 0, "span_end": len(excerpt), "excerpt": excerpt}
            ]
        }
    )
    out = cite_finalize(
        engine,
        candidate_source_ids=[sid],
        cache_key=bundle.cache_key,
        raw_output=raw,
    )
    assert isinstance(out, CiteOutput)
    assert len(out.supporting_sources) == 1
    assert isinstance(out.supporting_sources[0], Support)
    assert out.supporting_sources[0].source_id == sid


def test_finalize_strips_hallucinated_excerpt(pg_url: str) -> None:
    engine = get_engine(pg_url)
    body = "Postgres supports MVCC."
    sid = write(engine, SourceInput(kind="note", content=body)).source_id
    bundle = cite_prepare(
        engine, claim_text="postgres uses MVCC", candidate_source_ids=[sid]
    )
    raw = json.dumps(
        {
            "supporting_sources": [
                {"source_id": sid, "span_start": 0, "span_end": 5, "excerpt": "FABRICATED TEXT"}
            ]
        }
    )
    out = cite_finalize(
        engine,
        candidate_source_ids=[sid],
        cache_key=bundle.cache_key,
        raw_output=raw,
    )
    assert out.supporting_sources == []


def test_prepare_second_call_returns_cached(pg_url: str) -> None:
    engine = get_engine(pg_url)
    body = "Postgres supports MVCC."
    sid = write(engine, SourceInput(kind="note", content=body)).source_id
    excerpt = "Postgres supports MVCC"
    bundle1 = cite_prepare(
        engine, claim_text="postgres uses MVCC", candidate_source_ids=[sid]
    )
    raw = json.dumps(
        {
            "supporting_sources": [
                {"source_id": sid, "span_start": 0, "span_end": len(excerpt), "excerpt": excerpt}
            ]
        }
    )
    cite_finalize(
        engine,
        candidate_source_ids=[sid],
        cache_key=bundle1.cache_key,
        raw_output=raw,
    )
    bundle2 = cite_prepare(
        engine, claim_text="postgres uses MVCC", candidate_source_ids=[sid]
    )
    assert bundle2.cached is not None
    assert bundle2.cached.supporting_sources[0].source_id == sid
