"""compare_prepare / compare_finalize: prompt rendering + cache + validation."""

from __future__ import annotations

import json

from brain.db import get_engine
from brain.reasoning.compare import CompareOutput, compare_finalize, compare_prepare
from brain.schemas import SourceInput
from brain.write import write


def test_prepare_emits_prompt_with_both_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="postgres uses MVCC for concurrency")).source_id
    b = write(engine, SourceInput(kind="note", content="postgres locks rows for concurrency")).source_id
    bundle = compare_prepare(engine, a_source_id=a, b_source_id=b)
    assert bundle.cached is None
    assert f"id={a}" in bundle.prompt
    assert f"id={b}" in bundle.prompt
    for field in ("agreements", "disagreements", "scope_diff", "citations"):
        assert field in bundle.schema_json["properties"]


def test_finalize_validates_and_returns_typed(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="x")).source_id
    b = write(engine, SourceInput(kind="note", content="y")).source_id
    bundle = compare_prepare(engine, a_source_id=a, b_source_id=b)
    raw = json.dumps(
        {
            "agreements": ["both nonsense"],
            "disagreements": [
                {
                    "claim_a": "x",
                    "claim_b": "y",
                    "axis": "mechanism",
                    "source_a_span": "x",
                    "source_b_span": "y",
                }
            ],
            "scope_diff": "different letters",
            "citations": [a, b],
        }
    )
    out = compare_finalize(engine, cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(out, CompareOutput)
    assert out.disagreements[0]["axis"] == "mechanism"
    assert set(out.citations) == {a, b}


def test_prepare_second_call_returns_cached(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="alpha")).source_id
    b = write(engine, SourceInput(kind="note", content="beta")).source_id
    bundle1 = compare_prepare(engine, a_source_id=a, b_source_id=b)
    raw = json.dumps(
        {
            "agreements": [],
            "disagreements": [],
            "scope_diff": "different",
            "citations": [a, b],
        }
    )
    compare_finalize(engine, cache_key=bundle1.cache_key, raw_output=raw)
    bundle2 = compare_prepare(engine, a_source_id=a, b_source_id=b)
    assert bundle2.cached is not None
    assert bundle2.cached.scope_diff == "different"
