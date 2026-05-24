from pathlib import Path

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.migrate_v1 import migrate_v1_markdown


def _write_md(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_migrates_decision_with_multibucket(tmp_path: Path, pg_url: str) -> None:
    vault = tmp_path / "Agent-Brain"
    _write_md(
        vault / "agent-memory" / "decisions" / "2026-05-17-pick-redis.md",
        """---
type: decision
tags: [auth]
project: brain
status: active
created: 2026-05-17
updated: 2026-05-17
related: []
---
# Pick redis for JWT store

Body of the decision.
""",
    )
    engine = get_engine(pg_url)
    summary = migrate_v1_markdown(engine, vault)
    assert summary.files_imported == 1
    with session_scope(engine) as s:
        # Scope by uri to isolate from any decision rows written by other tests
        # (the DB persists across tests within a session; only migrations reset).
        sid = s.execute(
            text("SELECT id FROM sources WHERE kind = 'decision' AND uri LIKE :u"),
            {"u": f"file://{vault.resolve()}/%"},
        ).scalar()
        buckets = sorted(
            r[0]
            for r in s.execute(
                text("SELECT bucket FROM memory_classifications WHERE source_id = :s"),
                {"s": sid},
            ).fetchall()
        )
    assert buckets == ["episodic", "semantic"]


def test_idempotent_rerun(tmp_path: Path, pg_url: str) -> None:
    vault = tmp_path / "Agent-Brain"
    _write_md(
        vault / "knowledge" / "patterns" / "feature-flag-rollout.md",
        """---
type: pattern
status: active
created: 2026-05-01
updated: 2026-05-01
---
# Feature flag rollout

Body.
""",
    )
    engine = get_engine(pg_url)
    first = migrate_v1_markdown(engine, vault)
    second = migrate_v1_markdown(engine, vault)
    assert first.files_imported == 1
    assert second.files_imported == 1
    assert second.dedup_hits == 1  # second run sees the existing row
