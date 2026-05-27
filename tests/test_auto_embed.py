"""brain.write auto_embed flag + heuristic contextual ingest (v0.8.4)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.schemas import SourceInput
from brain.write import _SUBSTANTIVE_KINDS, write


pytestmark = pytest.mark.slow  # embedder load is ~3s


def _embedding_count(engine, source_id: int) -> int:
    with session_scope(engine) as s:
        return int(
            s.execute(
                text(
                    "SELECT COUNT(*) FROM embeddings_1024 e "
                    "JOIN sources child ON child.id = e.source_id "
                    "WHERE child.parent_id = :sid OR child.id = :sid"
                ),
                {"sid": source_id},
            ).scalar()
            or 0
        )


def test_substantive_kinds_set_covers_expected_kinds() -> None:
    """Regression: the substantive kinds set is the contract for auto-embed."""
    assert "decision" in _SUBSTANTIVE_KINDS
    assert "gotcha" in _SUBSTANTIVE_KINDS
    assert "pattern" in _SUBSTANTIVE_KINDS
    assert "note" in _SUBSTANTIVE_KINDS
    assert "subtask_summary" in _SUBSTANTIVE_KINDS
    # Hook-driven high-volume kinds must NOT be in the set
    assert "tool_call_output" not in _SUBSTANTIVE_KINDS
    assert "command" not in _SUBSTANTIVE_KINDS


def test_auto_embed_false_is_default(pg_url: str) -> None:
    """Without explicit auto_embed=True, brain.write does not embed.
    Preserves Stop-hook performance (no embedder load tax on Bash failures)."""
    engine = get_engine(pg_url)
    res = write(
        engine,
        SourceInput(kind="decision", content="no auto embed by default"),
    )
    assert _embedding_count(engine, res.source_id) == 0


def test_auto_embed_true_triggers_embedding_for_substantive_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    res = write(
        engine,
        SourceInput(
            kind="decision",
            content="v0.8.4 auto-embed end-to-end test: decision content "
            "should be embedded immediately so subsequent recall finds it.",
        ),
        auto_embed=True,
    )
    assert _embedding_count(engine, res.source_id) >= 1


def test_auto_embed_skips_non_substantive_kinds(pg_url: str) -> None:
    """tool_call_output etc. should not embed even with auto_embed=True."""
    engine = get_engine(pg_url)
    res = write(
        engine,
        SourceInput(
            kind="tool_call_output",
            content="some tool output that's high-volume and not worth embedding",
        ),
        auto_embed=True,
    )
    assert _embedding_count(engine, res.source_id) == 0


def test_auto_embed_idempotent_on_resave(pg_url: str) -> None:
    """If a source already has embeddings, auto-embed is a no-op."""
    engine = get_engine(pg_url)
    src = SourceInput(
        kind="gotcha",
        content="idempotent embed test — once embedded, second auto_embed is a no-op",
        uri="test://idempotent-embed",
    )
    r1 = write(engine, src, auto_embed=True)
    n1 = _embedding_count(engine, r1.source_id)
    assert n1 >= 1

    # Dedup hit returns same source_id; second auto_embed should not add embeddings.
    r2 = write(engine, src, auto_embed=True)
    assert r2.source_id == r1.source_id
    assert _embedding_count(engine, r2.source_id) == n1


def test_brain_auto_embed_false_env_disables(pg_url: str, monkeypatch) -> None:
    monkeypatch.setenv("BRAIN_AUTO_EMBED", "false")
    engine = get_engine(pg_url)
    res = write(
        engine,
        SourceInput(kind="decision", content="env-disabled embed test"),
        auto_embed=True,
    )
    assert _embedding_count(engine, res.source_id) == 0
