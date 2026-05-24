"""summarize_prepare / summarize_finalize: prompt rendering + cache + validation."""

from __future__ import annotations

import json

from brain.db import get_engine
from brain.reasoning.summarize import SummarizeOutput, summarize_finalize, summarize_prepare
from brain.schemas import SourceInput
from brain.write import write


def test_prepare_emits_prompt_with_source_markers(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("alpha source", "beta source"):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    bundle = summarize_prepare(engine, source_ids=ids)
    assert bundle.cached is None
    for sid in ids:
        assert f"[id={sid}]" in bundle.prompt
    assert "summary" in bundle.schema_json["properties"]
    assert "citations" in bundle.schema_json["properties"]


def test_finalize_validates_and_returns_typed(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("postgres is open source",):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    bundle = summarize_prepare(engine, source_ids=ids)
    raw = json.dumps({"summary": "postgres summary", "citations": ids})
    out = summarize_finalize(engine, cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(out, SummarizeOutput)
    assert out.summary == "postgres summary"
    assert out.citations == ids


def test_prepare_second_call_returns_cached(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("alpha", "beta"):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    bundle1 = summarize_prepare(engine, source_ids=ids)
    raw = json.dumps({"summary": "alpha and beta", "citations": ids})
    summarize_finalize(engine, cache_key=bundle1.cache_key, raw_output=raw)
    bundle2 = summarize_prepare(engine, source_ids=ids)
    assert bundle2.cached is not None
    assert bundle2.cached.summary == "alpha and beta"
