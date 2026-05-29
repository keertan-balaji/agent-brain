"""MultiQueryExpander GroundedHelper — Phase 3b."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.reasoning.multi_query import MultiQueryExpansion, MultiQueryExpander


def test_prepare_emits_prompt_and_schema(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle = h.prepare("how do hooks survive compaction")
    assert "how do hooks survive compaction" in bundle.prompt
    # The schema must declare the `variants` array field.
    assert "variants" in json.dumps(bundle.schema_json)
    assert bundle.cached is None  # first run, nothing cached


def test_finalize_persists_and_returns_validated_model(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle = h.prepare("how do hooks survive compaction")
    raw = json.dumps({
        "variants": [
            "how do hooks survive compaction",
            "claude code hooks across context window summarization",
            "session resume bundles for hook persistence",
            "compaction recovery for hook state",
        ],
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(result, MultiQueryExpansion)
    assert len(result.variants) == 4
    assert "how do hooks survive compaction" in result.variants


def test_prepare_hits_cache_on_repeat(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle1 = h.prepare("X Y Z")
    raw = json.dumps({"variants": ["X Y Z", "X with Y", "Z near X"]})
    h.finalize(cache_key=bundle1.cache_key, raw_output=raw)
    bundle2 = h.prepare("X Y Z")
    assert bundle2.cached is not None
    assert bundle2.cached.variants == ["X Y Z", "X with Y", "Z near X"]


def test_validates_min_variant_count(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle = h.prepare("Q")
    # spec: 3–5 variants. Schema enforces min 3.
    bad = json.dumps({"variants": ["only one"]})
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=bad)
