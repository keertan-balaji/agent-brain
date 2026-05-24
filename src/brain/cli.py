"""Click CLI: `brain` command group."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from brain.config import load_config
from brain.db import get_engine
from brain.helpers.entity_timeline import entity_timeline as _entity_timeline
from brain.helpers.health import audit as _audit
from brain.migrate_v1 import migrate_v1_markdown
from brain.obsidian.export import export_brain_to_markdown
from brain.read import recall as _recall
from brain.schemas import SourceInput
from brain.write import write as _write

console = Console()


@click.group()
@click.pass_context
def main(ctx: click.Context) -> None:
    """Agent Brain CLI."""
    ctx.ensure_object(dict)
    cfg = load_config()
    ctx.obj["engine"] = get_engine(cfg.db_url)
    ctx.obj["config"] = cfg


@main.command()
@click.option("--kind", required=True)
@click.option("--content", required=True)
@click.option("--uri")
@click.option("--project-id", type=int)
@click.option("--bucket", multiple=True, help="Repeatable: --bucket semantic --bucket episodic")
@click.pass_context
def write(
    ctx: click.Context,
    kind: str,
    content: str,
    uri: str | None,
    project_id: int | None,
    bucket: tuple[str, ...],
) -> None:
    """Capture a source into the brain."""
    result = _write(
        ctx.obj["engine"],
        SourceInput(
            kind=kind,  # type: ignore[arg-type]
            content=content,
            uri=uri,
            project_id=project_id,
            buckets=list(bucket),  # type: ignore[arg-type]
        ),
    )
    click.echo(json.dumps(result.model_dump()))


@main.command()
@click.argument("query")
@click.option("-k", default=5, type=int)
@click.option("--project-id", type=int)
@click.option("--bucket", multiple=True)
@click.option("--kind-filter", multiple=True)
@click.pass_context
def recall(
    ctx: click.Context,
    query: str,
    k: int,
    project_id: int | None,
    bucket: tuple[str, ...],
    kind_filter: tuple[str, ...],
) -> None:
    """Retrieve top-k sources matching a query (FTS in Phase 1)."""
    hits = _recall(
        ctx.obj["engine"],
        query,
        k=k,
        project_id=project_id,
        buckets=list(bucket) or None,  # type: ignore[arg-type]
        kinds=list(kind_filter) or None,
    )
    table = Table("id", "kind", "score", "content (head)")
    for h in hits:
        table.add_row(str(h.id), h.kind, f"{h.score:.3f}", h.content[:80])
    console.print(table)


@main.command()
@click.option("--threshold", default=3, type=int)
@click.pass_context
def health(ctx: click.Context, threshold: int) -> None:
    """Run the Phase-1 health audit and print a table."""
    report = _audit(ctx.obj["engine"], undercapture_threshold=threshold)
    table = Table("table", "rows")
    for name, n in sorted(report.table_row_counts.items()):
        table.add_row(name, str(n))
    console.print(table)
    if report.undercaptured_sessions:
        console.print(
            f"[yellow]under-captured sessions: {len(report.undercaptured_sessions)}[/]"
        )
    if report.orphan_classification_count:
        console.print(
            f"[red]orphan classifications: {report.orphan_classification_count}[/]"
        )
    if report.stale_active_count:
        console.print(
            f"[yellow]stale active-status sources (>90d): {report.stale_active_count}[/]"
        )


@main.command(name="entity-timeline")
@click.argument("entity_id", type=int)
@click.option("--from", "from_ts", type=click.DateTime())
@click.option("--to", "to_ts", type=click.DateTime())
@click.pass_context
def entity_timeline_cmd(
    ctx: click.Context, entity_id: int, from_ts: datetime | None, to_ts: datetime | None
) -> None:
    """Show chronological events/decisions/failures referencing an entity."""
    items = _entity_timeline(
        ctx.obj["engine"], entity_id, from_ts=from_ts, to_ts=to_ts
    )
    table = Table("when", "kind", "role", "source_id", "summary")
    for item in items:
        table.add_row(
            item.occurred_at.isoformat(),
            item.kind,
            item.role,
            str(item.source_id or ""),
            item.summary[:80],
        )
    console.print(table)


@main.command(name="export")
@click.option("--out", required=False, type=click.Path(path_type=Path))
@click.pass_context
def export_cmd(ctx: click.Context, out: Path | None) -> None:
    """Export the brain to Obsidian-readable markdown."""
    cfg = ctx.obj["config"]
    out_path = out or cfg.brain_path
    summary = export_brain_to_markdown(ctx.obj["engine"], out_path)
    click.echo(
        f"wrote {summary.files_written} files to {out_path} (skipped {summary.files_skipped})"
    )


@main.command()
@click.argument("vault_path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def reingest(ctx: click.Context, vault_path: Path) -> None:
    """Re-ingest markdown from a vault path (Phase 1: equivalent to v1 migration)."""
    summary = migrate_v1_markdown(ctx.obj["engine"], vault_path)
    click.echo(
        f"imported {summary.files_imported} files (dedup hits: {summary.dedup_hits}, "
        f"skipped unknown type: {len(summary.skipped_unknown_type)})"
    )


if __name__ == "__main__":
    main()
