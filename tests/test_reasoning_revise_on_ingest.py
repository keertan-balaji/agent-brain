"""reasoning.revise_on_ingest: A-MEM-style plan for claim mutations + contradictions."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.llm.client import HAIKU_MODEL_ID, HAIKU_MODEL_VER, LlmResult
from brain.reasoning.revise_on_ingest import (
    ClaimUpdate,
    Contradiction,
    RevisionPlan,
    revise_on_ingest,
)
from brain.schemas import SourceInput
from brain.write import write


def _mock_client(text_out: str) -> MagicMock:
    client = MagicMock()
    client.haiku.return_value = LlmResult(
        text=text_out,
        tokens_in=200,
        tokens_out=80,
        usd=0.0001,
        model_id=HAIKU_MODEL_ID,
        model_ver=HAIKU_MODEL_VER,
    )
    return client


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


def test_revise_returns_revision_plan(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    old = write(engine, SourceInput(kind="note", content="postgres uses row locks for concurrency")).source_id
    new = write(engine, SourceInput(kind="note", content="postgres uses MVCC for concurrency control")).source_id
    ingest_source(engine, source_id=old, embedder=bge_m3_embedder)
    ingest_source(engine, source_id=new, embedder=bge_m3_embedder)
    claim_id = _insert_claim(engine, old, "postgres", "uses", "row locks")

    fixture = json.dumps(
        {
            "updates": [
                {"claim_id": claim_id, "action": "invalidate", "new_subject": "", "new_predicate": "", "new_object": ""},
                {"claim_id": None, "action": "create", "new_subject": "postgres", "new_predicate": "uses", "new_object": "MVCC"},
            ],
            "contradictions": [
                {"claim_a_id": claim_id, "claim_b_id": claim_id, "reason": "self-test"}
            ],
            "affected_pages": [old, new],
        }
    )
    client = _mock_client(fixture)
    plan = revise_on_ingest(engine, new_source_id=new, embedder=bge_m3_embedder, llm_client=client)
    assert isinstance(plan, RevisionPlan)
    assert len(plan.updates) == 2
    assert isinstance(plan.updates[0], ClaimUpdate)
    assert plan.updates[0].action == "invalidate"
    assert plan.updates[1].action == "create"
    assert isinstance(plan.contradictions[0], Contradiction)
    assert set(plan.affected_pages) >= {old, new}


def test_revise_does_not_mutate_sources(pg_url: str, bge_m3_embedder: BgeM3Embedder) -> None:
    engine = get_engine(pg_url)
    new = write(engine, SourceInput(kind="note", content="some content")).source_id
    ingest_source(engine, source_id=new, embedder=bge_m3_embedder)
    fixture = json.dumps(
        {
            "updates": [
                {"claim_id": None, "action": "create", "new_subject": "x", "new_predicate": "y", "new_object": "z"}
            ],
            "contradictions": [],
            "affected_pages": [new],
        }
    )
    client = _mock_client(fixture)
    revise_on_ingest(engine, new_source_id=new, embedder=bge_m3_embedder, llm_client=client)
    # source content untouched
    with session_scope(engine) as s:
        content = s.execute(text("SELECT content FROM sources WHERE id = :i"), {"i": new}).scalar()
    assert content == "some content"
    # no claim rows inserted (helper only proposes)
    with session_scope(engine) as s:
        n = s.execute(text("SELECT COUNT(*) FROM extracted_claims WHERE source_id = :i"), {"i": new}).scalar()
    assert n == 0
