"""SQL queries backing the Telescope frontend (v0.11.0). All queries are
read-only; routes never mutate. Returns Pydantic models for typed render."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from brain.compliance import under_captured_sessions, is_strict_mode
from brain.db import session_scope
from brain.staleness import scan_db

_SUBSTANTIVE_KINDS = ["decision", "gotcha", "pattern", "note", "subtask_summary", "session_summary", "faq"]


# ============ Dashboard ============

class HeroBlock(BaseModel):
    total: int
    delta_week: int
    last_capture: str  # human-readable relative time


class CaptureCadence(BaseModel):
    last_30d_total: int
    delta_vs_prior_30d: int
    by_kind: dict[str, int]
    sparkline: list[int]  # 30 ints, one per day


class ComplianceBlock(BaseModel):
    under_captured_30d: int
    thin_sessions_30d: int
    strict_mode: bool


class StalenessBlock(BaseModel):
    total: int
    changed: int
    missing: int
    untracked: int
    scanned: int


class FailureRow(BaseModel):
    id: int
    target_problem: str
    attempted_approach: str
    retry_count: int
    last_attempted_at: datetime


class EmbeddingCoverage(BaseModel):
    embedded: int
    total: int
    percent: float


class DashboardStats(BaseModel):
    hero: HeroBlock
    capture_cadence: CaptureCadence
    compliance: ComplianceBlock
    staleness: StalenessBlock
    failures: list[FailureRow]
    embedding_coverage: EmbeddingCoverage


def dashboard_stats(engine: Engine) -> DashboardStats:
    with session_scope(engine) as s:
        # Hero
        total = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        week_ago = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL "
                "  AND created_at >= NOW() - INTERVAL '7 days'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        last_cap_at = s.execute(
            text(
                "SELECT created_at FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar()

        # Capture cadence — per-kind for last 30d
        by_kind_rows = s.execute(
            text(
                "SELECT kind, COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL "
                "  AND created_at >= NOW() - INTERVAL '30 days' "
                "GROUP BY kind"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).all()
        by_kind = {r[0]: int(r[1]) for r in by_kind_rows}

        # Sparkline: count per day (last 30 days)
        spark_rows = s.execute(
            text(
                "SELECT DATE(created_at) AS d, COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL "
                "  AND created_at >= NOW() - INTERVAL '30 days' "
                "GROUP BY DATE(created_at) ORDER BY d"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).all()
        spark_dict = {r[0]: int(r[1]) for r in spark_rows}
        today = datetime.now(timezone.utc).date()
        sparkline = [spark_dict.get(today - timedelta(days=29 - i), 0) for i in range(30)]

        last_30d_total = sum(sparkline)
        prior_30d = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL "
                "  AND created_at >= NOW() - INTERVAL '60 days' "
                "  AND created_at <  NOW() - INTERVAL '30 days'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0

        # NOTE: these helpers each open their own session_scope, so this function
        # briefly holds up to 4 simultaneous pool connections. Acceptable for a
        # single-user local dashboard; revisit if pool pressure shows up in prod.
        uc = len(under_captured_sessions(engine, limit=200))
        thin = s.execute(
            text(
                "SELECT COUNT(DISTINCT session_id) FROM session_events "
                "WHERE event_kind = 'thin_session' AND occurred_at > NOW() - INTERVAL '30 days'"
            )
        ).scalar() or 0
        strict = is_strict_mode(engine)

        # Staleness
        report = scan_db(engine)
        by_status: dict[str, int] = {"changed": 0, "missing": 0, "untracked": 0}
        for sx in report.stale_sources:
            by_status[sx.status] = by_status.get(sx.status, 0) + 1

        # Failures (top 5 by retry_count)
        f_rows = s.execute(
            text(
                "SELECT id, target_problem, attempted_approach, retry_count, last_attempted_at "
                "FROM failure_memories "
                "WHERE t_valid_to IS NULL "
                "ORDER BY retry_count DESC, last_attempted_at DESC LIMIT 5"
            )
        ).all()

        # Embedding coverage
        emb_count = s.execute(
            text(
                "SELECT COUNT(DISTINCT s.id) FROM sources s "
                "WHERE s.kind = ANY(:k) AND s.t_valid_to IS NULL AND s.parent_id IS NULL "
                "  AND EXISTS ("
                "    SELECT 1 FROM embeddings_1024 e "
                "    JOIN sources child ON child.id = e.source_id "
                "    WHERE child.parent_id = s.id OR child.id = s.id "
                "  )"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0

    if last_cap_at:
        last_cap_str = _relative_time(last_cap_at)
    else:
        last_cap_str = "—"

    return DashboardStats(
        hero=HeroBlock(total=int(total), delta_week=int(week_ago), last_capture=last_cap_str),
        capture_cadence=CaptureCadence(
            last_30d_total=last_30d_total,
            delta_vs_prior_30d=last_30d_total - int(prior_30d),
            by_kind=by_kind,
            sparkline=sparkline,
        ),
        compliance=ComplianceBlock(
            under_captured_30d=int(uc),
            thin_sessions_30d=int(thin),
            strict_mode=strict,
        ),
        staleness=StalenessBlock(
            total=len(report.stale_sources),
            changed=by_status["changed"],
            missing=by_status["missing"],
            untracked=by_status["untracked"],
            scanned=report.scanned_sources,
        ),
        failures=[
            FailureRow(
                id=int(r.id),
                target_problem=str(r.target_problem),
                attempted_approach=str(r.attempted_approach),
                retry_count=int(r.retry_count),
                last_attempted_at=r.last_attempted_at,
            )
            for r in f_rows
        ],
        embedding_coverage=EmbeddingCoverage(
            embedded=int(emb_count),
            total=int(total),
            percent=(100.0 * int(emb_count) / int(total)) if total else 0.0,
        ),
    )


# ============ Sources list ============

class SourceRow(BaseModel):
    id: int
    kind: str
    uri: str | None
    content_preview: str
    created_at: datetime
    embedded: bool
    # NOTE: stale_status is populated by the route layer (Task 3) using a
    # cached scan_db() per request, not by list_sources itself — joining
    # the full staleness scan into every list query is too expensive.
    stale_status: str | None = None  # "changed" | "missing" | "untracked" | None


class SourcePage(BaseModel):
    rows: list[SourceRow]
    total: int
    page: int
    per_page: int
    total_pages: int


def list_sources(
    engine: Engine, *, kind: str | None = None, embedded_only: bool = False,
    page: int = 1, per_page: int = 30,
) -> SourcePage:
    offset = (page - 1) * per_page
    where = ["t_valid_to IS NULL", "parent_id IS NULL", "status = 'active'"]
    params: dict[str, Any] = {"limit": per_page, "offset": offset}
    if kind:
        where.append("kind = :kind")
        params["kind"] = kind
    if embedded_only:
        where.append(
            "EXISTS (SELECT 1 FROM embeddings_1024 e "
            "JOIN sources child ON child.id = e.source_id "
            "WHERE child.parent_id = s.id OR child.id = s.id)"
        )
    where_sql = " AND ".join(where)

    sql = (
        "SELECT s.id, s.kind, s.uri, LEFT(s.content, 120) AS preview, s.created_at, "
        "  EXISTS ("
        "    SELECT 1 FROM embeddings_1024 e "
        "    JOIN sources child ON child.id = e.source_id "
        "    WHERE child.parent_id = s.id OR child.id = s.id "
        "  ) AS embedded "
        f"FROM sources s WHERE {where_sql} "
        "ORDER BY s.id DESC LIMIT :limit OFFSET :offset"
    )
    count_sql = f"SELECT COUNT(*) FROM sources s WHERE {where_sql}"

    with session_scope(engine) as s:
        rows = s.execute(text(sql), params).all()
        total = s.execute(text(count_sql), params).scalar() or 0

    return SourcePage(
        rows=[
            SourceRow(
                id=int(r.id),
                kind=r.kind,
                uri=r.uri,
                content_preview=str(r.preview or ""),
                created_at=r.created_at,
                embedded=bool(r.embedded),
            )
            for r in rows
        ],
        total=int(total),
        page=page,
        per_page=per_page,
        total_pages=max(1, (int(total) + per_page - 1) // per_page),
    )


# ============ Source detail ============

class SourceDetail(BaseModel):
    id: int
    kind: str
    uri: str | None
    content: str
    created_at: datetime
    updated_at: datetime
    t_valid_from: datetime
    t_valid_to: datetime | None
    generation_depth: int
    provenance_kind: str
    project_id: int | None
    provenance_meta: dict[str, Any] | None


def source_by_id(engine: Engine, *, source_id: int) -> SourceDetail | None:
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT id, kind, uri, content, created_at, updated_at, "
                "  t_valid_from, t_valid_to, generation_depth, provenance_kind, "
                "  project_id, provenance_meta "
                "FROM sources WHERE id = :i AND t_valid_to IS NULL"
            ),
            {"i": source_id},
        ).first()
    if row is None:
        return None
    return SourceDetail(
        id=int(row.id),
        kind=row.kind,
        uri=row.uri,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
        t_valid_from=row.t_valid_from,
        t_valid_to=row.t_valid_to,
        generation_depth=int(row.generation_depth),
        provenance_kind=row.provenance_kind,
        project_id=row.project_id,
        provenance_meta=row.provenance_meta,
    )


# ============ Health page ============

class PoolStats(BaseModel):
    size: int
    checked_in: int
    checked_out: int
    overflow: int


class RetrievalLatency(BaseModel):
    p50_ms: float
    p95_ms: float
    sample_count: int


class HealthStats(BaseModel):
    sources_total: int
    sources_substantive: int
    sources_chunks: int
    captures_1h: int
    captures_24h: int
    captures_7d: int
    embedding: EmbeddingCoverage
    staleness: StalenessBlock
    pool: PoolStats
    retrieval: RetrievalLatency
    last_capture_at: datetime | None
    last_session_event_at: datetime | None


def _pool_stat(pool: Any, attr: str) -> int:
    """Read a pool stat that may be a method (QueuePool) or an int attribute (SingletonThreadPool)."""
    v = getattr(pool, attr, None)
    if v is None:
        return 0
    return int(v() if callable(v) else v)


def health_stats(engine: Engine) -> HealthStats:
    """Aggregate observability snapshot. Reuses dashboard math where possible."""
    with session_scope(engine) as s:
        sources_total = s.execute(text("SELECT COUNT(*) FROM sources")).scalar() or 0
        sources_chunks = s.execute(
            text("SELECT COUNT(*) FROM sources WHERE parent_id IS NOT NULL")
        ).scalar() or 0
        sources_substantive = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        captures_1h = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND parent_id IS NULL AND t_valid_to IS NULL "
                "  AND created_at >= NOW() - INTERVAL '1 hour'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        captures_24h = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND parent_id IS NULL AND t_valid_to IS NULL "
                "  AND created_at >= NOW() - INTERVAL '24 hours'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        captures_7d = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND parent_id IS NULL AND t_valid_to IS NULL "
                "  AND created_at >= NOW() - INTERVAL '7 days'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        last_cap_at = s.execute(
            text(
                "SELECT created_at FROM sources "
                "WHERE kind = ANY(:k) AND parent_id IS NULL AND t_valid_to IS NULL "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar()
        last_session_at = s.execute(
            text("SELECT MAX(occurred_at) FROM session_events")
        ).scalar()

        # Embedding coverage (mirrors dashboard math).
        emb_count = s.execute(
            text(
                "SELECT COUNT(DISTINCT s.id) FROM sources s "
                "WHERE s.kind = ANY(:k) AND s.t_valid_to IS NULL AND s.parent_id IS NULL "
                "  AND EXISTS ("
                "    SELECT 1 FROM embeddings_1024 e "
                "    JOIN sources child ON child.id = e.source_id "
                "    WHERE child.parent_id = s.id OR child.id = s.id"
                "  )"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0

        # Retrieval latency from retrieval_log. Use duration_ms column.
        # Fall back to zero counts if the table is empty or column is absent.
        try:
            latency_rows = s.execute(
                text(
                    "SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50, "
                    "       percentile_disc(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95, "
                    "       COUNT(*) AS n "
                    "FROM retrieval_log "
                    "WHERE occurred_at >= NOW() - INTERVAL '24 hours'"
                )
            ).first()
            p50 = float(latency_rows.p50 or 0)
            p95 = float(latency_rows.p95 or 0)
            n_samples = int(latency_rows.n or 0)
        except (OperationalError, ProgrammingError):
            # retrieval_log column may be named differently in older schemas
            p50, p95, n_samples = 0.0, 0.0, 0

    # Staleness (reuses scan_db).
    report = scan_db(engine)
    by_status: dict[str, int] = {"changed": 0, "missing": 0, "untracked": 0}
    for sx in report.stale_sources:
        by_status[sx.status] = by_status.get(sx.status, 0) + 1

    # Pool stats from SQLAlchemy.
    pool = engine.pool
    pool_stats = PoolStats(
        size=_pool_stat(pool, "size"),
        checked_in=_pool_stat(pool, "checkedin"),
        checked_out=_pool_stat(pool, "checkedout"),
        overflow=max(0, _pool_stat(pool, "overflow")),  # clamp negative idle-overflow
    )

    return HealthStats(
        sources_total=int(sources_total),
        sources_substantive=int(sources_substantive),
        sources_chunks=int(sources_chunks),
        captures_1h=int(captures_1h),
        captures_24h=int(captures_24h),
        captures_7d=int(captures_7d),
        embedding=EmbeddingCoverage(
            embedded=int(emb_count),
            total=int(sources_substantive),
            percent=(100.0 * int(emb_count) / int(sources_substantive)) if sources_substantive else 0.0,
        ),
        staleness=StalenessBlock(
            total=len(report.stale_sources),
            changed=by_status["changed"],
            missing=by_status["missing"],
            untracked=by_status["untracked"],
            scanned=report.scanned_sources,
        ),
        pool=pool_stats,
        retrieval=RetrievalLatency(p50_ms=p50, p95_ms=p95, sample_count=n_samples),
        last_capture_at=last_cap_at,
        last_session_event_at=last_session_at,
    )


# ============ Knowledge graph ============

class GraphNode(BaseModel):
    id: str           # cytoscape requires string ids
    label: str
    kind: str
    project_id: int | None


class GraphEdge(BaseModel):
    source: str       # cytoscape: "source" is the from-node id
    target: str       # "target" is the to-node id
    kind: str         # "parent-of" | "same-project"


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def knowledge_graph_data(engine: Engine, *, limit: int = 50) -> GraphData:
    """Return a lightweight node+edge view for Cytoscape rendering.

    Strategy: take top-N substantive sources by recency. Edges:
      1. parent-of: from each substantive source to up to 3 child chunks.
      2. same-project: cluster substantive sources sharing project_id under
         a synthetic project node (id "project-<pid>", kind "project").

    Heavy entity-extraction edges are deferred to v0.11.2.
    """
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, kind, content, project_id FROM sources "
                "WHERE kind = ANY(:k) AND t_valid_to IS NULL AND parent_id IS NULL "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"k": _SUBSTANTIVE_KINDS, "lim": limit},
        ).all()

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        seen_projects: set[int] = set()

        for r in rows:
            node_id = f"s-{r.id}"
            preview = (r.content or "").strip().splitlines()[0][:60]
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=f"{r.kind} #{r.id}: {preview}" if preview else f"{r.kind} #{r.id}",
                    kind=r.kind,
                    project_id=r.project_id,
                )
            )
            if r.project_id is not None:
                pid = int(r.project_id)
                pnode_id = f"p-{pid}"
                if pid not in seen_projects:
                    nodes.append(GraphNode(id=pnode_id, label=f"project #{pid}", kind="project", project_id=pid))
                    seen_projects.add(pid)
                edges.append(GraphEdge(source=node_id, target=pnode_id, kind="same-project"))

        # Parent-of edges: limit 3 chunks per substantive source for clarity.
        if rows:
            parent_ids = [int(r.id) for r in rows]
            chunk_rows = s.execute(
                text(
                    "SELECT id, parent_id, kind FROM sources "
                    "WHERE parent_id = ANY(:ids) AND t_valid_to IS NULL "
                    "ORDER BY parent_id, id"
                ),
                {"ids": parent_ids},
            ).all()
            chunk_count_per_parent: dict[int, int] = {}
            for c in chunk_rows:
                pid = int(c.parent_id)
                if chunk_count_per_parent.get(pid, 0) >= 3:
                    continue
                chunk_count_per_parent[pid] = chunk_count_per_parent.get(pid, 0) + 1
                cnode_id = f"c-{c.id}"
                # Display kind "chunk" is a presentational concept — chunk rows in the DB
                # inherit their parent's kind ("decision", "note", etc.), so we override here
                # so the Cytoscape stylesheet (node[kind='chunk']) and legend color apply.
                nodes.append(GraphNode(id=cnode_id, label=f"chunk #{c.id}", kind="chunk", project_id=None))
                edges.append(GraphEdge(source=f"s-{pid}", target=cnode_id, kind="parent-of"))

    return GraphData(nodes=nodes, edges=edges)


# ============ Helpers ============

def _relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"
