from brain.db import get_engine
from brain.read import recall
from brain.schemas import SourceInput
from brain.write import write


def test_recall_returns_fts_hits(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="alpha beta gamma"))
    write(engine, SourceInput(kind="note", content="delta epsilon zeta"))
    write(engine, SourceInput(kind="note", content="alpha epsilon"))
    hits = recall(engine, "alpha", k=10)
    contents = {h.content for h in hits}
    assert "alpha beta gamma" in contents
    assert "alpha epsilon" in contents
    assert "delta epsilon zeta" not in contents


def test_recall_ranks_by_relevance(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="postgres"))
    write(engine, SourceInput(kind="note", content="postgres postgres postgres pgvector"))
    hits = recall(engine, "postgres pgvector", k=5)
    assert hits[0].content.startswith("postgres postgres")


def test_recall_returns_at_most_k(pg_url: str) -> None:
    engine = get_engine(pg_url)
    for i in range(10):
        write(engine, SourceInput(kind="note", content=f"alpha {i}"))
    hits = recall(engine, "alpha", k=3)
    assert len(hits) == 3
