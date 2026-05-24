"""DB → Obsidian markdown view. One file per narrative source (per spec §Content
fidelity rule: tool_call_output and binary_artifact are NOT exported)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import Engine, text

from brain.db import session_scope

_EXPORT_KIND_TO_DIR: dict[str, str] = {
    "decision": "agent-memory/decisions",
    "gotcha": "agent-memory/gotchas",
    "pattern": "knowledge/patterns",
    "note": "agent-memory/notes",
    "session_summary": "agent-memory/sessions",
    "subtask_summary": "agent-memory/sessions",
    "paper": "knowledge/papers",
    "code_file": "knowledge/code",
    "web_page": "knowledge/web",
    "project_index": "projects",
    "faq": "knowledge/faqs",
}

_KIND_TO_TEMPLATE = {
    "decision": "decision.md.j2",
    "gotcha": "gotcha.md.j2",
    "pattern": "pattern.md.j2",
    "note": "note.md.j2",
    "session_summary": "session_summary.md.j2",
    "subtask_summary": "session_summary.md.j2",
    "paper": "note.md.j2",
    "code_file": "note.md.j2",
    "web_page": "note.md.j2",
    "project_index": "note.md.j2",
    "faq": "note.md.j2",
}


@dataclass
class ExportSummary:
    files_written: int = 0
    files_skipped: int = 0


def _slugify(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
    return cleaned[:80] if cleaned else fallback


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def export_brain_to_markdown(engine: Engine, out_root: Path) -> ExportSummary:
    out_root.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "render_templates"),
        autoescape=False,
        keep_trailing_newline=True,
    )
    summary = ExportSummary()

    with session_scope(engine) as s:
        rows = s.execute(
            text(
                """
                SELECT s.id, s.kind, s.content, s.status, s.created_at, s.updated_at,
                       s.provenance_kind,
                       p.slug AS project_slug,
                       COALESCE(
                           ARRAY(SELECT bucket FROM memory_classifications mc
                                 WHERE mc.source_id = s.id ORDER BY bucket),
                           ARRAY[]::TEXT[]
                       ) AS buckets
                FROM sources s
                LEFT JOIN projects p ON p.id = s.project_id
                WHERE s.t_valid_to IS NULL AND s.status != 'draft'
                """
            )
        ).fetchall()

    for row in rows:
        kind = row[1]
        if kind not in _EXPORT_KIND_TO_DIR:
            summary.files_skipped += 1
            continue
        subdir = out_root / _EXPORT_KIND_TO_DIR[kind]
        subdir.mkdir(parents=True, exist_ok=True)
        title = _extract_title(row[2], fallback=f"{kind}-{row[0]}")
        date_prefix = row[4].date().isoformat()
        is_dated_kind = kind in (
            "decision",
            "gotcha",
            "session_summary",
            "subtask_summary",
        )
        slug = _slugify(title, fallback=f"id-{row[0]}")
        fname = f"{date_prefix}-{slug}.md" if is_dated_kind else f"{slug}.md"
        target = subdir / fname

        template = env.get_template(_KIND_TO_TEMPLATE[kind])

        src = SimpleNamespace(
            id=row[0],
            kind=row[1],
            content=row[2],
            status=row[3],
            created_at=row[4],
            updated_at=row[5],
            provenance_kind=row[6],
        )
        rendered = template.render(
            source=src, project_slug=row[7], buckets=list(row[8])
        )
        target.write_text(rendered)
        summary.files_written += 1

    return summary
