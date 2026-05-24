"""Schema round-trip tests: insert a row, read it back, verify shape."""

from sqlalchemy import text

from brain.db import get_engine, session_scope


def test_projects_round_trip(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO projects(slug, task_type, status, repo_root) "
                "VALUES (:slug, :tt, :st, :root)"
            ),
            {"slug": "test-proj", "tt": "development", "st": "active", "root": "/tmp/x"},
        )
    with session_scope(engine) as s:
        row = s.execute(text("SELECT slug, task_type, status FROM projects")).fetchone()
    assert row is not None
    assert row[0] == "test-proj"
    assert row[1] == "development"
    assert row[2] == "active"


def test_sessions_and_subtasks(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        proj_id = s.execute(
            text(
                "INSERT INTO projects(slug, task_type) VALUES ('p2','development') "
                "RETURNING id"
            )
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p, 'claude-code') "
                "RETURNING id"
            ),
            {"p": proj_id},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO subtasks(session_id, title, goal) "
                "VALUES (:s, 'do thing', 'do the thing')"
            ),
            {"s": sess_id},
        )
    with session_scope(engine) as s:
        sub = s.execute(text("SELECT title, outcome FROM subtasks")).fetchone()
    assert sub is not None
    assert sub[0] == "do thing"
    assert sub[1] is None  # outcome is NULL until set
