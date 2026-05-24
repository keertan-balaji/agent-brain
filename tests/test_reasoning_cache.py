"""reasoning_cache + GroundedHelper contract (cache, retry, validate)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.reasoning.base import GroundedHelper, cache_key_for


class _Out(BaseModel):
    answer: str


def test_cache_key_is_deterministic() -> None:
    a = cache_key_for("summarize", b"\x00" * 32, "haiku", "v1", "p1")
    b = cache_key_for("summarize", b"\x00" * 32, "haiku", "v1", "p1")
    assert a == b
    assert len(a) == 32


def test_cache_key_differs_on_input() -> None:
    base = cache_key_for("summarize", b"\x00" * 32, "haiku", "v1", "p1")
    assert cache_key_for("compare", b"\x00" * 32, "haiku", "v1", "p1") != base
    assert cache_key_for("summarize", b"\x01" * 32, "haiku", "v1", "p1") != base
    assert cache_key_for("summarize", b"\x00" * 32, "sonnet", "v1", "p1") != base
    assert cache_key_for("summarize", b"\x00" * 32, "haiku", "v2", "p1") != base
    assert cache_key_for("summarize", b"\x00" * 32, "haiku", "v1", "p2") != base


def test_grounded_helper_caches_second_call(pg_url: str) -> None:
    engine = get_engine(pg_url)
    llm_fn = MagicMock(return_value='{"answer": "42"}')
    helper = GroundedHelper(
        engine=engine,
        name="testhelper",
        prompt_ver="v1",
        output_schema=_Out,
        llm_fn=llm_fn,
        llm_model_id="haiku",
        llm_model_ver="2025-10-01",
    )
    first = helper.run("the prompt")
    second = helper.run("the prompt")
    assert first.answer == "42"
    assert second.answer == "42"
    assert llm_fn.call_count == 1  # second served from cache

    # hit_count bumped
    with session_scope(engine) as s:
        rows = s.execute(
            text("SELECT hit_count FROM reasoning_cache WHERE helper_name = 'testhelper'")
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] >= 2


def test_grounded_helper_retries_on_invalid_json(pg_url: str) -> None:
    engine = get_engine(pg_url)
    llm_fn = MagicMock(side_effect=["not json", "still bad", '{"answer": "ok"}'])
    helper = GroundedHelper(
        engine=engine,
        name="retry_helper",
        prompt_ver="v1",
        output_schema=_Out,
        llm_fn=llm_fn,
        llm_model_id="haiku",
        llm_model_ver="2025-10-01",
    )
    out = helper.run("try me")
    assert out.answer == "ok"
    assert llm_fn.call_count == 3


def test_grounded_helper_raises_after_max_retries(pg_url: str) -> None:
    engine = get_engine(pg_url)
    llm_fn = MagicMock(return_value="not json ever")
    helper = GroundedHelper(
        engine=engine,
        name="fail_helper",
        prompt_ver="v1",
        output_schema=_Out,
        llm_fn=llm_fn,
        llm_model_id="haiku",
        llm_model_ver="2025-10-01",
    )
    with pytest.raises(RuntimeError):
        helper.run("doomed")
    assert llm_fn.call_count == 3  # MAX_RETRIES
