"""src/brain/failures.py — failure-memory CRUD + dedup."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.failures import FailureRow, invalidate, list_active, record


def test_record_creates_new_failure_with_retry_one(pg_url: str) -> None:
    engine = get_engine(pg_url)
    fid, n = record(
        engine,
        target_problem="install postgres",
        attempted_approach="docker-compose pgvector image",
        outcome_evidence="connection refused on 5432",
    )
    assert fid > 0
    assert n == 1
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT target_problem, attempted_approach, retry_count "
                "FROM failure_memories WHERE id = :i"
            ),
            {"i": fid},
        ).first()
    assert row.target_problem == "install postgres"
    assert row.attempted_approach == "docker-compose pgvector image"
    assert row.retry_count == 1


def test_record_idempotent_bumps_retry_count(pg_url: str) -> None:
    engine = get_engine(pg_url)
    fid1, n1 = record(
        engine,
        target_problem="P1",
        attempted_approach="A1",
        outcome_evidence="evidence v1",
    )
    fid2, n2 = record(
        engine,
        target_problem="P1",
        attempted_approach="A1",
        outcome_evidence="evidence v2",
    )
    assert fid1 == fid2
    assert n1 == 1
    assert n2 == 2


def test_record_clears_prior_invalidation_on_reoccurrence(pg_url: str) -> None:
    engine = get_engine(pg_url)
    fid, _ = record(engine, target_problem="P2", attempted_approach="A2")
    invalidate(engine, failure_id=fid, reason="thought it was fixed")
    with session_scope(engine) as s:
        ended = s.execute(
            text("SELECT t_valid_to FROM failure_memories WHERE id = :i"), {"i": fid}
        ).scalar()
    assert ended is not None  # invalidated

    fid2, n2 = record(engine, target_problem="P2", attempted_approach="A2")
    assert fid2 == fid
    assert n2 == 2
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT t_valid_to, invalidation_reason "
                "FROM failure_memories WHERE id = :i"
            ),
            {"i": fid},
        ).first()
    assert row.t_valid_to is None  # cleared
    assert row.invalidation_reason is None


def test_list_active_excludes_invalidated(pg_url: str) -> None:
    engine = get_engine(pg_url)
    fid_a, _ = record(engine, target_problem="PA", attempted_approach="AA")
    fid_b, _ = record(engine, target_problem="PB", attempted_approach="AB")
    invalidate(engine, failure_id=fid_a, reason="resolved")
    rows = list_active(engine, limit=50)
    ids = {r.id for r in rows}
    assert fid_b in ids
    assert fid_a not in ids


def test_list_active_filtered_by_project(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        pid = s.execute(
            text(
                "INSERT INTO projects(slug, task_type, repo_root) "
                "VALUES ('test-failure-list', 'generic', '/tmp/test-failure-list') "
                "RETURNING id"
            )
        ).scalar()
    record(engine, target_problem="P_in", attempted_approach="A_in", project_id=pid)
    record(engine, target_problem="P_out", attempted_approach="A_out")
    rows = list_active(engine, project_id=pid)
    targets = {r.target_problem for r in rows}
    assert "P_in" in targets
    assert "P_out" not in targets


def test_record_writes_sources_row_with_auto_flag_when_provided(pg_url: str) -> None:
    engine = get_engine(pg_url)
    fid, _ = record(
        engine,
        target_problem="P_auto",
        attempted_approach="A_auto",
        outcome_evidence="Traceback ...",
        auto_flagged_by="stop_hook",
    )
    with session_scope(engine) as s:
        sid = s.execute(
            text("SELECT source_id FROM failure_memories WHERE id = :i"), {"i": fid}
        ).scalar()
        flags = s.execute(
            text("SELECT flags FROM sources WHERE id = :i"), {"i": sid}
        ).scalar()
    assert flags["auto_flagged_by"] == "stop_hook"


def test_record_preserves_prior_outcome_evidence_when_none_passed(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # First record with concrete evidence.
    fid1, _ = record(
        engine,
        target_problem="P_coalesce",
        attempted_approach="A_coalesce",
        outcome_evidence="original evidence",
    )
    # Re-occurrence with no evidence — COALESCE must keep the original.
    fid2, n2 = record(
        engine,
        target_problem="P_coalesce",
        attempted_approach="A_coalesce",
        outcome_evidence=None,
    )
    assert fid2 == fid1
    assert n2 == 2
    with session_scope(engine) as s:
        oe = s.execute(
            text("SELECT outcome_evidence FROM failure_memories WHERE id = :i"),
            {"i": fid1},
        ).scalar()
    assert oe == "original evidence"
