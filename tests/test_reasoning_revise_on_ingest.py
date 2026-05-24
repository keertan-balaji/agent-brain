"""revise_prepare / revise_finalize: A-MEM neighbor-rewrite plan, agent-driven."""

from __future__ import annotations

import json

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.reasoning.revise_on_ingest import (
    ClaimUpdate,
    Contradiction,
    RevisionPlan,
    revise_finalize,
    revise_prepare,
)
from brain.schemas import SourceInput
from brain.write import write


def _insert_claim(engine, source_id, subject, predicate, obj, conf=0.9):
    with session_scope(engine) as s:
        return s.execute(
            text(
                """
                INSERT INTO extracted_claims(
                    source_id, subject, predicate, object,
                    evidence_span_start, evidence_span_end, confidence, extracted_by_model
                ) VALUES (:sid, :s, :p, :o, 0, 10, :c, 'test')
                RETURNING id
                """
            ),
            {"sid": source_id, "s": subject, "p": predicate, "o": obj, "c": conf},
        ).scalar()


def test_prepare_emits_prompt_with_new_source_and_neighbor_claims(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    old = write(engine, SourceInput(kind="note", content="postgres uses row locks")).source_id
    new = write(engine, SourceInput(kind="note", content="postgres uses MVCC")).source_id
    ingest_source(engine, source_id=old, embedder=bge_m3_embedder)
    ingest_source(engine, source_id=new, embedder=bge_m3_embedder)
    claim_id = _insert_claim(engine, old, "postgres", "uses", "row locks")

    bundle = revise_prepare(engine, new_source_id=new, embedder=bge_m3_embedder)
    assert bundle.cached is None
    assert "postgres uses MVCC" in bundle.prompt
    assert f"claim_id={claim_id}" in bundle.prompt or str(claim_id) in bundle.prompt
    for field in ("updates", "contradictions", "affected_pages"):
        assert field in bundle.schema_json["properties"]


def test_finalize_validates_and_returns_typed(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    new = write(engine, SourceInput(kind="note", content="postgres uses MVCC")).source_id
    ingest_source(engine, source_id=new, embedder=bge_m3_embedder)
    bundle = revise_prepare(engine, new_source_id=new, embedder=bge_m3_embedder)
    raw = json.dumps(
        {
            "updates": [
                {
                    "claim_id": None,
                    "action": "create",
                    "new_subject": "postgres",
                    "new_predicate": "uses",
                    "new_object": "MVCC",
                }
            ],
            "contradictions": [],
            "affected_pages": [new],
        }
    )
    plan = revise_finalize(engine, cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(plan, RevisionPlan)
    assert isinstance(plan.updates[0], ClaimUpdate)
    assert plan.updates[0].action == "create"
    assert plan.affected_pages == [new]


def test_finalize_does_not_mutate_sources_or_claims(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    new = write(engine, SourceInput(kind="note", content="some content")).source_id
    ingest_source(engine, source_id=new, embedder=bge_m3_embedder)
    bundle = revise_prepare(engine, new_source_id=new, embedder=bge_m3_embedder)
    raw = json.dumps(
        {
            "updates": [
                {"claim_id": None, "action": "create", "new_subject": "x", "new_predicate": "y", "new_object": "z"}
            ],
            "contradictions": [],
            "affected_pages": [new],
        }
    )
    revise_finalize(engine, cache_key=bundle.cache_key, raw_output=raw)
    with session_scope(engine) as s:
        content = s.execute(text("SELECT content FROM sources WHERE id = :i"), {"i": new}).scalar()
    assert content == "some content"
    with session_scope(engine) as s:
        n_claims = s.execute(
            text("SELECT COUNT(*) FROM extracted_claims WHERE source_id = :i"), {"i": new}
        ).scalar()
    assert n_claims == 0
