"""reasoning.compare: pairwise source comparison with typed disagreement axis."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from brain.db import get_engine
from brain.llm.client import HAIKU_MODEL_ID, HAIKU_MODEL_VER, LlmResult
from brain.reasoning.compare import CompareOutput, compare
from brain.schemas import SourceInput
from brain.write import write


def _mock_client(text: str) -> MagicMock:
    client = MagicMock()
    client.haiku.return_value = LlmResult(
        text=text,
        tokens_in=300,
        tokens_out=120,
        usd=0.0002,
        model_id=HAIKU_MODEL_ID,
        model_ver=HAIKU_MODEL_VER,
    )
    return client


def test_compare_returns_parsed_output(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="postgres uses MVCC for concurrency")).source_id
    b = write(engine, SourceInput(kind="note", content="postgres locks rows for concurrency")).source_id
    fixture = json.dumps(
        {
            "agreements": ["both about postgres concurrency"],
            "disagreements": [
                {
                    "claim_a": "MVCC",
                    "claim_b": "row locking",
                    "axis": "mechanism",
                    "source_a_span": "uses MVCC",
                    "source_b_span": "locks rows",
                }
            ],
            "scope_diff": "A: concurrency model; B: locking strategy",
            "citations": [a, b],
        }
    )
    client = _mock_client(fixture)
    out = compare(engine, a_source_id=a, b_source_id=b, llm_client=client)
    assert isinstance(out, CompareOutput)
    assert len(out.agreements) == 1
    assert len(out.disagreements) == 1
    assert out.disagreements[0]["axis"] == "mechanism"
    assert set(out.citations) == {a, b}


def test_compare_caches_second_call(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="alpha")).source_id
    b = write(engine, SourceInput(kind="note", content="beta")).source_id
    fixture = json.dumps(
        {
            "agreements": [],
            "disagreements": [],
            "scope_diff": "different topics",
            "citations": [a, b],
        }
    )
    client = _mock_client(fixture)
    compare(engine, a_source_id=a, b_source_id=b, llm_client=client)
    compare(engine, a_source_id=a, b_source_id=b, llm_client=client)
    assert client.haiku.call_count == 1


def test_compare_validates_disagreement_axis_loose(pg_url: str) -> None:
    """We accept any axis string today (no Literal validation). Document this."""
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="x")).source_id
    b = write(engine, SourceInput(kind="note", content="y")).source_id
    fixture = json.dumps(
        {
            "agreements": [],
            "disagreements": [
                {
                    "claim_a": "x",
                    "claim_b": "y",
                    "axis": "novel_axis",
                    "source_a_span": "x",
                    "source_b_span": "y",
                }
            ],
            "scope_diff": "",
            "citations": [a, b],
        }
    )
    client = _mock_client(fixture)
    out = compare(engine, a_source_id=a, b_source_id=b, llm_client=client)
    assert out.disagreements[0]["axis"] == "novel_axis"
