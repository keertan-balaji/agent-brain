from brain.db import get_engine
from brain.schemas import SourceInput
from brain.write import write


def test_write_returns_source_id_and_created(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="hello brain"))
    assert res.source_id > 0
    assert res.created is True
    assert res.generation_depth == 0


def test_write_classifies_bucket_when_given(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(
        engine,
        SourceInput(kind="decision", content="use postgres", buckets=["semantic", "episodic"]),
    )
    from sqlalchemy import text

    from brain.db import session_scope

    with session_scope(engine) as s:
        buckets = sorted(
            row[0]
            for row in s.execute(
                text("SELECT bucket FROM memory_classifications WHERE source_id = :s"),
                {"s": res.source_id},
            ).fetchall()
        )
    assert buckets == ["episodic", "semantic"]


def test_write_populates_fts(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="postgres pgvector hybrid"))
    from sqlalchemy import text

    from brain.db import session_scope

    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT 1 FROM sources_fts WHERE source_id = :s "
                "AND tsv @@ to_tsquery('english', 'postgres & pgvector')"
            ),
            {"s": res.source_id},
        ).scalar()
    assert row == 1
