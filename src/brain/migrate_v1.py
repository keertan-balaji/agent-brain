"""One-shot migration: v1 markdown vault → Postgres brain.

Parses YAML frontmatter, maps `type` to `kind`, classifies into buckets per
the same rules as classify.py, dedupes via brain.write()'s scoped uniqueness.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter
from sqlalchemy import Engine

from brain.classify import buckets_for_kind
from brain.schemas import SourceInput, SourceKind
from brain.write import write

_TYPE_TO_KIND: dict[str, SourceKind] = {
    "decision": "decision",
    "gotcha": "gotcha",
    "pattern": "pattern",
    "note": "note",
    "session": "session_summary",
    "api": "code_file",
    "architecture": "code_file",
    "process": "note",
    "glossary": "note",
    "project": "project_index",
    "task": "note",
    "meta": "note",
}


@dataclass
class MigrationSummary:
    files_imported: int = 0
    dedup_hits: int = 0
    skipped_unknown_type: list[Path] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.skipped_unknown_type is None:
            self.skipped_unknown_type = []


def migrate_v1_markdown(engine: Engine, vault_path: Path) -> MigrationSummary:
    summary = MigrationSummary()
    for md_file in vault_path.rglob("*.md"):
        if md_file.name.startswith("."):
            continue
        post = frontmatter.load(md_file)
        fm = post.metadata
        v1_type = fm.get("type")
        if v1_type not in _TYPE_TO_KIND:
            summary.skipped_unknown_type.append(md_file)
            continue
        kind = _TYPE_TO_KIND[v1_type]
        buckets = buckets_for_kind(kind, curated=False)
        result = write(
            engine,
            SourceInput(
                kind=kind,
                content=post.content,
                uri=f"file://{md_file.resolve()}",
                buckets=buckets,
                classifier="v1-migration",
            ),
        )
        if result.created:
            summary.files_imported += 1
        else:
            summary.dedup_hits += 1
            summary.files_imported += 1  # count as imported for re-run idempotency
    return summary
