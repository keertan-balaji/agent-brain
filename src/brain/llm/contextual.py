"""Contextual Retrieval (Anthropic): prepend a per-chunk doc-aware summary
before embedding to improve retrieval. See:
https://www.anthropic.com/news/contextual-retrieval
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from brain.llm.client import AnthropicClient, LlmResult

_PROMPT_PATH = Path(__file__).parent / "prompts" / "chunk_context.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()

_SYSTEM = (
    "You produce short, search-friendly context summaries to situate chunks "
    "within their parent documents. Answer only with the summary text."
)


@dataclass
class ContextualizedChunk:
    context_summary: str
    contextualized_text: str
    tokens_used: int


def contextualize_chunk(
    client: AnthropicClient,
    *,
    document: str,
    chunk: str,
    max_tokens: int = 256,
) -> ContextualizedChunk:
    rendered = _PROMPT_TEMPLATE.format(document=document, chunk=chunk)
    result: LlmResult = client.haiku(
        system=_SYSTEM,
        messages=[{"role": "user", "content": rendered}],
        max_tokens=max_tokens,
        temperature=0.0,
    )
    summary = result.text.strip()
    contextualized = f"{summary}\n\n{chunk}"
    return ContextualizedChunk(
        context_summary=summary,
        contextualized_text=contextualized,
        tokens_used=result.tokens_in + result.tokens_out,
    )
