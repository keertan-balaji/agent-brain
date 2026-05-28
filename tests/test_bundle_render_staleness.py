"""Bundle render surfaces stale_sources when present (v0.9.0)."""

from __future__ import annotations

from datetime import datetime, timezone

from brain.hooks.bundle import BundleSelection
from brain.hooks.render import render_bundle


def test_render_includes_stale_sources_section() -> None:
    sel = BundleSelection(
        stale_sources=[
            {"source_id": 42, "kind": "decision", "path": "/x/y.py", "status": "changed"},
        ],
    )
    out = render_bundle(
        sel,
        cc_session_id="cc-stale-1",
        session_id=1,
        cwd="/tmp/r",
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime.now(timezone.utc),
    )
    assert "Potentially stale" in out.markdown
    assert "42" in out.markdown
    assert "/x/y.py" in out.markdown
    assert out.manifest["selection"]["stale_sources"] == sel.stale_sources


def test_render_omits_stale_section_when_empty() -> None:
    sel = BundleSelection()
    out = render_bundle(
        sel,
        cc_session_id="cc-stale-2",
        session_id=1,
        cwd="/tmp/r",
        trigger="pre_compact",
        token_budget=4000,
        generated_at=datetime.now(timezone.utc),
    )
    assert "Potentially stale" not in out.markdown
