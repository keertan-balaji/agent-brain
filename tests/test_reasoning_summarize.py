"""reasoning.summarize: cited synthesis over a set of sources."""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.db import get_engine
from brain.llm.client import HAIKU_MODEL_ID, HAIKU_MODEL_VER, LlmResult
from brain.reasoning.summarize import SummarizeOutput, summarize
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


def test_summarize_returns_parsed_output(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("postgres is open source", "postgres supports MVCC", "postgres has FTS"):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    fixture = (
        '{"summary": "Postgres is an open-source MVCC database with full-text search.", '
        f'"citations": {ids}}}'
    )
    client = _mock_client(fixture)
    out = summarize(engine, source_ids=ids, llm_client=client)
    assert isinstance(out, SummarizeOutput)
    assert "postgres" in out.summary.lower()
    assert set(out.citations) == set(ids)


def test_summarize_caches_second_call(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("alpha source", "beta source"):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    fixture = (
        '{"summary": "Alpha and beta are placeholder sources.", '
        f'"citations": {ids}}}'
    )
    client = _mock_client(fixture)
    out1 = summarize(engine, source_ids=ids, llm_client=client)
    out2 = summarize(engine, source_ids=ids, llm_client=client)
    assert out1.summary == out2.summary
    assert client.haiku.call_count == 1  # second served from cache
