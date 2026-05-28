"""SQL queries backing the Telescope frontend (v0.11.0). All queries are
read-only; routes never mutate. Returns Pydantic models for typed render."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope

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
        from datetime import date, timedelta
        today = date.today()
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

        # Compliance
        from brain.compliance import under_captured_sessions, is_strict_mode
        uc = len(under_captured_sessions(engine, limit=200))
        thin = s.execute(
            text(
                "SELECT COUNT(DISTINCT session_id) FROM session_events "
                "WHERE event_kind = 'thin_session' AND occurred_at > NOW() - INTERVAL '30 days'"
            )
        ).scalar() or 0
        strict = is_strict_mode(engine)

        # Staleness
        from brain.staleness import scan_db
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
    stale_status: str | None  # "changed" | "missing" | "untracked" | None


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
                stale_status=None,
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
    provenance_meta: dict | None


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


# ============ Helpers ============

def _relative_time(dt: datetime) -> str:
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"
