"""CragVerifier GroundedHelper — Phase 3b."""

from __future__ import annotations

import json

import pytest

from brain.db import get_engine
from brain.reasoning.crag_verify import (
    CragVerdict,
    CragVerification,
    CragVerifier,
)


def test_prepare_emits_prompt_and_schema(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    candidates = [
        {"id": 1, "kind": "decision", "content": "use postgres for FTS"},
        {"id": 2, "kind": "gotcha",   "content": "psql -d brain fails in docker"},
    ]
    bundle = h.prepare(query="how do we run FTS", candidates=candidates)
    assert "how do we run FTS" in bundle.prompt
    assert "use postgres for FTS" in bundle.prompt
    assert "verdicts" in json.dumps(bundle.schema_json)


def test_finalize_returns_three_way_verdicts(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    candidates = [
        {"id": 1, "kind": "decision", "content": "use postgres for FTS"},
        {"id": 2, "kind": "gotcha",   "content": "psql -d brain fails in docker"},
        {"id": 3, "kind": "note",     "content": "favorite color is blue"},
    ]
    bundle = h.prepare(query="how do we run FTS", candidates=candidates)
    raw = json.dumps({
        "verdicts": [
            {"source_id": 1, "score": 0.92, "verdict": "keep",    "reason": "directly answers"},
            {"source_id": 2, "score": 0.55, "verdict": "merge",   "reason": "tangential but useful"},
            {"source_id": 3, "score": 0.05, "verdict": "discard", "reason": "irrelevant"},
        ]
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(result, CragVerification)
    assert len(result.verdicts) == 3
    assert result.verdicts[0].verdict == CragVerdict.KEEP
    assert result.verdicts[1].verdict == CragVerdict.MERGE
    assert result.verdicts[2].verdict == CragVerdict.DISCARD


def test_score_must_be_in_unit_interval(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    bundle = h.prepare(query="Q", candidates=[{"id": 1, "kind": "note", "content": "X"}])
    raw = json.dumps({
        "verdicts": [
            {"source_id": 1, "score": 1.7, "verdict": "keep", "reason": "ok"},  # invalid score
        ]
    })
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=raw)


def test_verdict_enum_enforced(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    bundle = h.prepare(query="Q", candidates=[{"id": 1, "kind": "note", "content": "X"}])
    raw = json.dumps({
        "verdicts": [
            {"source_id": 1, "score": 0.5, "verdict": "maybe", "reason": "ok"},
        ]
    })
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=raw)
