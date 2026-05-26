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
from brain import failures as _failures
from brain.helpers.entity_timeline import entity_timeline as _entity_timeline
from brain.helpers.health import audit as _audit
from brain.hooks.cli import hook as _hook_group
from brain.migrate_v1 import migrate_v1_markdown
from brain.obsidian.export import export_brain_to_markdown
from brain.read import recall as _recall
from brain.retrieval.render import quote_origin
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
        head = quote_origin(h.kind, h.content[:80])
        table.add_row(str(h.id), h.kind, f"{h.score:.3f}", head)
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


@main.group()
@click.pass_context
def ingest(ctx: click.Context) -> None:
    """Chunk + embed a source (plain), or run agent-driven Contextual Retrieval."""


@ingest.command("source")
@click.argument("source_id", type=int)
@click.option("--child-max-tokens", default=256, type=int)
@click.option("--parent-max-tokens", default=1024, type=int)
@click.pass_context
def ingest_source_cmd(
    ctx: click.Context,
    source_id: int,
    child_max_tokens: int,
    parent_max_tokens: int,
) -> None:
    from brain.embed.bge_m3 import BgeM3Embedder
    from brain.ingest import ingest_source as _ingest

    embedder = BgeM3Embedder()
    summary = _ingest(
        ctx.obj["engine"],
        source_id=source_id,
        embedder=embedder,
        child_max_tokens=child_max_tokens,
        parent_max_tokens=parent_max_tokens,
    )
    click.echo(
        json.dumps(
            {
                "parent_source_id": summary.parent_source_id,
                "chunks_created": summary.chunks_created,
                "context_summaries_inserted": summary.context_summaries_inserted,
                "embeddings_inserted": summary.embeddings_inserted,
            },
            indent=2,
        )
    )


@ingest.command("prepare-contexts")
@click.argument("source_id", type=int)
@click.option("--child-max-tokens", default=256, type=int)
@click.option("--parent-max-tokens", default=1024, type=int)
@click.pass_context
def ingest_prepare_contexts_cmd(
    ctx: click.Context,
    source_id: int,
    child_max_tokens: int,
    parent_max_tokens: int,
) -> None:
    from brain.ingest import ingest_prepare_contexts as _prep

    prep = _prep(
        ctx.obj["engine"],
        source_id=source_id,
        child_max_tokens=child_max_tokens,
        parent_max_tokens=parent_max_tokens,
    )
    click.echo(
        json.dumps(
            {
                "source_id": prep.source_id,
                "doc_body": prep.doc_body,
                "chunks": [
                    {"chunk_idx": c.chunk_idx, "child_text": c.child_text, "prompt": c.prompt}
                    for c in prep.chunks
                ],
            },
            indent=2,
        )
    )


@ingest.command("finalize-contexts")
@click.argument("source_id", type=int)
@click.option("--contexts-json", required=True, help="JSON array of {chunk_idx, context}")
@click.option("--child-max-tokens", default=256, type=int)
@click.option("--parent-max-tokens", default=1024, type=int)
@click.pass_context
def ingest_finalize_contexts_cmd(
    ctx: click.Context,
    source_id: int,
    contexts_json: str,
    child_max_tokens: int,
    parent_max_tokens: int,
) -> None:
    from brain.embed.bge_m3 import BgeM3Embedder
    from brain.ingest import ChunkContext, ingest_finalize_contexts as _fin

    raw = json.loads(contexts_json)
    contexts = [ChunkContext(chunk_idx=int(c["chunk_idx"]), context=str(c["context"])) for c in raw]
    embedder = BgeM3Embedder()
    summary = _fin(
        ctx.obj["engine"],
        source_id=source_id,
        embedder=embedder,
        contexts=contexts,
        child_max_tokens=child_max_tokens,
        parent_max_tokens=parent_max_tokens,
    )
    click.echo(
        json.dumps(
            {
                "parent_source_id": summary.parent_source_id,
                "chunks_created": summary.chunks_created,
                "context_summaries_inserted": summary.context_summaries_inserted,
                "embeddings_inserted": summary.embeddings_inserted,
            },
            indent=2,
        )
    )


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


@main.command(name="session-log")
@click.option("--limit", default=20, type=int)
@click.option("--cc-session-id", help="Filter to a specific Claude Code session UUID")
@click.pass_context
def session_log_cmd(ctx: click.Context, limit: int, cc_session_id: str | None) -> None:
    """List recent session_events (filterable by Claude Code session UUID)."""
    from sqlalchemy import text as _text
    from brain.db import session_scope as _scope

    engine = ctx.obj["engine"]
    with _scope(engine) as s:
        if cc_session_id is not None:
            rows = s.execute(
                _text(
                    "SELECT se.occurred_at, se.event_kind, se.payload, ses.cc_session_id "
                    "FROM session_events se JOIN sessions ses ON se.session_id = ses.id "
                    "WHERE ses.cc_session_id = :cc "
                    "ORDER BY se.occurred_at DESC LIMIT :n"
                ),
                {"cc": cc_session_id, "n": limit},
            ).fetchall()
        else:
            rows = s.execute(
                _text(
                    "SELECT se.occurred_at, se.event_kind, se.payload, ses.cc_session_id "
                    "FROM session_events se JOIN sessions ses ON se.session_id = ses.id "
                    "ORDER BY se.occurred_at DESC LIMIT :n"
                ),
                {"n": limit},
            ).fetchall()
    t = Table("when", "cc_session", "kind", "payload_head", title="Session events")
    for r in rows:
        head = str(r.payload)[:60]
        t.add_row(r.occurred_at.isoformat(), (r.cc_session_id or "")[:8], r.event_kind, head)
    console.print(t)


@main.command(name="session-resume")
@click.option("--cwd", default=None, help="Working directory (defaults to PWD)")
@click.option(
    "--mode",
    type=click.Choice(["show", "regenerate"]),
    default="show",
    help="show: print latest unconsumed bundle. regenerate: build a fresh one and print.",
)
@click.pass_context
def session_resume_cmd(ctx: click.Context, cwd: str | None, mode: str) -> None:
    """Inspect or regenerate the latest resume bundle for a cwd."""
    import os as _os
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    from sqlalchemy import text as _text

    from brain.db import session_scope as _scope
    from brain.hooks.bundle import gather_bundle_selection
    from brain.hooks.render import render_bundle
    from brain.hooks.session import start_session

    engine = ctx.obj["engine"]
    cwd_val = cwd or _os.getcwd()

    if mode == "show":
        with _scope(engine) as s:
            row = s.execute(
                _text(
                    "SELECT rendered, generated_at, consumed_at FROM session_resume_bundles "
                    "WHERE cwd = :c ORDER BY generated_at DESC LIMIT 1"
                ),
                {"c": cwd_val},
            ).fetchone()
        if row is None:
            click.echo(f"no bundles for cwd={cwd_val}")
            return
        click.echo(f"# Latest bundle for {cwd_val}")
        click.echo(f"# generated_at: {row.generated_at.isoformat()}")
        click.echo(f"# consumed_at: {row.consumed_at.isoformat() if row.consumed_at else 'unconsumed'}")
        click.echo("---")
        click.echo(row.rendered)
        return

    # regenerate
    sid = start_session(
        engine,
        cc_session_id=f"manual-regenerate-{_dt.now(_tz.utc).timestamp()}",
        cwd=cwd_val,
        agent="brain-cli",
        source="startup",
    )
    sel = gather_bundle_selection(engine, session_id=sid, cwd=cwd_val, limit_per_kind=10)
    rendered = render_bundle(
        sel,
        cc_session_id="manual",
        session_id=sid,
        cwd=cwd_val,
        trigger="manual",
        token_budget=4000,
        generated_at=_dt.now(_tz.utc),
    )
    with _scope(engine) as s:
        project_id = s.execute(
            _text("SELECT id FROM projects WHERE repo_root = :r"), {"r": cwd_val},
        ).scalar()
        if project_id is None:
            slug = cwd_val.rstrip("/").rsplit("/", 1)[-1] or "anon"
            project_id = s.execute(
                _text(
                    "INSERT INTO projects(slug, task_type, repo_root) "
                    "VALUES (:s, 'generic', :r) ON CONFLICT (slug) DO UPDATE SET repo_root = EXCLUDED.repo_root "
                    "RETURNING id"
                ),
                {"s": slug, "r": cwd_val},
            ).scalar()
        s.execute(
            _text(
                "UPDATE session_resume_bundles SET superseded_at = NOW() "
                "WHERE cwd = :c AND consumed_at IS NULL AND superseded_at IS NULL"
            ),
            {"c": cwd_val},
        )
        s.execute(
            _text(
                "INSERT INTO session_resume_bundles("
                "project_id, session_id, trigger, token_budget, manifest, rendered, cwd) "
                "VALUES(:p, :s, 'manual', :tb, CAST(:m AS jsonb), :r, :c)"
            ),
            {
                "p": project_id,
                "s": sid,
                "tb": rendered.manifest["token_budget"],
                "m": _json.dumps(rendered.manifest),
                "r": rendered.markdown,
                "c": cwd_val,
            },
        )
    click.echo(rendered.markdown)


@main.command()
@click.option("--cwd", default=None, help="Working directory (defaults to PWD)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Output format",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Write to file instead of stdout",
)
@click.pass_context
def handoff(ctx: click.Context, cwd: str | None, fmt: str, out: Path | None) -> None:
    """Export the current resume bundle (markdown or JSON) for handoff to another agent."""
    import os as _os
    import json as _json

    from sqlalchemy import text as _text

    from brain.db import session_scope as _scope

    engine = ctx.obj["engine"]
    cwd_val = cwd or _os.getcwd()
    with _scope(engine) as s:
        row = s.execute(
            _text(
                "SELECT rendered, manifest FROM session_resume_bundles "
                "WHERE cwd = :c ORDER BY generated_at DESC LIMIT 1"
            ),
            {"c": cwd_val},
        ).fetchone()
    if row is None:
        click.echo(f"no bundle for cwd={cwd_val}; run `brain session-resume --mode regenerate` first", err=True)
        ctx.exit(1)
    body = row.rendered if fmt == "markdown" else _json.dumps(row.manifest, indent=2)
    if out is not None:
        out.write_text(body)
        click.echo(f"wrote {len(body)} bytes to {out}")
    else:
        click.echo(body)


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


@main.group()
def failure() -> None:
    """Failure-memory CRUD (typed entity, not just a tag)."""


@failure.command("record")
@click.option("--target-problem", required=True)
@click.option("--attempted-approach", required=True)
@click.option("--outcome-evidence", default=None)
@click.option("--project-id", type=int, default=None)
@click.pass_context
def failure_record(
    ctx: click.Context,
    target_problem: str,
    attempted_approach: str,
    outcome_evidence: str | None,
    project_id: int | None,
) -> None:
    """Record a failure attempt. Dedup on (target-problem, attempted-approach)."""
    fid, n = _failures.record(
        ctx.obj["engine"],
        target_problem=target_problem,
        attempted_approach=attempted_approach,
        outcome_evidence=outcome_evidence,
        project_id=project_id,
    )
    click.echo(f"failure_id={fid} retry_count={n}")


@failure.command("list")
@click.option("--project-id", type=int, default=None)
@click.option("--limit", type=int, default=20)
@click.pass_context
def failure_list(
    ctx: click.Context,
    project_id: int | None,
    limit: int,
) -> None:
    """List active failures, most-recently-attempted first."""
    rows = _failures.list_active(ctx.obj["engine"], project_id=project_id, limit=limit)
    if not rows:
        click.echo("(no active failures)")
        return
    for r in rows:
        click.echo(
            f"[{r.id}] retry={r.retry_count} "
            f"last={r.last_attempted_at:%Y-%m-%d %H:%M} "
            f"{r.target_problem[:60]} :: {r.attempted_approach[:60]}"
        )


@failure.command("invalidate")
@click.argument("failure_id", type=int)
@click.option("--reason", required=True)
@click.pass_context
def failure_invalidate(
    ctx: click.Context,
    failure_id: int,
    reason: str,
) -> None:
    """Mark a failure as superseded (it no longer applies)."""
    _failures.invalidate(ctx.obj["engine"], failure_id=failure_id, reason=reason)
    click.echo(f"invalidated failure_id={failure_id}")


main.add_command(_hook_group)


if __name__ == "__main__":
    main()
