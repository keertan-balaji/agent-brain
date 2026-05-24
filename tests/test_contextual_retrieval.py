"""Contextual Retrieval: per-chunk Haiku summary prepended to chunk before embedding."""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.llm.client import HAIKU_MODEL_ID, HAIKU_MODEL_VER, LlmResult
from brain.llm.contextual import ContextualizedChunk, contextualize_chunk


def _mock_client(summary: str = "This chunk discusses postgres setup.", tokens: int = 50):
    client = MagicMock()
    client.haiku.return_value = LlmResult(
        text=summary,
        tokens_in=tokens,
        tokens_out=tokens // 2,
        usd=0.0001,
        model_id=HAIKU_MODEL_ID,
        model_ver=HAIKU_MODEL_VER,
    )
    return client


def test_returns_contextualized_chunk_dataclass():
    client = _mock_client()
    result = contextualize_chunk(client, document="full doc", chunk="snippet")
    assert isinstance(result, ContextualizedChunk)
    assert result.context_summary
    assert result.contextualized_text
    assert result.tokens_used > 0


def test_prompt_includes_document_and_chunk():
    client = _mock_client()
    doc = "the full document body"
    chunk = "the chunk snippet"
    contextualize_chunk(client, document=doc, chunk=chunk)
    call_kwargs = client.haiku.call_args.kwargs
    rendered = call_kwargs["messages"][0]["content"]
    assert doc in rendered
    assert chunk in rendered


def test_contextualized_text_is_summary_plus_chunk():
    client = _mock_client(summary="Background: this is a setup section.")
    chunk = "Run apt install postgres."
    result = contextualize_chunk(client, document="d", chunk=chunk)
    assert result.contextualized_text.startswith(result.context_summary)
    assert result.contextualized_text.endswith(chunk)


def test_tokens_used_sums_input_and_output():
    client = _mock_client(tokens=100)
    result = contextualize_chunk(client, document="d", chunk="c")
    assert result.tokens_used == 100 + 50
