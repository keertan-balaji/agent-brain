from datetime import datetime

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.schemas import SourceInput
from brain.write import invalidate, write


def test_invalidate_marks_t_valid_to(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(engine, SourceInput(kind="note", uri="x://i1", content="will be invalid"))
    invalidate(engine, res.source_id, reason="user requested")
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT t_valid_to, invalidation_reason FROM sources WHERE id = :s"),
            {"s": res.source_id},
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] == "user requested"


def test_reassert_after_invalidate_creates_new_row(pg_url: str) -> None:
    engine = get_engine(pg_url)
    first = write(engine, SourceInput(kind="note", uri="x://i2", content="body"))
    invalidate(engine, first.source_id, reason="superseded")
    second = write(engine, SourceInput(kind="note", uri="x://i2", content="body"))
    assert second.source_id != first.source_id
    assert second.created is True
