"""recall() writes a retrieval_log row with derived metrics on every call."""

from __future__ import annotations

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.read import recall
from brain.schemas import SourceInput
from brain.write import write


def _last_log_row(engine):
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT query, filters, candidates, selected, synthesized_ratio, "
                "captured_ratio, abstained, top1_score, agent, session_id "
                "FROM retrieval_log ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
    return row


def test_fts_recall_writes_log_row(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="postgres is a relational database"))
    hits = recall(engine, "postgres", k=5)
    assert len(hits) >= 1
    row = _last_log_row(engine)
    query, filters, candidates, selected, synth_ratio, cap_ratio, abstained, top1, agent, sid = row
    assert query == "postgres"
    assert filters is not None
    assert candidates is not None
    assert isinstance(candidates, list)
    assert selected is None
    assert abstained is False
    assert top1 is not None
    assert top1 > 0
    assert sid is None  # Phase 2 — no hooks yet


def test_abstain_sets_abstained_flag_true(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="postgres is a database"))
    hits = recall(engine, "postgres", k=5, tau=10.0)
    assert hits == []
    row = _last_log_row(engine)
    assert row[6] is True  # abstained


def test_hybrid_recall_populates_provenance_ratios(
    pg_url: str, bge_m3_embedder: BgeM3Embedder
) -> None:
    engine = get_engine(pg_url)
    for body in ("postgres is a relational database", "react is a frontend library"):
        src = write(engine, SourceInput(kind="note", content=body))
        ingest_source(engine, source_id=src.source_id, embedder=bge_m3_embedder)
    hits = recall(engine, "database", k=3, embedder=bge_m3_embedder)
    row = _last_log_row(engine)
    synth_ratio, cap_ratio = row[4], row[5]
    if hits:  # non-abstain path
        assert synth_ratio is not None
        assert cap_ratio is not None
        assert 0.0 <= synth_ratio <= 1.0
        assert 0.0 <= cap_ratio <= 1.0
        # ratios should sum to 1 across the result set (captured + synthesized)
        assert abs(synth_ratio + cap_ratio - 1.0) < 1e-6


def test_agent_field_from_env(pg_url: str, monkeypatch) -> None:
    engine = get_engine(pg_url)
    monkeypatch.setenv("BRAIN_AGENT", "test-agent")
    write(engine, SourceInput(kind="note", content="postgres"))
    recall(engine, "postgres", k=1)
    row = _last_log_row(engine)
    assert row[8] == "test-agent"


def test_filters_jsonb_includes_passed_filters(pg_url: str) -> None:
    engine = get_engine(pg_url)
    write(engine, SourceInput(kind="note", content="postgres is a database"))
    recall(engine, "postgres", k=1, project_id=None, buckets=["semantic"], kinds=["note"])
    row = _last_log_row(engine)
    filters = row[1]
    assert filters["buckets"] == ["semantic"]
    assert filters["kinds"] == ["note"]
    assert filters["project_id"] is None
