from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.helpers.health import audit
from brain.schemas import SourceInput
from brain.write import write


def test_audit_reports_table_sizes(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="a"))
    write(engine, SourceInput(kind="note", content="b"))
    report = audit(engine)
    assert report.table_row_counts["sources"] >= 2
    assert report.table_row_counts["sources_fts"] >= 2


def test_audit_lists_undercaptured_sessions(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with session_scope(engine) as s:
        pid = s.execute(
            text(
                "INSERT INTO projects(slug,task_type) VALUES ('uc','development') RETURNING id"
            )
        ).scalar()
        sess_id = s.execute(
            text(
                "INSERT INTO sessions(project_id, agent, ended_at) "
                "VALUES (:p,'claude-code', NOW()) RETURNING id"
            ),
            {"p": pid},
        ).scalar()
        # Add 1 event (below threshold=3, above 0) so the under-captured check fires.
        # Zero-event sessions are the Phase 1 baseline (no hook capture) and would
        # otherwise flood the audit; the query now requires > 0 events.
        s.execute(
            text("INSERT INTO events(session_id, ordinal, kind) VALUES (:s, 1, 'reflection')"),
            {"s": sess_id},
        )
    report = audit(engine, undercapture_threshold=3)
    assert sess_id in [row.session_id for row in report.undercaptured_sessions]


def test_audit_reports_orphan_classifications(pg_url: str) -> None:
    engine = get_engine(pg_url)
    # Create a source, classify it, then forcibly delete the source row (test only).
    res = write(
        engine,
        SourceInput(kind="note", content="for-orphan", buckets=["semantic"]),
    )
    with session_scope(engine) as s:
        # Hard delete sidesteps the CASCADE — emulating corruption to test the audit.
        s.execute(
            text("ALTER TABLE memory_classifications DROP CONSTRAINT memory_classifications_source_id_fkey")
        )
        s.execute(text("DELETE FROM sources WHERE id = :s"), {"s": res.source_id})
    report = audit(engine)
    assert report.orphan_classification_count >= 1
    # Restore the FK so subsequent tests stay clean.
    with session_scope(engine) as s:
        s.execute(text("DELETE FROM memory_classifications WHERE source_id = :s"), {"s": res.source_id})
        s.execute(
            text(
                "ALTER TABLE memory_classifications "
                "ADD CONSTRAINT memory_classifications_source_id_fkey "
                "FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE"
            )
        )
