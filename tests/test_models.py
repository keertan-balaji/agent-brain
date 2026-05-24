"""Schema round-trip tests: insert a row, read it back, verify shape."""

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.models import Project, Session as BrainSession, Source, Subtask  # noqa: F401  (BrainSession/Subtask re-exported for parity with plan)


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


def test_events_round_trip(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        pid = s.execute(
            text("INSERT INTO projects(slug, task_type) VALUES ('ep','development') RETURNING id")
        ).scalar()
        sid = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent) VALUES (:p,'claude-code') RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO events(session_id, ordinal, kind, tool, status) "
                "VALUES (:s, 1, 'tool_call', 'Bash', 'ok')"
            ),
            {"s": sid},
        )
    with session_scope(engine) as s:
        row = s.execute(text("SELECT kind, tool, status FROM events")).fetchone()
    assert row == ("tool_call", "Bash", "ok")


def test_procedures_partial_unique_active(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('pattern','x',sha256('procx'::bytea)) RETURNING id"
            )
        ).scalar()
        s.execute(
            text(
                "INSERT INTO procedures(source_id, title, target_situation, granularity, build_method) "
                "VALUES (:s, 't', 'install x', 'step', 'user_authored')"
            ),
            {"s": sid},
        )
    raised = False
    try:
        with session_scope(engine) as s:
            sid2 = s.execute(
                text(
                    "INSERT INTO sources(kind, content, content_hash) "
                    "VALUES ('pattern','y',sha256('procy'::bytea)) RETURNING id"
                )
            ).scalar()
            s.execute(
                text(
                    "INSERT INTO procedures(source_id, title, target_situation, granularity, build_method) "
                    "VALUES (:s, 't2', 'install x', 'step', 'user_authored')"
                ),
                {"s": sid2},
            )
    except Exception as exc:
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised, "second active step for same situation must violate partial unique index"


def test_entities_and_edges(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('paper','x',sha256('paperx'::bytea)) RETURNING id"
            )
        ).scalar()
        a = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('person','Alice',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        b = s.execute(
            text(
                "INSERT INTO entities(kind, canonical_name, source_id) "
                "VALUES ('person','Bob',:s) RETURNING id"
            ),
            {"s": sid},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO edges(src_id, dst_id, relation, source_id) "
                "VALUES (:a, :b, 'cites', :s)"
            ),
            {"a": a, "b": b, "s": sid},
        )
    with session_scope(engine) as s:
        rel = s.execute(text("SELECT relation FROM edges")).scalar()
    assert rel == "cites"


def test_retrieval_log_inserts(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO retrieval_log(query, agent) VALUES ('hello world','claude-code')"
            )
        )
    with session_scope(engine) as s:
        q = s.execute(text("SELECT query FROM retrieval_log")).scalar()
    assert q == "hello world"


def test_session_resume_bundles_active_unique(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        pid = s.execute(
            text("INSERT INTO projects(slug, task_type) VALUES ('rb','development') RETURNING id")
        ).scalar()
        s.execute(
            text(
                "INSERT INTO session_resume_bundles(project_id, trigger, token_budget, manifest, rendered) "
                "VALUES (:p,'manual', 500, '{}'::jsonb, 'render1')"
            ),
            {"p": pid},
        )
    raised = False
    try:
        with session_scope(engine) as s:
            s.execute(
                text(
                    "INSERT INTO session_resume_bundles(project_id, trigger, token_budget, manifest, rendered) "
                    "VALUES (:p,'manual', 500, '{}'::jsonb, 'render2')"
                ),
                {"p": pid},
            )
    except Exception as exc:
        raised = "unique" in str(exc).lower() or "duplicate" in str(exc).lower()
    assert raised, "second active bundle for same project must violate partial unique index"


def test_orm_round_trip_project_and_source(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        p = Project(slug="orm-test", task_type="development", status="active")
        s.add(p)
        s.flush()
        src = Source(
            kind="note",
            content="orm hello",
            content_hash=__import__("hashlib").sha256(b"orm hello").digest(),
            project_id=p.id,
        )
        s.add(src)
        s.flush()
        pid = p.id
        sid = src.id
    with session_scope(engine) as s:
        loaded = s.get(Source, sid)
    assert loaded is not None
    assert loaded.kind == "note"
    assert loaded.project_id == pid
    assert loaded.provenance_kind == "captured"
    assert loaded.generation_depth == 0
    assert loaded.status == "active"


def test_phase2_orm_round_trip(pg_url: str) -> None:
    from brain.models import CostLog, ExtractedClaim, ReasoningCache

    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash) "
                "VALUES ('note','c',sha256('cphase2'::bytea)) RETURNING id"
            )
        ).scalar()
        claim = ExtractedClaim(
            source_id=sid,
            subject="postgres",
            predicate="supports",
            object="halfvec",
            evidence_span_start=0,
            evidence_span_end=10,
            confidence=0.92,
            extracted_by_model="claude-haiku",
        )
        s.add(claim)
        cache = ReasoningCache(
            cache_key=b"\x00" * 32,
            helper_name="summarize",
            input_hash=b"\x01" * 32,
            llm_model_id="claude-haiku",
            llm_model_ver="2024-10-22",
            prompt_ver="v1",
            output_json={"summary": "hi"},
            tokens_used=42,
        )
        s.add(cache)
        log = CostLog(
            helper="summarize",
            llm_model="claude-haiku",
            tokens_in=100,
            tokens_out=50,
            usd=0.0001,
        )
        s.add(log)
    with session_scope(engine) as s:
        n = s.execute(text("SELECT COUNT(*) FROM extracted_claims")).scalar()
        assert n >= 1
        n = s.execute(text("SELECT COUNT(*) FROM reasoning_cache")).scalar()
        assert n >= 1
        n = s.execute(text("SELECT COUNT(*) FROM cost_log")).scalar()
        assert n >= 1
