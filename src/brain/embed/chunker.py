"""Parent-document chunker.

Splits a source document into sentence-aligned child windows of <= child_max_tokens
tokens, each paired with a larger parent window of <= parent_max_tokens tokens
centered on the child. Children carry the embedding signal; parents are returned
verbatim to the LLM at recall time.

Token counts use tiktoken's cl100k_base encoding — a close approximation to
Claude/GPT tokenizers (within ~5% on English/code).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    child_text: str
    parent_text: str
    child_token_count: int
    parent_token_count: int
    span_start: int
    span_end: int


def _count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _split_sentences(text: str) -> List[str]:
    try:
        import nltk
        return nltk.sent_tokenize(text)
    except (LookupError, ImportError):
        return [s for s in text.split("\n") if s.strip()]


def _sentence_spans(text: str, sentences: List[str]) -> List[tuple[int, int]]:
    """Locate each sentence's char span in the original text via sequential search."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for s in sentences:
        idx = text.find(s, cursor)
        if idx < 0:
            idx = cursor
        spans.append((idx, idx + len(s)))
        cursor = idx + len(s)
    return spans


def chunk_document(
    text: str,
    *,
    child_max_tokens: int,
    parent_max_tokens: int,
) -> List[Chunk]:
    """Split text into (child, parent) chunk pairs.

    Algorithm:
    1. If whole doc fits in child_max_tokens, emit one chunk where child == parent.
    2. Sentence-tokenize, compute char spans.
    3. Greedy-pack sentences into children up to child_max_tokens.
    4. For each child, expand outward symmetrically (sentence-by-sentence) into a
       parent window up to parent_max_tokens.
    """
    if not text.strip():
        return []

    total_tokens = _count_tokens(text)
    if total_tokens <= child_max_tokens:
        return [
            Chunk(
                child_text=text,
                parent_text=text,
                child_token_count=total_tokens,
                parent_token_count=total_tokens,
                span_start=0,
                span_end=len(text),
            )
        ]

    sentences = _split_sentences(text)
    if not sentences:
        return []
    spans = _sentence_spans(text, sentences)
    sent_tokens = [_count_tokens(s) for s in sentences]

    # Greedy pack child windows
    children: list[tuple[int, int]] = []  # (start_idx, end_idx) inclusive over sentences
    i = 0
    while i < len(sentences):
        j = i
        running = 0
        while j < len(sentences) and running + sent_tokens[j] <= child_max_tokens:
            running += sent_tokens[j]
            j += 1
        if j == i:  # single sentence exceeds child_max_tokens — still take it alone
            j = i + 1
        children.append((i, j - 1))
        i = j

    chunks: list[Chunk] = []
    for c_start, c_end in children:
        child_tokens = sum(sent_tokens[c_start : c_end + 1])
        # expand outward symmetrically to build parent window
        p_start, p_end = c_start, c_end
        parent_tokens = child_tokens
        toggle_left = True
        while True:
            grew = False
            if toggle_left and p_start > 0 and parent_tokens + sent_tokens[p_start - 1] <= parent_max_tokens:
                p_start -= 1
                parent_tokens += sent_tokens[p_start]
                grew = True
            elif not toggle_left and p_end < len(sentences) - 1 and parent_tokens + sent_tokens[p_end + 1] <= parent_max_tokens:
                p_end += 1
                parent_tokens += sent_tokens[p_end]
                grew = True
            else:
                # try the other side
                if toggle_left and p_end < len(sentences) - 1 and parent_tokens + sent_tokens[p_end + 1] <= parent_max_tokens:
                    p_end += 1
                    parent_tokens += sent_tokens[p_end]
                    grew = True
                elif not toggle_left and p_start > 0 and parent_tokens + sent_tokens[p_start - 1] <= parent_max_tokens:
                    p_start -= 1
                    parent_tokens += sent_tokens[p_start]
                    grew = True
            toggle_left = not toggle_left
            if not grew:
                break

        child_span_start = spans[c_start][0]
        child_span_end = spans[c_end][1]
        parent_span_start = spans[p_start][0]
        parent_span_end = spans[p_end][1]
        chunks.append(
            Chunk(
                child_text=text[child_span_start:child_span_end],
                parent_text=text[parent_span_start:parent_span_end],
                child_token_count=child_tokens,
                parent_token_count=parent_tokens,
                span_start=child_span_start,
                span_end=child_span_end,
            )
        )
    return chunks
