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


def test_sources_basic_insert(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('note', 'hello world', sha256('hello world'::bytea)) RETURNING id"
            )
        ).scalar()
        assert sid is not None
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT kind, provenance_kind, generation_depth, status "
                "FROM sources WHERE id = :id"
            ),
            {"id": sid},
        ).fetchone()
    assert row is not None
    assert row[0] == "note"
    assert row[1] == "captured"  # default
    assert row[2] == 0  # default
    assert row[3] == "active"  # default


def test_sources_scoped_dedup_allows_same_hash_different_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        # Same content_hash but different kind — should be allowed.
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('note', 'duplicated', sha256('duplicated'::bytea))"
            )
        )
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('decision', 'duplicated', sha256('duplicated'::bytea))"
            )
        )
    with session_scope(engine) as s:
        cnt = s.execute(
            text(
                "SELECT COUNT(*) FROM sources WHERE content = 'duplicated' "
                "AND t_valid_to IS NULL"
            )
        ).scalar()
    assert cnt == 2  # two active rows: scoped uniqueness by (kind, uri, content_hash)


def test_sources_scoped_dedup_blocks_same_kind_uri_hash(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, uri, content, content_hash) "
                "VALUES ('note', 'x://1', 'dup2', sha256('dup2'::bytea))"
            )
        )
    raised = False
    try:
        with session_scope(engine) as s:
            s.execute(
                text(
                    "INSERT INTO sources(kind, uri, content, content_hash) "
                    "VALUES ('note', 'x://1', 'dup2', sha256('dup2'::bytea))"
                )
            )
    except Exception as exc:
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised


def test_memory_classifications_multi_bucket(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('decision','foo',sha256('foo'::bytea)) RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO memory_classifications(source_id, bucket, classifier) "
                "VALUES (:s, 'semantic', 'agent'), (:s, 'episodic', 'agent')"
            ),
            {"s": sid},
        )
    with session_scope(engine) as s:
        buckets = s.execute(
            text(
                "SELECT bucket FROM memory_classifications "
                "WHERE source_id = :s ORDER BY bucket"
            ),
            {"s": sid},
        ).fetchall()
    assert [b[0] for b in buckets] == ["episodic", "semantic"]


def test_failure_memories_dedup_on_problem_approach(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('gotcha','docker permission denied',sha256('a'::bytea)) "
                "RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO failure_memories(source_id, target_problem, attempted_approach) "
                "VALUES (:s, 'install pg on arch', 'docker compose pgvector')"
            ),
            {"s": sid},
        )
    raised = False
    try:
        with session_scope(engine) as s:
            s.execute(
                text(
                    "INSERT INTO failure_memories(source_id, target_problem, attempted_approach) "
                    "VALUES (:s, 'install pg on arch', 'docker compose pgvector')"
                ),
                {"s": sid},
            )
    except Exception as exc:
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised
