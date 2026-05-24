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


@main.group()
@click.pass_context
def summarize(ctx: click.Context) -> None:
    """Prepare/finalize the summarize reasoning helper."""


@summarize.command("prepare")
@click.option("--source-ids", required=True, help="Comma-separated source ids")
@click.pass_context
def summarize_prepare_cmd(ctx: click.Context, source_ids: str) -> None:
    from brain.reasoning.summarize import summarize_prepare as _prep

    ids = [int(x) for x in source_ids.split(",") if x.strip()]
    bundle = _prep(ctx.obj["engine"], source_ids=ids)
    payload = {
        "cache_key": bundle.cache_key_hex,
        "schema": bundle.schema_json,
        "prompt": bundle.prompt,
        "cached": bundle.cached.model_dump(mode="json") if bundle.cached else None,
    }
    click.echo(json.dumps(payload, indent=2))


@summarize.command("finalize")
@click.option("--cache-key", required=True, help="Hex cache key from prepare")
@click.option("--output", required=True, help="JSON output string to validate")
@click.pass_context
def summarize_finalize_cmd(ctx: click.Context, cache_key: str, output: str) -> None:
    from brain.reasoning.summarize import summarize_finalize as _fin

    out = _fin(ctx.obj["engine"], cache_key=bytes.fromhex(cache_key), raw_output=output)
    click.echo(json.dumps(out.model_dump(mode="json"), indent=2))


@main.group()
@click.pass_context
def compare(ctx: click.Context) -> None:
    """Prepare/finalize the compare reasoning helper."""


@compare.command("prepare")
@click.option("--a-id", "a_source_id", required=True, type=int, help="Source A id")
@click.option("--b-id", "b_source_id", required=True, type=int, help="Source B id")
@click.pass_context
def compare_prepare_cmd(ctx: click.Context, a_source_id: int, b_source_id: int) -> None:
    from brain.reasoning.compare import compare_prepare as _prep

    bundle = _prep(ctx.obj["engine"], a_source_id=a_source_id, b_source_id=b_source_id)
    payload = {
        "cache_key": bundle.cache_key_hex,
        "schema": bundle.schema_json,
        "prompt": bundle.prompt,
        "cached": bundle.cached.model_dump(mode="json") if bundle.cached else None,
    }
    click.echo(json.dumps(payload, indent=2))


@compare.command("finalize")
@click.option("--cache-key", required=True, help="Hex cache key from prepare")
@click.option("--output", required=True, help="JSON output string to validate")
@click.pass_context
def compare_finalize_cmd(ctx: click.Context, cache_key: str, output: str) -> None:
    from brain.reasoning.compare import compare_finalize as _fin

    out = _fin(ctx.obj["engine"], cache_key=bytes.fromhex(cache_key), raw_output=output)
    click.echo(json.dumps(out.model_dump(mode="json"), indent=2))


@main.group()
@click.pass_context
def cite(ctx: click.Context) -> None:
    """Prepare/finalize the cite reasoning helper."""


@cite.command("prepare")
@click.option("--claim", "claim_text", required=True, help="Claim to find supporting spans for")
@click.option("--source-ids", required=True, help="Comma-separated candidate source ids")
@click.pass_context
def cite_prepare_cmd(ctx: click.Context, claim_text: str, source_ids: str) -> None:
    from brain.reasoning.cite import cite_prepare as _prep

    ids = [int(x) for x in source_ids.split(",") if x.strip()]
    bundle = _prep(ctx.obj["engine"], claim_text=claim_text, candidate_source_ids=ids)
    payload = {
        "cache_key": bundle.cache_key_hex,
        "schema": bundle.schema_json,
        "prompt": bundle.prompt,
        "cached": bundle.cached.model_dump(mode="json") if bundle.cached else None,
    }
    click.echo(json.dumps(payload, indent=2))


@cite.command("finalize")
@click.option("--source-ids", required=True, help="Comma-separated candidate source ids (for re-validation)")
@click.option("--cache-key", required=True, help="Hex cache key from prepare")
@click.option("--output", required=True, help="JSON output string to validate")
@click.pass_context
def cite_finalize_cmd(ctx: click.Context, source_ids: str, cache_key: str, output: str) -> None:
    from brain.reasoning.cite import cite_finalize as _fin

    ids = [int(x) for x in source_ids.split(",") if x.strip()]
    out = _fin(
        ctx.obj["engine"],
        candidate_source_ids=ids,
        cache_key=bytes.fromhex(cache_key),
        raw_output=output,
    )
    click.echo(json.dumps(out.model_dump(mode="json"), indent=2))


@main.group()
@click.pass_context
def revise(ctx: click.Context) -> None:
    """Prepare/finalize the revise_on_ingest reasoning helper (A-MEM plan)."""


@revise.command("prepare")
@click.option("--source-id", "new_source_id", required=True, type=int, help="New source id to revise around")
@click.pass_context
def revise_prepare_cmd(ctx: click.Context, new_source_id: int) -> None:
    from brain.embed.bge_m3 import BgeM3Embedder
    from brain.reasoning.revise_on_ingest import revise_prepare as _prep

    embedder = BgeM3Embedder()
    bundle = _prep(ctx.obj["engine"], new_source_id=new_source_id, embedder=embedder)
    payload = {
        "cache_key": bundle.cache_key_hex,
        "schema": bundle.schema_json,
        "prompt": bundle.prompt,
        "cached": bundle.cached.model_dump(mode="json") if bundle.cached else None,
    }
    click.echo(json.dumps(payload, indent=2))


@revise.command("finalize")
@click.option("--cache-key", required=True, help="Hex cache key from prepare")
@click.option("--output", required=True, help="JSON output string to validate")
@click.pass_context
def revise_finalize_cmd(ctx: click.Context, cache_key: str, output: str) -> None:
    from brain.reasoning.revise_on_ingest import revise_finalize as _fin

    plan = _fin(ctx.obj["engine"], cache_key=bytes.fromhex(cache_key), raw_output=output)
    click.echo(json.dumps(plan.model_dump(mode="json"), indent=2))


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
    t_tau = Table(
        "bucket",
        "tau-rolling ratio",
        title="Recent selected/candidates ratio (past 100 queries)",
    )
    for bucket, ratio in sorted(report.tau_rolling_ratios.items()):
        t_tau.add_row(bucket, "no data yet" if ratio is None else f"{ratio:.3f}")
    console.print(t_tau)


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
@click.argument("source_id", type=int)
@click.option("-k", "top_k", default=5, type=int, help="Max suggestions to show (default 5)")
@click.pass_context
def link(ctx: click.Context, source_id: int, top_k: int) -> None:
    """Suggest related sources for SOURCE_ID via FTS + vector + entity-graph."""
    from brain.embed.bge_m3 import BgeM3Embedder
    from brain.reasoning.propose_links import propose_links as _propose

    engine = ctx.obj["engine"]
    embedder = BgeM3Embedder()
    result = _propose(engine, source_id=source_id, embedder=embedder, top_k=top_k)
    if not result.proposals:
        click.echo("no link candidates")
        return
    from sqlalchemy import text

    from brain.db import session_scope

    ids = [p.target_source_id for p in result.proposals]
    with session_scope(engine) as s:
        rows = s.execute(
            text("SELECT id, kind, content FROM sources WHERE id = ANY(:ids)"),
            {"ids": ids},
        ).fetchall()
    by_id = {r[0]: (r[1], r[2]) for r in rows}
    table = Table("target_id", "kind", "score", "rationale", "head")
    for p in result.proposals:
        kind, content = by_id.get(p.target_source_id, ("?", ""))
        table.add_row(
            str(p.target_source_id),
            kind,
            f"{p.score:.3f}",
            p.rationale_kind,
            content[:60],
        )
    console.print(table)


@main.command()
@click.argument("title")
@click.option("--project", default="", help="Project slug for frontmatter")
@click.pass_context
def decide(ctx: click.Context, title: str, project: str) -> None:
    """Capture an ADR-format decision into the brain (kind=decision)."""
    from datetime import date

    template_path = (
        Path(__file__).parent.parent.parent
        / "vault-template"
        / "templates"
        / "decision-adr.md"
    )
    body = template_path.read_text()
    body = (
        body.replace("{{ project }}", project)
        .replace("{{ date }}", date.today().isoformat())
        .replace("{{ title }}", title)
    )

    result = _write(
        ctx.obj["engine"],
        SourceInput(
            kind="decision",
            content=body,
            buckets=["semantic"],
        ),
    )
    click.echo(json.dumps(result.model_dump()))


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Snapshot: active projects, recent captures, recent failures."""
    from sqlalchemy import text

    from brain.db import session_scope

    engine = ctx.obj["engine"]
    with session_scope(engine) as s:
        active_projects = s.execute(
            text(
                "SELECT slug, status, updated_at FROM projects WHERE status='active' ORDER BY updated_at DESC LIMIT 20"
            )
        ).fetchall()
        captures_7d = s.execute(
            text(
                "SELECT kind, COUNT(*) FROM sources WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY kind ORDER BY 2 DESC"
            )
        ).fetchall()
        recent_failures = s.execute(
            text(
                "SELECT target_problem, attempted_approach, retry_count, last_attempted_at FROM failure_memories WHERE t_valid_to IS NULL ORDER BY last_attempted_at DESC LIMIT 5"
            )
        ).fetchall()

    t1 = Table("project slug", "status", "updated_at", title="Active projects")
    for r in active_projects:
        t1.add_row(str(r[0]), str(r[1]), str(r[2]))
    console.print(t1)

    t2 = Table("kind", "n (past 7d)", title="Recent captures")
    for r in captures_7d:
        t2.add_row(str(r[0]), str(r[1]))
    console.print(t2)

    t3 = Table(
        "problem", "approach", "retries", "last attempt", title="Recent failures (top 5)"
    )
    for r in recent_failures:
        t3.add_row(str(r[0])[:50], str(r[1])[:50], str(r[2]), str(r[3]))
    console.print(t3)

    click.echo("tasks tracking lands Phase 3a")


@main.command(name="promote-answer")
@click.argument("cache_key_hex")
@click.option("--kind", default="faq", help="Source kind for the promoted row (default: faq)")
@click.option("--yes", is_flag=True, help="Skip interactive confirmation")
@click.pass_context
def promote_answer(ctx: click.Context, cache_key_hex: str, kind: str, yes: bool) -> None:
    """Promote a cached reasoning output into a new captured source row."""
    from sqlalchemy import text

    from brain.db import session_scope

    engine = ctx.obj["engine"]
    try:
        key = bytes.fromhex(cache_key_hex)
    except ValueError:
        click.echo(f"invalid cache key (must be hex): {cache_key_hex}", err=True)
        ctx.exit(1)
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT helper_name, output_json FROM reasoning_cache WHERE cache_key = :k"),
            {"k": key},
        ).fetchone()
    if row is None:
        click.echo(f"no cache row for key {cache_key_hex}", err=True)
        ctx.exit(1)
    helper_name, output_json = row
    body = json.dumps(output_json, indent=2)
    click.echo(f"helper: {helper_name}")
    click.echo(body)
    if not yes and not click.confirm("promote this answer into a new source row?"):
        click.echo("aborted")
        return
    result = _write(
        engine,
        SourceInput(
            kind=kind,  # type: ignore[arg-type]
            content=body,
            provenance_kind="synthesized",
        ),
    )
    click.echo(json.dumps(result.model_dump()))


@main.command()
@click.argument("vault_path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def reingest(ctx: click.Context, vault_path: Path) -> None:
    """Re-ingest markdown from a vault path (Phase 1: equivalent to v1 migration)."""
    summary = migrate_v1_markdown(ctx.obj["engine"], vault_path)
    click.echo(
        f"processed {summary.files_processed} files "
        f"(created {summary.files_created}, dedup hits {summary.dedup_hits}, "
        f"skipped unknown type: {len(summary.skipped_unknown_type)})"
    )


if __name__ == "__main__":
    main()
