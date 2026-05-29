"""QueryFilterExtractor GroundedHelper — Phase 3b Self-Query."""

from __future__ import annotations

import json

import pytest

from brain.db import get_engine
from brain.reasoning.self_query import (
    QueryFilterExtractor,
    QueryFilters,
)


def test_prepare_emits_prompt_and_schema(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("what decisions did we make last week in the brain project")
    assert "last week" in bundle.prompt
    assert "kinds" in json.dumps(bundle.schema_json)
    assert "since_iso" in json.dumps(bundle.schema_json)


def test_finalize_returns_validated_filters(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("recent gotchas about hooks")
    raw = json.dumps({
        "kinds": ["gotcha"],
        "project_hint": None,
        "buckets": [],
        "since_iso": "2026-05-22T00:00:00Z",
        "until_iso": None,
        "residual_query": "hooks",
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(result, QueryFilters)
    assert result.kinds == ["gotcha"]
    assert result.residual_query == "hooks"
    assert result.since_iso == "2026-05-22T00:00:00Z"


def test_empty_filters_are_valid(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("Q")
    raw = json.dumps({
        "kinds": [],
        "project_hint": None,
        "buckets": [],
        "since_iso": None,
        "until_iso": None,
        "residual_query": "Q",
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert result.kinds == []
    assert result.residual_query == "Q"


def test_residual_query_required(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("Q")
    raw = json.dumps({
        "kinds": [],
        "project_hint": None,
        "buckets": [],
        "since_iso": None,
        "until_iso": None,
        # residual_query missing
    })
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=raw)
