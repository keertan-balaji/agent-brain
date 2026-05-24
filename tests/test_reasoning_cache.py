"""GroundedHelper: prepare / finalize / cache via sha256(name+input+prompt_ver)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.reasoning.base import GroundedHelper, PromptBundle, cache_key_for


class _Out(BaseModel):
    answer: str


def test_cache_key_is_deterministic_three_field() -> None:
    a = cache_key_for("summarize", b"\x00" * 32, "v1")
    b = cache_key_for("summarize", b"\x00" * 32, "v1")
    assert a == b
    assert len(a) == 32


def test_cache_key_differs_on_input() -> None:
    base = cache_key_for("summarize", b"\x00" * 32, "v1")
    assert cache_key_for("compare", b"\x00" * 32, "v1") != base
    assert cache_key_for("summarize", b"\x01" * 32, "v1") != base
    assert cache_key_for("summarize", b"\x00" * 32, "v2") != base


def test_prepare_returns_bundle_with_no_cache(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t1", prompt_ver="v1", output_schema=_Out
    )
    bundle = helper.prepare("hello prompt")
    assert isinstance(bundle, PromptBundle)
    assert bundle.cached is None
    assert bundle.prompt == "hello prompt"
    assert "answer" in bundle.schema_json["properties"]
    assert bundle.cache_key_hex == bundle.cache_key.hex()


def test_finalize_validates_and_persists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t2", prompt_ver="v1", output_schema=_Out
    )
    bundle = helper.prepare("prompt-a")
    out = helper.finalize(cache_key=bundle.cache_key, raw_output='{"answer":"42"}')
    assert out.answer == "42"
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT helper_name, hit_count FROM reasoning_cache WHERE cache_key = :k"),
            {"k": bundle.cache_key},
        ).one()
    assert row[0] == "t2"
    assert row[1] == 1


def test_prepare_second_call_returns_cached(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t3", prompt_ver="v1", output_schema=_Out
    )
    bundle1 = helper.prepare("prompt-b")
    helper.finalize(cache_key=bundle1.cache_key, raw_output='{"answer":"cached-value"}')
    bundle2 = helper.prepare("prompt-b")
    assert bundle2.cached is not None
    assert bundle2.cached.answer == "cached-value"
    with session_scope(engine) as s:
        n = s.execute(
            text("SELECT hit_count FROM reasoning_cache WHERE cache_key = :k"),
            {"k": bundle2.cache_key},
        ).scalar()
    assert n >= 2


def test_finalize_raises_on_invalid_json(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t4", prompt_ver="v1", output_schema=_Out
    )
    bundle = helper.prepare("prompt-c")
    with pytest.raises(Exception):
        helper.finalize(cache_key=bundle.cache_key, raw_output="not json")
