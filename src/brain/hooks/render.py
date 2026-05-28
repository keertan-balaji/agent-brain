"""Bundle render: BundleSelection → (manifest JSONB-ready dict, markdown body).

Markdown body is what SessionStart emits as additionalContext. Manifest is what
session_resume_bundles.manifest stores. Render is bounded by `token_budget`
(approximate: 4 chars/token); sections are dropped from least-important to
most-important to fit, with `Decisions` retained longest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from brain.hooks.bundle import BundleSelection
from brain.retrieval.render import quote_origin

_VALID_TRIGGERS = ("pre_compact", "session_end", "manual")


@dataclass
class RenderedBundle:
    manifest: dict[str, Any]
    markdown: str


def _section_md(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    return f"\n## {title}\n" + "\n".join(f"- {ln}" for ln in lines) + "\n"


def render_bundle(
    selection: BundleSelection,
    *,
    cc_session_id: str,
    session_id: int,
    cwd: str,
    trigger: str,
    token_budget: int,
    generated_at: datetime,
) -> RenderedBundle:
    if trigger not in _VALID_TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}; expected one of {_VALID_TRIGGERS}")

    manifest = {
        "schema_version": 1,
        "session_id": session_id,
        "cc_session_id": cc_session_id,
        "cwd": cwd,
        "trigger": trigger,
        "generated_at": generated_at.isoformat(),
        "token_budget": token_budget,
        "selection": {
            "decisions": selection.decisions,
            "gotchas": selection.gotchas,
            "patterns": selection.patterns,
            "failures": selection.failures,
            "subtasks_open": selection.subtasks_open,
            "recent_events": selection.recent_events,
            "stale_sources": selection.stale_sources,
        },
    }

    # Render sections in priority order; we drop from the tail when over budget.
    sections_in_priority: list[tuple[str, list[str]]] = [
        ("Decisions", [f"[id={d['source_id']}] {quote_origin(d['kind'], d['head'])}" for d in selection.decisions]),
        ("Recent gotchas", [f"[id={g['source_id']}] {quote_origin(g['kind'], g['head'])}" for g in selection.gotchas]),
        ("Patterns", [f"[id={p['source_id']}] {quote_origin(p['kind'], p['head'])}" for p in selection.patterns]),
        (
            "Unresolved failures",
            [
                f"target: {f['target_problem'][:60]}; approach: {f['approach'][:60]}; attempts: {f['retry_count']}"
                for f in selection.failures
            ],
        ),
        (
            "Open subtasks",
            [f"({t['subtask_id']}) {t['title']}" for t in selection.subtasks_open],
        ),
        (
            "Potentially stale sources (file changed since capture)",
            [
                f"[id={s['source_id']}] kind={s['kind']} status={s['status']} path={s['path']}"
                for s in selection.stale_sources
            ],
        ),
        (
            "Recent activity",
            [
                f"{e['occurred_at']} {e['event_kind']}: {str(e['payload'])[:80]}"
                for e in selection.recent_events
            ],
        ),
    ]

    header = (
        f"# Agent Brain resume bundle\n\n"
        f"Project `{cwd}`, session {session_id}, "
        f"triggered by `{trigger}` at {generated_at.isoformat()}.\n"
    )

    # Greedy assemble within ~4-chars-per-token budget.
    char_budget = token_budget * 4
    out = header
    for title, lines in sections_in_priority:
        block = _section_md(title, lines)
        if not block:
            continue
        if len(out) + len(block) > char_budget:
            # Try truncating the block down to a few lines that fit.
            remaining_chars = char_budget - len(out) - len(f"\n## {title}\n")
            if remaining_chars <= 20:
                continue
            truncated_lines: list[str] = []
            running = 0
            for ln in lines:
                added = len(f"- {ln}\n")
                if running + added > remaining_chars:
                    break
                truncated_lines.append(ln)
                running += added
            block = _section_md(title, truncated_lines)
            out += block
            break
        out += block

    return RenderedBundle(manifest=manifest, markdown=out)
