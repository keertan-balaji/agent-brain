from brain.db import get_engine
from brain.schemas import SourceInput
from brain.write import write


def test_dedup_hits_when_same_kind_uri_content(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://a", content="same body"))
    second = write(engine, SourceInput(kind="note", uri="x://a", content="same body"))
    assert second.source_id == first.source_id
    assert second.created is False


def test_dedup_misses_when_different_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://b", content="text"))
    second = write(engine, SourceInput(kind="decision", uri="x://b", content="text"))
    assert second.source_id != first.source_id
    assert second.created is True


def test_dedup_misses_when_different_uri(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://c1", content="body3"))
    second = write(engine, SourceInput(kind="note", uri="x://c2", content="body3"))
    assert second.source_id != first.source_id
