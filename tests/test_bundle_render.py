"""Bundle render: serializes BundleSelection to (manifest_json, markdown_body)
with a token budget."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brain.hooks.bundle import BundleSelection
from brain.hooks.render import RenderedBundle, render_bundle


def _selection() -> BundleSelection:
    s = BundleSelection()
    s.decisions = [{"source_id": 1, "kind": "decision", "head": "chose pgvector for ops simplicity"}]
    s.gotchas = [{"source_id": 2, "kind": "gotcha", "head": "::jsonb collides with bind params"}]
    s.patterns = [{"source_id": 3, "kind": "pattern", "head": "CAST(:x AS jsonb)"}]
    s.failures = [
        {"failure_id": 4, "target_problem": "install plugin", "approach": "bare ./", "retry_count": 3}
    ]
    s.subtasks_open = [{"subtask_id": 5, "title": "ship 3a-1", "goal": "compaction-survival"}]
    s.recent_events = [
        {"event_kind": "user_prompt_submit", "occurred_at": "2026-05-25T13:00:00+00:00", "payload": {"prompt": "p"}}
    ]
    return s


def test_render_produces_manifest_and_markdown() -> None:
    sel = _selection()
    out = render_bundle(
        sel,
        cc_session_id="abc",
        session_id=42,
        cwd="/tmp/proj",
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime(2026, 5, 25, 13, tzinfo=timezone.utc),
    )
    assert isinstance(out, RenderedBundle)
    assert out.manifest["session_id"] == 42
    assert out.manifest["cc_session_id"] == "abc"
    assert out.manifest["cwd"] == "/tmp/proj"
    assert out.manifest["trigger"] == "pre_compact"
    assert out.manifest["token_budget"] == 4000
    assert "selection" in out.manifest
    assert "Decisions" in out.markdown
    assert "pgvector" in out.markdown
    assert "## Recent activity" in out.markdown


def test_render_omits_empty_sections() -> None:
    sel = BundleSelection()
    sel.decisions = [{"source_id": 1, "kind": "decision", "head": "only decision"}]
    out = render_bundle(
        sel,
        cc_session_id="x",
        session_id=1,
        cwd="/x",
        trigger="manual",
        token_budget=4000,
        generated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )
    assert "Decisions" in out.markdown
    # Empty kinds should NOT appear as empty headers
    assert "Gotchas" not in out.markdown
    assert "Patterns" not in out.markdown


def test_render_respects_token_budget() -> None:
    sel = BundleSelection()
    # 200 entries × 100-char heads >> 4000-token budget (~16000 chars).
    sel.gotchas = [
        {"source_id": i, "kind": "gotcha", "head": "x" * 100} for i in range(200)
    ]
    out = render_bundle(
        sel,
        cc_session_id="x",
        session_id=1,
        cwd="/x",
        trigger="pre_compact",
        token_budget=200,  # ~800 chars
        generated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )
    # 4 chars/token approximation: 200 tokens ≈ 800 chars. Render must stay close.
    assert len(out.markdown) <= 200 * 4 * 1.2  # 20% slack for headers


def test_render_rejects_unknown_trigger() -> None:
    sel = BundleSelection()
    with pytest.raises(ValueError):
        render_bundle(
            sel,
            cc_session_id="x",
            session_id=1,
            cwd="/x",
            trigger="bogus",
            token_budget=4000,
            generated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        )
