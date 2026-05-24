"""Parent-document chunker: child windows packed sentence-wise into parents."""

from brain.embed.chunker import chunk_document


def _make_text(n_sentences: int) -> str:
    return ". ".join(f"This is sentence number {i}" for i in range(n_sentences)) + "."


def test_short_text_produces_one_chunk() -> None:
    chunks = chunk_document("hello world", child_max_tokens=256, parent_max_tokens=1024)
    assert len(chunks) == 1


def test_long_text_produces_multiple_children() -> None:
    text = _make_text(200)
    chunks = chunk_document(text, child_max_tokens=128, parent_max_tokens=512)
    assert len(chunks) > 1
    for c in chunks:
        assert c.child_token_count <= 128 * 1.1


def test_parent_is_larger_than_child() -> None:
    text = _make_text(100)
    chunks = chunk_document(text, child_max_tokens=64, parent_max_tokens=256)
    for c in chunks:
        assert c.parent_token_count >= c.child_token_count


def test_spans_cover_source_without_overlap() -> None:
    text = _make_text(50)
    chunks = chunk_document(text, child_max_tokens=64, parent_max_tokens=256)
    for i in range(len(chunks) - 1):
        assert chunks[i].span_end <= chunks[i + 1].span_start


def test_chunk_returns_dataclass_with_required_fields() -> None:
    chunks = chunk_document("test text", child_max_tokens=256, parent_max_tokens=1024)
    c = chunks[0]
    for attr in ("child_text", "parent_text", "child_token_count", "parent_token_count", "span_start", "span_end"):
        assert hasattr(c, attr)
