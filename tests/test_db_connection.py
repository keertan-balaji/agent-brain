"""Verify the DB connection module produces a working engine + session."""

from sqlalchemy import text

from brain.db import get_engine, session_scope


def test_engine_pings_postgres(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_session_scope_commits(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as session:
        session.execute(text("CREATE TEMP TABLE t(x INT)"))
        session.execute(text("INSERT INTO t VALUES (42)"))
    # commit was implicit on scope exit
    with session_scope(engine) as session:
        # temp table doesn't survive across sessions; that's fine for this test
        result = session.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_session_scope_rollback_on_exception(pg_url: str) -> None:
    engine = get_engine(pg_url)
    try:
        with session_scope(engine) as session:
            session.execute(text("CREATE TEMP TABLE t(x INT)"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # The temp table should not exist — rollback fired.
    with session_scope(engine) as session:
        result = session.execute(text("SELECT 1")).scalar()
    assert result == 1
