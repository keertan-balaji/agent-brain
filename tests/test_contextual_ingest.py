"""Heuristic contextual ingest for multi-chunk sources (v0.8.4)."""

from __future__ import annotations

from dataclasses import dataclass

from brain.ingest import _nearest_markdown_header, heuristic_contexts


@dataclass
class _FakeChunk:
    span_start: int


def test_nearest_markdown_header_finds_h1() -> None:
    content = "# Top header\n\nSome content here\nMore text"
    header = _nearest_markdown_header(content, span_start=len(content) - 5)
    assert header == "Top header"


def test_nearest_markdown_header_finds_nearest_h2() -> None:
    content = (
        "# Top header\n"
        "\n"
        "## Section A\n"
        "Body of section A\n"
        "## Section B\n"
        "Body of section B that the chunk lands inside"
    )
    span_start = content.index("Body of section B")
    assert _nearest_markdown_header(content, span_start) == "Section B"


def test_nearest_markdown_header_none_at_start() -> None:
    content = "no headers in this content"
    assert _nearest_markdown_header(content, span_start=5) is None


def test_nearest_markdown_header_caps_long_headers() -> None:
    long_title = "X" * 200
    content = f"# {long_title}\n\nbody"
    header = _nearest_markdown_header(content, span_start=len(content) - 1)
    assert header is not None
    assert len(header) <= 120


def test_heuristic_contexts_includes_source_tag_for_every_chunk() -> None:
    content = "## A\nbody-a\n## B\nbody-b"
    chunks = [_FakeChunk(span_start=content.index("body-a"))]
    ctxs = heuristic_contexts(
        content, chunks, parent_kind="note", parent_uri="note://example"
    )
    assert len(ctxs) == 1
    assert "[From note at note://example]" in ctxs[0]


def test_heuristic_contexts_includes_section_when_inside_md() -> None:
    content = "# Title\n\n## Section X\nBody of section X"
    chunks = [_FakeChunk(span_start=content.index("Body"))]
    ctxs = heuristic_contexts(
        content, chunks, parent_kind="note", parent_uri="note://example"
    )
    assert "[Section: Section X]" in ctxs[0]


def test_heuristic_contexts_omits_section_when_no_header_preceding() -> None:
    content = "Just plain text\nMore plain text"
    chunks = [_FakeChunk(span_start=5)]
    ctxs = heuristic_contexts(
        content, chunks, parent_kind="note", parent_uri=None
    )
    assert "[From note]" in ctxs[0]
    assert "[Section:" not in ctxs[0]


def test_heuristic_contexts_one_per_chunk() -> None:
    content = "## A\nbody-a\n## B\nbody-b\n## C\nbody-c"
    chunks = [
        _FakeChunk(span_start=content.index("body-a")),
        _FakeChunk(span_start=content.index("body-b")),
        _FakeChunk(span_start=content.index("body-c")),
    ]
    ctxs = heuristic_contexts(
        content, chunks, parent_kind="note", parent_uri="note://multi"
    )
    assert len(ctxs) == 3
    assert "[Section: A]" in ctxs[0]
    assert "[Section: B]" in ctxs[1]
    assert "[Section: C]" in ctxs[2]
