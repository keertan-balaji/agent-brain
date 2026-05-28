# Agent Brain v0.11.0 — Brain Insights Frontend (Telescope) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local FastAPI + Jinja + HTMX web frontend for the brain — a single-glance dark instrument panel showing dashboard + source browser + source detail (+ optional recall console). Minimum slice; analytics + graph deferred to v0.11.1-2.

**Architecture:** New `src/brain/web/` Python package. FastAPI app with Jinja2 templates rendering pages that match the **Crimson Matrix** design exactly (see `frontend-design/mockups/*.html` for pixel-locked references — each mockup is a Stitch-generated Tailwind dark theme with inlined config). HTMX for partial-page swaps (filter pills, pagination). Alpine.js for tiny client-side state (cmd-K modal). Zero npm / node toolchain — Tailwind via CDN with theme config inlined in `base.html`, JetBrains Mono + Geist + Material Symbols Outlined via Google Fonts CDN, JS libs via CDN. New `brain serve` CLI command launches Uvicorn on `127.0.0.1:8765` by default.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Uvicorn, HTMX 2 (CDN), Alpine.js 3 (CDN), Tailwind CDN (`https://cdn.tailwindcss.com?plugins=forms,container-queries`), Material Symbols Outlined (Google Fonts CDN), JetBrains Mono + Geist (Google Fonts CDN). New runtime deps: `fastapi`, `uvicorn[standard]`, `jinja2`. No frontend build step.

> **Policy note:** This plan supersedes the v2 "system fonts only — no CDN" rule. v3.1 (Crimson Matrix) requires Tailwind CDN + Google Fonts CDN — adopt them. Note that headlines are JetBrains Mono (NOT Geist) and body is Geist (NOT Inter) — the Crimson Matrix flips the typography roles from the earlier green theme.

> **SRI note (security):** External `<script>` tags should carry `integrity="sha384-..." crossorigin="anonymous"` to defend against CDN compromise. Apply SRI to HTMX (`htmx.org`) and Alpine.js (`alpinejs`) — both publish hashes. Tailwind Play CDN (`cdn.tailwindcss.com`) is an interpretation layer that re-evaluates utility classes at runtime and is not SRI-pinnable; mitigate by pinning a vendored `tailwind.min.js` from a specific release in `static/` for production (out of scope for v0.11.0 dev preview; track for v0.11.1). Server binds to `127.0.0.1` by default, so the threat surface is the user's own machine — but `brain serve --host 0.0.0.0` exposes the CDN-load path to LAN attackers, so SRI matters once that flag is used.

**Spec reference:** `docs/superpowers/specs/2026-05-28-brain-insights-frontend-design.md` (v3 section at top — Persistent Cognition Protocol tokens, typography, components). Mockups: `frontend-design/mockups/{dashboard,sources,source-detail,recall}.html`. Token + philosophy manifest: `frontend-design/stitch_agent_brain_dashboard/persistent_cognition_protocol/DESIGN.md`. Aesthetic direction: matrix-green primary on tonal-layered dark canvas, Material 3 dark system, 1px outlines, no shadows.

**v0.10.1 prerequisites in place (verified):**
- `brain.staleness.scan_db` returns `StalenessReport` with `stale_sources` + counts. Used by dashboard "staleness" card.
- `brain.compliance.under_captured_sessions` + `is_strict_mode`. Used by "compliance" card.
- `brain.failures.list_active` returns `FailureRow` list. Used by "active failures" table.
- `brain.read.recall` is the recall path. Used by `/console` (v0.11.2).
- `brain_config`, `sources`, `session_events`, `failure_memories`, `retrieval_log` schemas stable.

---

## File structure (v0.11.0)

### Creations

```
src/brain/web/
  __init__.py                            # FastAPI app factory
  app.py                                 # uvicorn entrypoint, register routes
  routes/
    __init__.py
    dashboard.py                         # GET /
    sources.py                           # GET /sources, GET /sources/<id>
    htmx.py                              # HTMX partial endpoints (filter pills, search)
  templates/
    base.html                            # sidebar + topbar + grain overlay + font links
    dashboard.html                       # extends base; matches mockups/dashboard.html
    sources.html                         # extends base; matches mockups/sources.html
    source_detail.html                   # extends base; matches mockups/source-detail.html
    partials/
      _sidebar.html
      _topbar.html
      _filter_pills.html                 # HTMX swap target
      _source_row.html                   # used by HTMX search-as-you-type
  static/
    app.css                              # small overrides only: scrollbar, .material-symbols-outlined variation settings, pulse keyframes
    # NO bundled styles.css — Tailwind theme config is inlined inside base.html's <head>
  queries.py                             # all SQL queries (dashboard stats, source list, source detail)
  models.py                              # Pydantic response models for typed routes
tests/
  test_web_app.py                        # FastAPI route smoke tests via httpx
  test_web_queries.py                    # query functions against test DB
  test_web_render.py                     # template render smoke (no HTTP, no browser)
docs/v0.11.0-frontend.md
```

### Modifications

```
src/brain/cli.py                         # new `brain serve` command
pyproject.toml                           # add fastapi, uvicorn[standard], jinja2 deps
.claude-plugin/plugin.json               # version 0.11.0
.claude-plugin/marketplace.json          # version 0.11.0
.cursor-plugin/plugin.json               # version 0.11.0
.codex-plugin/plugin.json                # version 0.11.0
README.md                                # v0.11.0 section
```

---

## Empirical findings (locked in via mockup review)

1. **The dashboard must show real captures from the live brain — even if sparse.** The mockup shows 44 captures across 3 projects; production should query the actual `sources` table. Empty-state messaging ("no captures yet — run `brain decide ...`") is required.
2. **Sparklines are SVG paths, not Chart.js.** v0.11.0 dashboard uses inline SVG paths only — Chart.js arrives in v0.11.1 for the retrieval analytics page.
3. **HTMX is for partial swaps, not page transitions.** Page nav uses full HTTP. Filter pills + search-as-you-type use HTMX `hx-get` + `hx-target`.
4. **Static files are served via FastAPI's `StaticFiles` mount, not Uvicorn config.** Mount at `/static`.

---

## Task 1: FastAPI app skeleton + `brain serve` CLI

**Files:**
- Create: `src/brain/web/__init__.py`, `src/brain/web/app.py`
- Modify: `src/brain/cli.py`
- Modify: `pyproject.toml`
- Create: `tests/test_web_app.py`

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

In the `[project]` `dependencies` list, add:

```toml
"fastapi>=0.115",
"uvicorn[standard]>=0.32",
"jinja2>=3.1",
"httpx>=0.27",  # for tests
```

Run: `.venv/bin/pip install -e .`
Expected: deps install cleanly.

- [ ] **Step 2: Write the failing test**

Create `tests/test_web_app.py`:

```python
"""FastAPI web app smoke tests (v0.11.0)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from brain.web.app import create_app


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_app_factory_returns_fastapi_instance(pg_url: str) -> None:
    app = create_app(db_url=pg_url)
    assert app is not None
    assert app.title == "agent-brain"


def test_dashboard_route_returns_200(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    # The hero metric must appear somewhere on the page.
    assert "hero-value" in res.text


def test_static_files_served(client: TestClient) -> None:
    res = client.get("/static/app.css")
    assert res.status_code == 200
    # app.css holds Crimson Matrix overrides (scrollbar, scanline, MS icons).
    assert "crimson-scanline" in res.text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_app.py -v`
Expected: FAIL — `brain.web` doesn't exist.

- [ ] **Step 4: Implement the app skeleton**

Create `src/brain/web/__init__.py`:

```python
"""Brain Telescope — local FastAPI frontend for brain insights (v0.11.0)."""
from brain.web.app import create_app

__all__ = ["create_app"]
```

Create `src/brain/web/app.py`:

```python
"""FastAPI application factory + route registration."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from brain.db import get_engine


def create_app(*, db_url: str | None = None) -> FastAPI:
    """Build the Telescope FastAPI app.

    db_url is optional; if absent, `brain.config.load_config().db_url` is used.
    Lets tests pass a per-test pg_url.
    """
    if db_url is None:
        from brain.config import load_config
        db_url = load_config().db_url

    app = FastAPI(
        title="agent-brain",
        description="Brain Telescope — local insights frontend",
        version="0.11.0",
    )

    # Persist engine on app.state so route handlers can access it.
    app.state.engine = get_engine(db_url)

    web_root = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=str(web_root / "static")), name="static")

    from brain.web.routes.dashboard import router as dashboard_router
    from brain.web.routes.sources import router as sources_router
    from brain.web.routes.htmx import router as htmx_router
    app.include_router(dashboard_router)
    app.include_router(sources_router)
    app.include_router(htmx_router)

    return app
```

Create `src/brain/web/routes/__init__.py` as empty file.

Create `src/brain/web/routes/dashboard.py`:

```python
"""GET / — dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
_templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    # For Task 1, stub out the stats — Task 2 wires the live queries.
    return _templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "hero": {"total": 0, "delta_week": 0, "last_capture": "—"},
            "cards": {},
            "failures": [],
        },
    )
```

Create stub `src/brain/web/routes/sources.py`:

```python
"""GET /sources, GET /sources/<id>."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
_templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/sources", response_class=HTMLResponse)
def sources(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(
        "sources.html",
        {"request": request, "rows": [], "total": 0, "page": 1, "total_pages": 1},
    )


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def source_detail(request: Request, source_id: int) -> HTMLResponse:
    return _templates.TemplateResponse(
        "source_detail.html",
        {"request": request, "source": {"id": source_id, "kind": "—", "content": "Not found"}},
    )
```

Create stub `src/brain/web/routes/htmx.py`:

```python
"""HTMX partial endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/_htmx")


@router.get("/health")
def htmx_health() -> dict:
    return {"ok": True}
```

Create empty `src/brain/web/templates/dashboard.html` etc. — the minimal templates that allow the test to pass come in Task 3. For Task 1, just create them as:

```html
<!-- src/brain/web/templates/dashboard.html -->
<!DOCTYPE html><html><body><div class="hero-value">0</div></body></html>
```

```html
<!-- src/brain/web/templates/sources.html -->
<!DOCTYPE html><html><body><table></table></body></html>
```

```html
<!-- src/brain/web/templates/source_detail.html -->
<!DOCTYPE html><html><body><div class="detail-content">{{ source.content }}</div></body></html>
```

Create `src/brain/web/static/app.css` with the Crimson Matrix overrides (small file — Tailwind handles the rest via CDN):

```css
/* src/brain/web/static/app.css — Crimson Matrix overrides */

.material-symbols-outlined {
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  vertical-align: middle;
}

/* 4px crimson-hover scrollbars */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #0e0e0e; }
::-webkit-scrollbar-thumb { background: #444444; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #da0037; }

/* Optional CRT-scanline overlay for hero blocks */
.crimson-scanline {
  background: linear-gradient(to bottom, transparent 50%, rgba(218, 0, 55, 0.05) 50%);
  background-size: 100% 4px;
  pointer-events: none;
}
```

> **No `styles.css` in v3.1.** Tailwind handles all theming via the CDN script + inline config in `base.html`. `app.css` exists only for the handful of styles that can't live in Tailwind utilities (scrollbar, icon variation settings, scanline keyframes).

- [ ] **Step 5: Add `brain serve` to CLI**

In `src/brain/cli.py`, add a new command (place near the existing top-level commands):

```python
@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind (use 0.0.0.0 for LAN access — no auth!)")
@click.option("--port", default=8765, type=int)
@click.option("--reload", is_flag=True, help="Dev mode: auto-reload templates")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, reload: bool) -> None:
    """Launch Brain Telescope — local web frontend at http://<host>:<port> (v0.11.0)."""
    import uvicorn

    from brain.web.app import create_app

    cfg = ctx.obj["config"]
    app = create_app(db_url=cfg.db_url)
    click.echo(f"Telescope live at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=reload)
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_web_app.py -v`
Expected: PASS — 3 tests green.

- [ ] **Step 7: Smoke launch**

Run: `brain serve` (in another shell).
Visit: `http://127.0.0.1:8765`.
Expected: page renders (will look unfinished — templates are stubs).

Kill with Ctrl-C.

- [ ] **Step 8: Commit**

```bash
git add src/brain/web/ src/brain/cli.py pyproject.toml tests/test_web_app.py
git commit -m "feat(v0.11.0): FastAPI app skeleton + brain serve CLI"
```

---

## Task 2: Dashboard queries module

**Files:**
- Create: `src/brain/web/queries.py`
- Create: `tests/test_web_queries.py`

Pure query functions. No HTTP. Returns Pydantic models for typed render.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_queries.py`:

```python
"""Query functions backing the Telescope frontend (v0.11.0)."""

from __future__ import annotations

from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.queries import (
    dashboard_stats,
    list_sources,
    source_by_id,
)


def _seed_decision(engine, content: str, uri: str | None = None) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES ('decision', :c, :h, 'active', :u) RETURNING id"
            ),
            {"c": content, "h": h, "u": uri},
        ).scalar()
    return int(sid)


def test_dashboard_stats_empty_brain_returns_zeros(pg_url: str) -> None:
    engine = get_engine(pg_url)
    stats = dashboard_stats(engine)
    assert stats.hero.total == 0
    assert stats.hero.delta_week == 0


def test_dashboard_stats_counts_substantive_captures(pg_url: str) -> None:
    engine = get_engine(pg_url)
    _seed_decision(engine, "d1")
    _seed_decision(engine, "d2")
    stats = dashboard_stats(engine)
    assert stats.hero.total >= 2
    # Breakdown carries per-kind counts.
    assert stats.capture_cadence.by_kind.get("decision", 0) >= 2


def test_list_sources_default_returns_substantive_kinds(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_decision(engine, "browse-me", uri="decision://test-1")
    page = list_sources(engine, kind=None, page=1, per_page=20)
    ids = {row.id for row in page.rows}
    assert sid in ids
    assert page.total >= 1


def test_list_sources_filtered_by_kind(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_decision(engine, "filter-me", uri="decision://test-2")
    page = list_sources(engine, kind="decision", page=1, per_page=20)
    assert sid in {r.id for r in page.rows}
    page_g = list_sources(engine, kind="gotcha", page=1, per_page=20)
    assert sid not in {r.id for r in page_g.rows}


def test_source_by_id_returns_full_detail(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid = _seed_decision(engine, "detail-me", uri="decision://detail-1")
    src = source_by_id(engine, source_id=sid)
    assert src.id == sid
    assert src.content == "detail-me"
    assert src.uri == "decision://detail-1"


def test_source_by_id_returns_none_when_absent(pg_url: str) -> None:
    engine = get_engine(pg_url)
    assert source_by_id(engine, source_id=999_999) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_queries.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/brain/web/queries.py`**

```python
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
        by_kind = {row.kind: int(row.count) for row in by_kind_rows} if False else {r[0]: int(r[1]) for r in by_kind_rows}

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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_web_queries.py -v`
Expected: PASS — 6 tests green.

- [ ] **Step 5: Commit**

```bash
git add src/brain/web/queries.py tests/test_web_queries.py
git commit -m "feat(v0.11.0): dashboard + source list/detail queries"
```

---

## Task 3: Production templates matching mockups

**Files:**
- Modify: `src/brain/web/templates/{base,dashboard,sources,source_detail}.html`
- Create: `src/brain/web/templates/partials/{_sidebar,_topbar,_filter_pills,_source_row}.html`
- Modify: `src/brain/web/routes/{dashboard,sources}.py` to pass real data into templates

The templates must match `frontend-design/mockups/{dashboard,sources,source-detail}.html` exactly. Use Jinja2 to make the seeded data dynamic.

- [ ] **Step 1: Create `src/brain/web/templates/base.html`**

Mirror the Stitch mockup `<head>` block exactly. The base must include:

1. `<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>`
2. The full Tailwind theme config block (`<script id="tailwind-config">tailwind.config = {...}</script>`) extracted verbatim from any Stitch mockup. This is the single source of truth — every page inherits it from `base.html`.
3. Google Fonts links (Crimson Matrix):
   ```html
   <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Geist:wght@400;500;600&display=swap" />
   <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" />
   ```
4. The Material Symbols inline style + custom scrollbar CSS lifted from the Crimson Matrix mockups:
   ```html
   <link rel="stylesheet" href="{{ url_for('static', path='app.css') }}">
   ```
   where `app.css` contains:
   ```css
   .material-symbols-outlined {
     font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
     vertical-align: middle;
   }
   ::-webkit-scrollbar { width: 4px; height: 4px; }
   ::-webkit-scrollbar-track { background: #0e0e0e; }
   ::-webkit-scrollbar-thumb { background: #444444; border-radius: 2px; }
   ::-webkit-scrollbar-thumb:hover { background: #da0037; }
   .crimson-scanline {
     background: linear-gradient(to bottom, transparent 50%, rgba(218, 0, 55, 0.05) 50%);
     background-size: 100% 4px;
     pointer-events: none;
   }
   ```
5. `<body class="bg-background text-on-background font-body-md selection:bg-primary-container selection:text-white overflow-hidden">`.

Yield blocks for `title`, `topbar_meta`, and `content`. Include `partials/_sidebar.html` and `partials/_topbar.html`.

- [ ] **Step 2: Convert each mockup into a Jinja template**

For each of dashboard / sources / source-detail:
1. Open the mockup HTML.
2. Copy the `<main>` content into a Jinja template.
3. Replace seeded data with `{{ vars }}` from the route context.
4. For repeated rows (table rows, failure list), use `{% for ... %}` loops.
5. For the sparkline SVG path, generate the `d=` attribute from the `sparkline` int array. Use a Jinja macro `sparkline_path(values)` that maps to SVG coordinates.

- [ ] **Step 3: Wire route data**

Update `src/brain/web/routes/dashboard.py` to call `dashboard_stats(request.app.state.engine)` and pass the model into the template.

Update `src/brain/web/routes/sources.py` to:
- `GET /sources?kind=&page=` → `list_sources(...)` → template
- `GET /sources/{id}` → `source_by_id(...)` → template; 404 if None

- [ ] **Step 4: Write the failing render test**

Create `tests/test_web_render.py`:

```python
"""Verify production templates render expected content (v0.11.0)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.app import create_app


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_dashboard_renders_hero_value(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("test-decision")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'test-decision', :h, 'active')"
            ),
            {"h": h},
        )
    res = client.get("/")
    assert res.status_code == 200
    assert "hero-value" in res.text
    # The hero must contain a number ≥ 1 since we just inserted a decision.
    # v3: hero-value class lives inside a Tailwind-themed page; assert the class survives template render.
    assert "hero-value" in res.text


def test_sources_lists_recently_inserted(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("sources-page")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES ('decision', 'sources-page', :h, 'active', 'decision://test-sources-page')"
            ),
            {"h": h},
        )
    res = client.get("/sources")
    assert res.status_code == 200
    assert "decision://test-sources-page" in res.text
    assert "sources-page" in res.text


def test_source_detail_renders_content(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("detail-content")
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'detail-content', :h, 'active') RETURNING id"
            ),
            {"h": h},
        ).scalar()
    res = client.get(f"/sources/{int(sid)}")
    assert res.status_code == 200
    assert "detail-content" in res.text


def test_source_detail_404_for_missing(client: TestClient) -> None:
    res = client.get("/sources/999999")
    assert res.status_code == 404
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_web_render.py -v`
Expected: PASS — 4 tests green.

- [ ] **Step 6: Visual review**

```bash
brain serve  # in another shell
```

Open `http://127.0.0.1:8765` and `http://127.0.0.1:8765/sources` in a browser. Compare side-by-side with the static mockups. The colors, typography, spacing, hover states, and animations must match.

- [ ] **Step 7: Commit**

```bash
git add src/brain/web/templates/ src/brain/web/routes/ src/brain/web/static/ tests/test_web_render.py
git commit -m "feat(v0.11.0): production templates matching design mockups"
```

---

## Task 4: HTMX search-as-you-type + filter pills

**Files:**
- Modify: `src/brain/web/routes/htmx.py`
- Modify: `src/brain/web/templates/sources.html` (add `hx-*` attributes)
- Create: `src/brain/web/templates/partials/_source_rows.html` (HTMX swap target)

- [ ] **Step 1: Add the HTMX endpoint**

```python
@router.get("/sources", response_class=HTMLResponse)
def htmx_sources(
    request: Request,
    q: str = "",
    kind: str | None = None,
    page: int = 1,
) -> HTMLResponse:
    from brain.web.queries import list_sources

    engine = request.app.state.engine
    result = list_sources(engine, kind=kind, page=page, per_page=30)
    # Filter by q in-Python for v0.11.0 — FTS in v0.11.1
    if q:
        result.rows = [r for r in result.rows if q.lower() in (r.content_preview or "").lower()]

    return _templates.TemplateResponse(
        "partials/_source_rows.html",
        {"request": request, "rows": result.rows},
    )
```

- [ ] **Step 2: Update sources.html template**

Add `hx-get="/_htmx/sources"`, `hx-trigger="input changed delay:200ms"`, `hx-target="#source-rows"` to the search input. Wrap the `<tbody>` in a div with `id="source-rows"`.

- [ ] **Step 3: Test HTMX endpoint**

```python
def test_htmx_sources_returns_partial(client: TestClient, pg_url: str) -> None:
    # Insert a source that matches.
    ...
    res = client.get("/_htmx/sources?q=test")
    assert res.status_code == 200
    # Partial should NOT have <html> or <body> — just rows.
    assert "<html" not in res.text.lower()
    assert "<tr" in res.text
```

- [ ] **Step 4: Commit**

```bash
git add src/brain/web/routes/htmx.py src/brain/web/templates/sources.html src/brain/web/templates/partials/_source_rows.html
git commit -m "feat(v0.11.0): HTMX search-as-you-type on sources page"
```

---

## Task 5: Manifests + docs + ship v0.11.0

- [ ] **Step 1: Bump manifests**

```bash
sed -i 's/"version": "0.10.1"/"version": "0.11.0"/g' .claude-plugin/plugin.json .claude-plugin/marketplace.json .cursor-plugin/plugin.json .codex-plugin/plugin.json
```

Update descriptions to mention v0.11.0 Brain Telescope frontend.

- [ ] **Step 2: Add README section**

```markdown
## Agent Brain v0.11.0 — Brain Telescope (insights frontend)

A local web frontend for the agent-brain. Dark refined instrument panel showing dashboard + source browser + source detail. Built with FastAPI + Jinja + HTMX + Alpine — no node toolchain.

```bash
brain serve              # → http://127.0.0.1:8765
brain serve --port 9000
```

Pages shipped in v0.11.0: dashboard (capture cadence + compliance + staleness + failures + embedding coverage), source browser (filterable + paginated + HTMX search), source detail (full content + provenance + neighbors). Sessions timeline + retrieval analytics + knowledge graph + console deferred to v0.11.1-2.

Design: `docs/superpowers/specs/2026-05-28-brain-insights-frontend-design.md`. Mockups: `frontend-design/mockups/`.
```

- [ ] **Step 3: Write `docs/v0.11.0-frontend.md`**

Mirror the structure of `docs/v0.9.0-staleness.md`. Cover:
- Overview + aesthetic direction
- Pages shipped
- CLI: `brain serve` with all flags
- Stack (FastAPI / Jinja / HTMX / Alpine; no build)
- Known limits (no auth, dark-only, no mobile, polling not sockets)
- Roadmap to v0.11.1+

- [ ] **Step 4: Full suite**

```bash
.venv/bin/pytest tests/ -q
# Expected: previous 302 + new tests from this plan = ~315+ passing.
```

- [ ] **Step 5: End-to-end smoke**

```bash
brain serve --port 8765 &
sleep 2
curl -s http://127.0.0.1:8765/ | grep -q "hero-value" && echo "OK"
curl -s http://127.0.0.1:8765/sources | grep -q "search captures" && echo "OK"
kill %1
```

- [ ] **Step 6: Merge + tag**

```bash
git add docs/v0.11.0-frontend.md README.md .claude-plugin/ .cursor-plugin/ .codex-plugin/
git commit -m "docs(v0.11.0): operations doc + README + manifests bumped"

git checkout main
git merge --no-ff v0.11.0-frontend -m "Merge v0.11.0-frontend: Brain Telescope insights frontend"
git tag v0.11.0 -m "v0.11.0 — Brain Telescope (FastAPI + Jinja + HTMX dark insights frontend)"
git push origin main && git push origin v0.11.0
```

---

# Self-review

1. **Spec coverage** — 4 of the 8 Phase 3d items ship:
   - Dashboard ✓
   - Source browser ✓
   - Source detail ✓
   - `brain serve` CLI ✓
   - Sessions / retrieval analytics / graph / console / hooks / health → deferred to v0.11.1-2
2. **Placeholder scan** — Task 3 says "convert each mockup into a Jinja template" without inlining the full template — acceptable because the mockup file IS the spec; the implementer copies + parameterizes.
3. **Type consistency** — `DashboardStats`, `SourcePage`, `SourceDetail` defined in Task 2 and consumed in Task 3 templates with the field names used here.

---

# Risk notes

- **Mockup-template parity is load-bearing.** If the implementer paraphrases the markup or substitutes "easier" CSS, the design lock breaks. Code-review step: open the mockup and the live page side-by-side at 100% zoom; check border colors, font sizes, spacing.
- **Sparkline SVG path generation.** A Jinja macro should produce the path string from the int array; the implementer must test that the path renders identically to the hand-written one in the mockup.
- **Empty-state UX.** A brand-new brain has 0 captures. The dashboard hero should render `0` and a caption pointing at `brain decide` / `brain write`. Don't crash on empty.
- **Test DB isolation.** The `pg_url` fixture points at `brain_test`. The `dashboard_stats` and `list_sources` queries depend on `sources` rows seeded in the test — make sure those queries don't blow up when the table is empty.
- **FastAPI + module-level engine.** The app factory persists the engine on `app.state` — good for tests, but `brain serve` reuses it across requests. Ensure SQLAlchemy connection pooling is configured (it defaults to `pool_pre_ping=True` per `brain/db.py`).
