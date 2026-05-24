from brain.db import get_engine, session_scope
from brain.read import recall
from brain.schemas import SourceInput
from brain.write import invalidate, write
from sqlalchemy import text


def test_pre_filter_excludes_invalidated(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", content="findme prefilter1"))
    invalidate(engine, res.source_id, reason="testing")
    hits = recall(engine, "findme prefilter1", k=10)
    assert all(h.id != res.source_id for h in hits)


def test_pre_filter_excludes_archived(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(
        engine, SourceInput(kind="note", content="findme arch", status="archived")
    )
    hits = recall(engine, "findme arch", k=10)
    assert all(h.id != res.source_id for h in hits)


def test_pre_filter_by_project(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        p1 = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('proj-a','development') RETURNING id")
        ).scalar()
        p2 = s.execute(
            text("INSERT INTO projects(slug,task_type) VALUES ('proj-b','development') RETURNING id")
        ).scalar()
    # Distinct content per row — dedup scope is (kind, uri, content_hash) and does NOT
    # include project_id, so reusing the same content would collapse both writes onto
    # one source. The test's intent is the project filter; the shared FTS term suffices.
    a = write(engine, SourceInput(kind="note", content="shared keyword first", project_id=p1))
    b = write(engine, SourceInput(kind="note", content="shared keyword second", project_id=p2))
    hits_p1 = recall(engine, "shared keyword", k=10, project_id=p1)
    ids = {h.id for h in hits_p1}
    assert a.source_id in ids
    assert b.source_id not in ids


def test_pre_filter_by_bucket(pg_url: str) -> None:
    engine = get_engine(pg_url)
    a = write(
        engine,
        SourceInput(kind="decision", content="bucket-test", buckets=["semantic"]),
    )
    b = write(
        engine,
        SourceInput(kind="gotcha", content="bucket-test", buckets=["failure", "episodic"]),
    )
    hits_failure = recall(engine, "bucket-test", k=10, buckets=["failure"])
    ids = {h.id for h in hits_failure}
    assert b.source_id in ids
    assert a.source_id not in ids
