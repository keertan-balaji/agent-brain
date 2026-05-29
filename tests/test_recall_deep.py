"""recall_deep — Phase 3b composition test.

The full LLM round-trips are stubbed via direct reasoning_cache seeds:
prepare() finds the cache hit immediately and returns the seeded output.
This lets us exercise the orchestration without an LLM in the loop.
"""

from __future__ import annotations

import json
import hashlib

import pytest
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.reasoning.base import cache_key_for
from brain.reasoning.multi_query import MultiQueryExpander
from brain.reasoning.self_query import QueryFilterExtractor
from brain.reasoning.crag_verify import CragVerifier
from brain.retrieval.deep import recall_deep


def _seed_reasoning_cache(engine, helper_name: str, prompt: str, prompt_ver: str, output: dict) -> None:
    """Pre-populate the cache so the GroundedHelper short-circuits at prepare()."""
    input_hash = hashlib.sha256(prompt.encode("utf-8")).digest()
    key = cache_key_for(helper_name, input_hash, prompt_ver)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO reasoning_cache(cache_key, helper_name, input_hash, prompt_ver, output_json) "
                "VALUES (:k, :n, :ih, :pv, CAST(:oj AS jsonb)) "
                "ON CONFLICT (cache_key) DO UPDATE SET output_json = EXCLUDED.output_json"
            ),
            {
                "k": key,
                "n": helper_name,
                "ih": input_hash,
                "pv": prompt_ver,
                "oj": json.dumps(output),
            },
        )


def _seed_source(engine, kind: str, content: str, uri: str) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES (:k, :c, :h, 'active', :u) RETURNING id"
            ),
            {"k": kind, "c": content, "h": h, "u": uri},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO sources_fts(source_id, tsv) VALUES (:i, to_tsvector('english', :c))"
            ),
            {"i": sid, "c": content},
        )
    return int(sid)


def test_recall_deep_calls_multi_query_and_returns_fused_hits(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid_a = _seed_source(engine, "decision", "FTS uses postgres ts_rank_cd", "decision://fts")
    sid_b = _seed_source(engine, "gotcha",   "ts_rank in postgres needs GIN", "gotcha://ts")

    # Pre-seed multi-query expansion.
    from brain.reasoning.multi_query import MultiQueryExpander
    h_mq = MultiQueryExpander(engine=engine)
    # The "prompt" the helper sees is the formatted template. We need the same
    # exact prompt to share a cache key — reach into the helper to compute it.
    bundle = h_mq.prepare("FTS in postgres")
    _seed_reasoning_cache(
        engine,
        helper_name="multi_query_expander",
        prompt=bundle.prompt,
        prompt_ver="v1",
        output={"variants": ["FTS in postgres", "ts_rank Postgres full-text search", "postgres full text query API"]},
    )

    # Pre-seed self-query extraction.
    h_sq = QueryFilterExtractor(engine=engine)
    sq_bundle = h_sq.prepare("FTS in postgres")
    _seed_reasoning_cache(
        engine,
        helper_name="query_filter_extractor",
        prompt=sq_bundle.prompt,
        prompt_ver="v1",
        output={
            "kinds": [],
            "project_hint": None,
            "buckets": [],
            "since_iso": None,
            "until_iso": None,
            "residual_query": "FTS in postgres",
        },
    )

    # Run deep recall — no CRAG seed needed because the trigger band won't fire
    # on this tiny synthetic corpus (FTS scores are tiny; below the 0.5–0.7 band).
    hits = recall_deep(engine, "FTS in postgres", k=5)
    ids = {h.id for h in hits}
    # At least one of the seeded sources should be retrieved via the expansion.
    assert sid_a in ids or sid_b in ids


def test_recall_deep_applies_self_query_kind_filter(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid_dec = _seed_source(engine, "decision", "build a docker volume", "decision://vol")
    sid_got = _seed_source(engine, "gotcha",   "docker volume permissions", "gotcha://vol")

    h_mq = MultiQueryExpander(engine=engine)
    bundle = h_mq.prepare("docker volume")
    _seed_reasoning_cache(
        engine, "multi_query_expander", bundle.prompt, "v1",
        {"variants": ["docker volume", "docker mount", "docker bind volume"]},
    )

    h_sq = QueryFilterExtractor(engine=engine)
    sq_bundle = h_sq.prepare("docker volume")
    # Self-Query restricts to kind=gotcha.
    _seed_reasoning_cache(
        engine, "query_filter_extractor", sq_bundle.prompt, "v1",
        {
            "kinds": ["gotcha"],
            "project_hint": None,
            "buckets": [],
            "since_iso": None,
            "until_iso": None,
            "residual_query": "docker volume",
        },
    )

    hits = recall_deep(engine, "docker volume", k=5)
    ids = {h.id for h in hits}
    assert sid_got in ids
    assert sid_dec not in ids


def test_recall_deep_falls_back_to_recall_on_zero_hits(pg_url: str) -> None:
    """If the deep stack returns nothing, the caller should still see an empty list, not crash."""
    engine = get_engine(pg_url)
    h_mq = MultiQueryExpander(engine=engine)
    bundle = h_mq.prepare("nothing-here-zzz")
    _seed_reasoning_cache(
        engine, "multi_query_expander", bundle.prompt, "v1",
        {"variants": ["nothing-here-zzz", "absolutely-not-there", "no-match-no-match"]},
    )
    h_sq = QueryFilterExtractor(engine=engine)
    sq_bundle = h_sq.prepare("nothing-here-zzz")
    _seed_reasoning_cache(
        engine, "query_filter_extractor", sq_bundle.prompt, "v1",
        {"kinds": [], "project_hint": None, "buckets": [], "since_iso": None, "until_iso": None, "residual_query": "nothing-here-zzz"},
    )
    hits = recall_deep(engine, "nothing-here-zzz", k=5)
    assert hits == []
