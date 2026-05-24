"""End-to-end: setup → write a sample corpus → recall → export → reingest."""

from pathlib import Path

import frontmatter
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.migrate_v1 import migrate_v1_markdown
from brain.obsidian.export import export_brain_to_markdown
from brain.read import recall
from brain.schemas import SourceInput
from brain.write import write


def test_capture_recall_export_reingest_roundtrip(tmp_path: Path, pg_url: str) -> None:
    engine = get_engine(pg_url)

    # Set up a project.
    with session_scope(engine) as s:
        pid = s.execute(
            text(
                "INSERT INTO projects(slug, task_type, repo_root) "
                "VALUES ('e2e-test','development','/tmp/e2e') RETURNING id"
            )
        ).scalar()

    # Capture three sources: a decision, a gotcha, a pattern.
    r1 = write(
        engine,
        SourceInput(
            kind="decision",
            content="# Use postgres + pgvector for v2 brain\n\nReasoning: scale + maturity.",
            project_id=pid,
            buckets=["semantic", "episodic"],
        ),
    )
    r2 = write(
        engine,
        SourceInput(
            kind="gotcha",
            content="# pgvector HALFVEC needs fixed dimension\n\nUse HALFVEC(1024) for HNSW.",
            project_id=pid,
            buckets=["failure", "episodic"],
        ),
    )
    r3 = write(
        engine,
        SourceInput(
            kind="pattern",
            content="# Bi-temporal validity via partial unique\n\nUNIQUE WHERE t_valid_to IS NULL.",
            project_id=pid,
            buckets=["procedural"],
        ),
    )
    assert r1.created and r2.created and r3.created

    # Recall: query should surface the decision.
    hits = recall(engine, "postgres pgvector", k=5, project_id=pid)
    assert any(h.id == r1.source_id for h in hits)

    # Export to markdown.
    out = tmp_path / "vault" / "Agent-Brain"
    summary = export_brain_to_markdown(engine, out)
    assert summary.files_written >= 3

    # Verify db_id frontmatter on the exported decision.
    decisions = list((out / "agent-memory" / "decisions").glob("*.md"))
    assert decisions
    written_ids = {r1.source_id, r2.source_id, r3.source_id}
    matched_decision = [
        frontmatter.load(f)
        for f in decisions
        if frontmatter.load(f).metadata.get("db_id") in written_ids
    ]
    assert matched_decision, "no exported decision matches any of the written source_ids"

    # Re-ingest the exported markdown.
    # Reingest creates new rows (different URIs) — round-trip-as-DR is a Phase 3a concern.
    # Verify that all 3 exported decision/gotcha/pattern files were imported as new rows.
    # (Phase 1 export does not preserve the original URI; Phase 3a will add db_id-based dedup.)
    summary2 = migrate_v1_markdown(engine, out)
    assert summary2.files_imported == 3
