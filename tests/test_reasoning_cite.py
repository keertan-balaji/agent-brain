"""reasoning.cite: span-grounded claim support with verbatim entailment check."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from brain.db import get_engine
from brain.llm.client import HAIKU_MODEL_ID, HAIKU_MODEL_VER, LlmResult
from brain.reasoning.cite import CiteOutput, Support, cite
from brain.schemas import SourceInput
from brain.write import write


def _mock_client(text: str) -> MagicMock:
    client = MagicMock()
    client.haiku.return_value = LlmResult(
        text=text,
        tokens_in=200,
        tokens_out=80,
        usd=0.0001,
        model_id=HAIKU_MODEL_ID,
        model_ver=HAIKU_MODEL_VER,
    )
    return client


def test_cite_returns_validated_support(pg_url: str) -> None:
    engine = get_engine(pg_url)
    body = "Postgres supports MVCC concurrency control out of the box."
    sid = write(engine, SourceInput(kind="note", content=body)).source_id
    excerpt = "Postgres supports MVCC concurrency control"
    fixture = json.dumps(
        {
            "supporting_sources": [
                {"source_id": sid, "span_start": 0, "span_end": len(excerpt), "excerpt": excerpt},
            ]
        }
    )
    client = _mock_client(fixture)
    out = cite(
        engine,
        claim_text="postgres uses MVCC",
        candidate_source_ids=[sid],
        llm_client=client,
    )
    assert isinstance(out, CiteOutput)
    assert len(out.supporting_sources) == 1
    assert isinstance(out.supporting_sources[0], Support)
    assert out.supporting_sources[0].source_id == sid


def test_cite_rejects_excerpt_not_in_source(pg_url: str) -> None:
    engine = get_engine(pg_url)
    body = "Postgres supports MVCC."
    sid = write(engine, SourceInput(kind="note", content=body)).source_id
    fixture = json.dumps(
        {
            "supporting_sources": [
                {"source_id": sid, "span_start": 0, "span_end": 5, "excerpt": "FABRICATED TEXT"},
            ]
        }
    )
    client = _mock_client(fixture)
    out = cite(
        engine,
        claim_text="postgres uses MVCC",
        candidate_source_ids=[sid],
        llm_client=client,
    )
    assert out.supporting_sources == []


def test_cite_returns_empty_when_no_support(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = write(engine, SourceInput(kind="note", content="totally unrelated content")).source_id
    fixture = json.dumps({"supporting_sources": []})
    client = _mock_client(fixture)
    out = cite(
        engine,
        claim_text="postgres uses MVCC",
        candidate_source_ids=[sid],
        llm_client=client,
    )
    assert out.supporting_sources == []
