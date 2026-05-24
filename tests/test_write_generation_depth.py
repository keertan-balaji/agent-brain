import pytest

from brain.db import get_engine
from brain.schemas import SourceInput
from brain.write import write


def test_captured_source_has_depth_zero(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="captured"))
    assert res.generation_depth == 0


def test_synthesized_from_captured_has_depth_one(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="src1"))
    b = write(engine, SourceInput(kind="note", content="src2"))
    syn = write(
        engine,
        SourceInput(
            kind="faq",
            content="answer derived from src1+src2",
            provenance_kind="synthesized",
            synthesized_from=[a.source_id, b.source_id],
        ),
    )
    assert syn.generation_depth == 1


def test_synthesized_from_synthesized_has_depth_two(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="raw"))
    d1 = write(
        engine,
        SourceInput(
            kind="faq",
            content="depth 1",
            provenance_kind="synthesized",
            synthesized_from=[a.source_id],
        ),
    )
    d2 = write(
        engine,
        SourceInput(
            kind="faq",
            content="depth 2",
            provenance_kind="synthesized",
            synthesized_from=[d1.source_id],
        ),
    )
    assert d1.generation_depth == 1
    assert d2.generation_depth == 2


def test_depth_three_is_max_and_depth_four_rejected(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(engine, SourceInput(kind="note", content="root"))
    d1 = write(
        engine,
        SourceInput(
            kind="faq", content="d1", provenance_kind="synthesized", synthesized_from=[a.source_id]
        ),
    )
    d2 = write(
        engine,
        SourceInput(
            kind="faq", content="d2", provenance_kind="synthesized", synthesized_from=[d1.source_id]
        ),
    )
    d3 = write(
        engine,
        SourceInput(
            kind="faq", content="d3", provenance_kind="synthesized", synthesized_from=[d2.source_id]
        ),
    )
    assert d3.generation_depth == 3
    with pytest.raises(ValueError, match="generation_depth"):
        write(
            engine,
            SourceInput(
                kind="faq",
                content="d4 too deep",
                provenance_kind="synthesized",
                synthesized_from=[d3.source_id],
            ),
        )
