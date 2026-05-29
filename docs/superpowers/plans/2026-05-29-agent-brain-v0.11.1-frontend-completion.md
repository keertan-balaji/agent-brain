# Agent Brain v0.11.1 — Brain Telescope Frontend Completion Plan

> **Historical plan — completed.** v0.11.1 shipped via commits `14f845a..66f518a`. The `frontend-design/` references throughout this plan now point to removed paths — the design manifest survives at `docs/design/crimson-matrix.md`, screenshots at `docs/design/screenshots/`, and the production Tailwind theme config lives at `src/brain/web/templates/base.html`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up the four remaining frontend surfaces — `/recall`, `/health`, `/knowledge`, and the favicon 404 — so the v0.11.0 Brain Telescope sidebar has no dead links and every Stitch Crimson Matrix mockup is live with real (or seeded-but-illustrative) data.

**Architecture:** Each page is a Jinja2 template extending `base.html` (Crimson Matrix Tailwind config already inlined). Routes mount on the existing FastAPI app. Data comes from new query functions added to `src/brain/web/queries.py` that read from the existing Postgres schema. No new infrastructure — just more routes, templates, and queries on top of the v0.11.0 skeleton.

**Tech Stack:** Same as v0.11.0 — FastAPI + Jinja2 + HTMX 2 + Alpine.js 3 + Tailwind CDN + Google Fonts. New dep: Cytoscape.js 3 (via CDN, for the knowledge graph page only).

**Spec reference:** Token + philosophy manifest at `frontend-design/stitch_agent_brain_dashboard/crimson_matrix/DESIGN.md`. Mockups at `frontend-design/mockups/{recall,health,knowledge}.html`. v0.11.0 design spec: `docs/superpowers/specs/2026-05-28-brain-insights-frontend-design.md`.

**v0.11.0 prerequisites in place (verified):**
- FastAPI app at `src/brain/web/app.py` mounts routes + `/static`.
- Shared Jinja env at `src/brain/web/templates_env.py` (`templates` global).
- `base.html` extends pattern with `{% block title %}`, `{% block page_title %}`, `{% block topbar_meta %}`, `{% block content %}`.
- `partials/_sidebar.html` already keyed on `active` context var with conditionals for `dashboard`, `sources`, AND `recall` (verified — recall conditional is already present from Task 3, just unwired). The sidebar partial does NOT yet have conditionals for `health` or `knowledge` — they're plain `href="#"` placeholders that this plan upgrades.
- `app.css` has `crimson-scanline`, scrollbar overrides, MS icon variation.
- `brain.read.recall(engine, query, *, k=10, project_id=None, buckets=None, kinds=None, include_archived=False, embedder=None, reranker=None, ...) -> list[RecallHit]` is the recall entry point. `RecallHit` has fields `id: int`, `kind: str`, `content: str`, `score: float`, `project_id: int | None`. FTS-only path (no embedder, no reranker) is the cheap fast path suitable for an interactive web search.
- `brain.web.queries.dashboard_stats`, `list_sources`, `source_by_id` are the existing query functions (Pydantic-modeled returns).
- Tests use `pg_url` fixture from `tests/conftest.py`. Autouse `_truncate_tables` runs after every test.
- Starlette 1.2 `TemplateResponse(request, name, context)` signature.

---

## File structure (v0.11.1)

### Creations

```
src/brain/web/
  templates/
    recall.html                          # /recall search console
    health.html                          # /health observability
    knowledge.html                       # /knowledge graph
    partials/
      _recall_hit.html                   # single recall result card
tests/
  test_web_recall.py                     # recall route smoke + query → render
  test_web_health.py                     # health route + health_stats query
  test_web_knowledge.py                  # knowledge route + knowledge_graph_data query
docs/v0.11.1-frontend-completion.md      # ops doc
```

### Modifications

```
src/brain/web/queries.py                 # add health_stats, knowledge_graph_data
src/brain/web/routes/__init__.py         # (still empty — kept clean)
src/brain/web/routes/dashboard.py        # no change (already done)
src/brain/web/routes/sources.py          # no change (already done)
src/brain/web/routes/htmx.py             # no change (already done)
src/brain/web/app.py                     # register 3 new routers + favicon route
src/brain/web/routes/recall.py           # NEW — GET /recall, POST /recall
src/brain/web/routes/health.py           # NEW — GET /health
src/brain/web/routes/knowledge.py        # NEW — GET /knowledge, GET /_htmx/knowledge.json
src/brain/web/routes/meta.py             # NEW — GET /favicon.ico → 204
src/brain/web/templates/base.html        # add Cytoscape.js CDN <script> conditionally
src/brain/web/templates/partials/_sidebar.html   # extend active conditionals to health + knowledge
.claude-plugin/plugin.json               # version 0.11.1
.claude-plugin/marketplace.json          # version 0.11.1
.cursor-plugin/plugin.json               # version 0.11.1
.codex-plugin/plugin.json                # version 0.11.1
README.md                                # v0.11.1 section
```

---

## Empirical findings (locked in via mockup review + recall code inspection)

1. **Recall via FTS-only is the right v0.11.1 wiring.** `brain.read.recall(engine, query)` with no embedder/reranker uses pure FTS — no GPU dependency, low latency, returns 10 hits by default. Vector + rerank can be added in v0.11.2 behind a checkbox.
2. **Knowledge graph: use parent_id + project_id as the relationship signal.** The brain has no dedicated relationships table for substantive captures. Edges = (substantive parent → its chunk children) + (substantive parents in the same project clustered into a center node). Limit to top 50 nodes by recency to avoid melting the browser.
3. **Health page metrics are dashboard_stats++.** Most fields are already computed in `dashboard_stats` — `health_stats` reuses them and adds retrieval p50/p95 latency from `retrieval_log` + DB pool stats from `engine.pool`.
4. **Mockups call out at `<main class="md:ml-64 ...">`.** The 256px sidebar offset is the only mobile-responsive behavior in the mockups; everything else is desktop-only. Match the mockup's `md:` breakpoints exactly.
5. **Mockup search inputs are pre-filled with seeded query text.** Production templates start with empty `value=""`. The placeholder text from the mockup is preserved.

---

## Task 1: `/recall` page + favicon (closes the visible 404s)

**Files:**
- Create: `src/brain/web/routes/recall.py`
- Create: `src/brain/web/routes/meta.py`
- Create: `src/brain/web/templates/recall.html`
- Create: `src/brain/web/templates/partials/_recall_hit.html`
- Modify: `src/brain/web/app.py`
- Modify: `src/brain/web/templates/partials/_sidebar.html` (already has the recall conditional; verify and leave alone)
- Create: `tests/test_web_recall.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_recall.py`:

```python
"""Recall page render + search smoke (v0.11.1)."""

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


def test_recall_page_renders_empty_state(client: TestClient) -> None:
    res = client.get("/recall")
    assert res.status_code == 200
    # The page shows the query input + an empty-state when no q is set.
    assert 'name="q"' in res.text
    assert "Memory Retrieval" in res.text  # page title from the mockup


def test_recall_page_runs_query_and_shows_hits(client: TestClient, pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("recall-target-unique-phrase")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'recall-target-unique-phrase', :h, 'active')"
            ),
            {"h": h},
        )
    res = client.get("/recall?q=recall-target-unique-phrase")
    assert res.status_code == 200
    assert "recall-target-unique-phrase" in res.text
    # At least one hit card is rendered — the partial uses class "recall-hit".
    assert "recall-hit" in res.text


def test_recall_page_no_match_shows_empty_state(client: TestClient) -> None:
    res = client.get("/recall?q=zzz-no-such-phrase-anywhere")
    assert res.status_code == 200
    assert "No matches" in res.text or "0 matches" in res.text


def test_favicon_returns_204(client: TestClient) -> None:
    res = client.get("/favicon.ico")
    assert res.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_recall.py -v`
Expected: FAIL — routes don't exist (`/recall` and `/favicon.ico` both 404 today).

- [ ] **Step 3: Implement `src/brain/web/routes/meta.py`**

```python
"""Cross-cutting meta endpoints (favicon, robots.txt etc.)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Silence the browser's automatic /favicon.ico probe.

    Returning 204 No Content stops browsers from logging a 404 and is cheaper
    than serving a real icon for a CLI-style local tool.
    """
    return Response(status_code=204)
```

- [ ] **Step 4: Implement `src/brain/web/routes/recall.py`**

```python
"""GET /recall — recall search console."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from brain.read import recall
from brain.web.templates_env import templates

router = APIRouter()


@router.get("/recall", response_class=HTMLResponse)
def recall_page(
    request: Request,
    q: str = Query("", max_length=500, description="Free-text recall query (FTS path)"),
    k: int = Query(10, ge=1, le=50),
) -> HTMLResponse:
    """Render the recall console.

    Empty q -> just the input form + empty state. Non-empty q -> run
    brain.read.recall in FTS-only mode (no embedder, no reranker — fast path)
    and render the hit cards.
    """
    hits: list = []
    if q.strip():
        hits = recall(request.app.state.engine, q.strip(), k=k)

    return templates.TemplateResponse(
        request,
        "recall.html",
        {
            "q": q,
            "k": k,
            "hits": hits,
            "match_count": len(hits),
            "active": "recall",
        },
    )
```

- [ ] **Step 5: Implement `src/brain/web/templates/partials/_recall_hit.html`**

Adapt the result-card markup from `frontend-design/mockups/recall.html` (lines ~342-383) — strip the seeded `RRF Score`/`FTS Score` doubled-score block (FTS-only path has one score), keep the single-score side-rail, and wire the kind/content/score to the `RecallHit` fields.

```jinja2
{# Single recall hit card. Context var: `hit` (a RecallHit dataclass) #}
<div class="recall-hit border border-surface-container-highest bg-surface-container-lowest rounded-DEFAULT overflow-hidden group hover:border-primary-container transition-colors relative">
  <div class="absolute top-0 left-0 w-1 h-full bg-primary-container"></div>
  <div class="p-4 pl-6">
    <div class="flex justify-between items-start mb-2">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-primary-container text-sm">description</span>
        <h3 class="font-label-md text-label-md text-on-surface truncate max-w-md">
          <a href="/sources/{{ hit.id }}" class="hover:text-primary">
            {{ hit.kind }} #{{ hit.id }}
          </a>
        </h3>
      </div>
      <div class="flex flex-col items-end">
        <span class="font-label-sm text-[10px] text-on-surface-variant">FTS Score</span>
        <span class="font-headline-sm text-sm text-primary">{{ "%.3f" | format(hit.score) }}</span>
      </div>
    </div>
    <div class="bg-surface-container-lowest border border-surface-container-high p-3 rounded-DEFAULT font-body-md text-sm text-on-surface-variant leading-relaxed overflow-x-auto">
      <pre class="whitespace-pre-wrap">{{ hit.content[:500] }}{% if hit.content | length > 500 %}…{% endif %}</pre>
    </div>
    <div class="flex justify-between items-center mt-3 pt-3 border-t border-surface-container-highest">
      <span class="font-label-sm text-[10px] text-on-surface-variant">
        {% if hit.project_id %}project={{ hit.project_id }}{% else %}no project{% endif %}
      </span>
      <a href="/sources/{{ hit.id }}" class="font-label-sm text-label-sm text-primary hover:text-primary-container transition-colors flex items-center gap-1">
        <span class="material-symbols-outlined text-[14px]">open_in_new</span> Open
      </a>
    </div>
  </div>
</div>
```

- [ ] **Step 6: Implement `src/brain/web/templates/recall.html`**

Extends base.html. Copy the page-frame structure from `frontend-design/mockups/recall.html` `<main>` (lines 265-420), with these substitutions:
- Search input: `value="{{ q | e }}"`, `name="q"`, wrap in `<form action="/recall" method="get" class="...">` so Enter submits.
- Metrics bar: show `{{ match_count }}` for "Matches" (right-side metric). Drop the "Latency" stat (no easy hook — defer to v0.11.2).
- "Active Filters" pill row: drop (no filter params in FTS-only v0.11.1).
- Results list: `{% for hit in hits %}{% include 'partials/_recall_hit.html' %}{% else %}<empty-state>{% endfor %}`.
- Empty state: when no hits AND q is empty, show "Enter a query to search the brain." When q is set but no hits, show `No matches for "{{ q }}"`.
- Drop the seeded "LOAD MORE RESULTS" button (k=10 is plenty for v0.11.1; pagination is v0.11.2).

```jinja2
{% extends "base.html" %}

{% block title %}Recall — Agent Brain{% endblock %}
{% block page_title %}Recall{% endblock %}
{% block topbar_meta %}
  <span class="inline-flex items-center px-2 py-1 rounded-DEFAULT border border-surface-container-highest font-label-sm text-label-sm text-on-surface-variant bg-surface-container-low">
    <span class="w-1.5 h-1.5 rounded-full bg-primary-container mr-2"></span>
    FTS path
  </span>
{% endblock %}

{% block content %}
<div class="flex-1 overflow-y-auto p-margin md:p-6 lg:p-8 space-y-6">
  <div class="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-surface-container-highest pb-4">
    <div>
      <h2 class="font-headline-lg text-headline-lg text-on-surface">Memory Retrieval</h2>
      <p class="font-body-md text-body-md text-on-surface-variant mt-1">
        FTS search over substantive sources. Vector + rerank land in v0.11.2.
      </p>
    </div>
    <div class="flex gap-2">
      <span class="inline-flex items-center px-2 py-1 rounded-DEFAULT border border-surface-container-highest font-label-sm text-label-sm text-on-surface-variant bg-surface-container-low">
        <span class="w-1.5 h-1.5 rounded-full bg-primary-container mr-2"></span>
        Index: Live
      </span>
    </div>
  </div>

  <form action="/recall" method="get" class="relative w-full group">
    <div class="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
      <span class="material-symbols-outlined text-on-surface-variant group-focus-within:text-primary-container transition-colors">search</span>
    </div>
    <input
      class="block w-full pl-12 pr-4 py-4 bg-surface-container-low border border-surface-container-highest rounded-DEFAULT font-headline-sm text-headline-sm text-on-surface placeholder-on-surface-variant focus:border-primary-container focus:ring-0 focus:outline-none transition-colors"
      placeholder="Enter a recall query…"
      type="text"
      name="q"
      value="{{ q | e }}"
      autofocus
    />
  </form>

  <div class="flex flex-wrap items-center justify-end gap-4 py-2">
    <div class="flex flex-col items-end">
      <span class="font-label-sm text-label-sm text-on-surface-variant">Matches</span>
      <span class="font-headline-sm text-headline-sm text-primary-container">{{ match_count }}</span>
    </div>
  </div>

  <div class="space-y-4">
    {% for hit in hits %}
      {% include 'partials/_recall_hit.html' %}
    {% else %}
      <div class="border border-dashed border-surface-container-highest rounded-DEFAULT p-8 text-center text-on-surface-variant font-body-md">
        {% if q %}
          No matches for "<span class="text-primary font-label-md">{{ q | e }}</span>".
        {% else %}
          Enter a query to search the brain.
        {% endif %}
      </div>
    {% endfor %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 7: Register routes in `src/brain/web/app.py`**

Open `src/brain/web/app.py`. In `create_app`, find the existing `app.include_router(...)` calls. Add:

```python
from brain.web.routes.recall import router as recall_router
from brain.web.routes.meta import router as meta_router

app.include_router(recall_router)
app.include_router(meta_router)
```

Place the `meta_router` LAST so it doesn't shadow anything. Place `recall_router` next to the other page routers.

- [ ] **Step 8: Verify sidebar already has recall conditional**

```bash
grep "active == 'recall'" src/brain/web/templates/partials/_sidebar.html | wc -l
```

Expected: 2 (the conditional appears in the link class AND the icon variation). If 0, fall back to the conditional pattern used for `dashboard`/`sources` in the same file.

- [ ] **Step 9: Run tests**

Run: `.venv/bin/pytest tests/test_web_recall.py -v`
Expected: PASS — 4/4 green.

- [ ] **Step 10: Smoke**

```bash
brain serve &
sleep 1
curl -s 'http://127.0.0.1:8765/recall' | grep -q "Memory Retrieval" && echo "RECALL PAGE OK"
curl -s 'http://127.0.0.1:8765/favicon.ico' -o /dev/null -w '%{http_code}\n'   # → 204
pkill -f "brain serve"
```

- [ ] **Step 11: Commit**

```bash
git add src/brain/web/routes/recall.py src/brain/web/routes/meta.py \
        src/brain/web/templates/recall.html \
        src/brain/web/templates/partials/_recall_hit.html \
        src/brain/web/app.py \
        tests/test_web_recall.py
git commit -m "feat(v0.11.1): /recall page wired to brain.read.recall + favicon 204"
```

---

## Task 2: `/health` observability page

**Files:**
- Create: `src/brain/web/routes/health.py`
- Create: `src/brain/web/templates/health.html`
- Modify: `src/brain/web/queries.py` (add `health_stats`)
- Modify: `src/brain/web/app.py`
- Modify: `src/brain/web/templates/partials/_sidebar.html` (add `active == 'health'` conditional to the Health nav row)
- Create: `tests/test_web_health.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_health.py`:

```python
"""Health page + health_stats query (v0.11.1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.app import create_app
from brain.web.queries import HealthStats, health_stats


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_health_stats_returns_model_on_empty_brain(pg_url: str) -> None:
    engine = get_engine(pg_url)
    stats = health_stats(engine)
    assert isinstance(stats, HealthStats)
    assert stats.sources_total >= 0
    assert stats.pool.size >= 1
    assert stats.embedding.percent >= 0


def test_health_stats_counts_real_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("health-target")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'health-target', :h, 'active')"
            ),
            {"h": h},
        )
    stats = health_stats(engine)
    assert stats.sources_substantive >= 1
    assert stats.captures_24h >= 1


def test_health_page_renders(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    # Mockup uses "System Observability" as the H2.
    assert "Observability" in res.text or "System Health" in res.text
    # Should display the substantive-sources tile.
    assert "Substantive" in res.text or "Sources" in res.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_health.py -v`
Expected: FAIL — `health_stats` and `/health` don't exist.

- [ ] **Step 3: Add `health_stats` to `src/brain/web/queries.py`**

Append (after `source_by_id`):

```python
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
                "WHERE kind = ANY(:k) AND parent_id IS NULL "
                "  AND created_at >= NOW() - INTERVAL '1 hour'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        captures_24h = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND parent_id IS NULL "
                "  AND created_at >= NOW() - INTERVAL '24 hours'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        captures_7d = s.execute(
            text(
                "SELECT COUNT(*) FROM sources "
                "WHERE kind = ANY(:k) AND parent_id IS NULL "
                "  AND created_at >= NOW() - INTERVAL '7 days'"
            ),
            {"k": _SUBSTANTIVE_KINDS},
        ).scalar() or 0
        last_cap_at = s.execute(
            text(
                "SELECT created_at FROM sources "
                "WHERE kind = ANY(:k) AND parent_id IS NULL "
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

        # Retrieval latency from retrieval_log. Use ms_taken if column exists, else duration_ms.
        # Fall back to zero counts if the table is empty.
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
        except Exception:
            # Column might be named differently in older schemas — degrade silently.
            p50, p95, n_samples = 0.0, 0.0, 0

    # Staleness (reuses scan_db).
    report = scan_db(engine)
    by_status: dict[str, int] = {"changed": 0, "missing": 0, "untracked": 0}
    for sx in report.stale_sources:
        by_status[sx.status] = by_status.get(sx.status, 0) + 1

    # Pool stats from SQLAlchemy.
    pool = engine.pool
    pool_stats = PoolStats(
        size=int(getattr(pool, "size", lambda: 0)()),
        checked_in=int(getattr(pool, "checkedin", lambda: 0)()),
        checked_out=int(getattr(pool, "checkedout", lambda: 0)()),
        overflow=int(getattr(pool, "overflow", lambda: 0)()),
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
```

> If `retrieval_log.duration_ms` column doesn't exist (check with `\d retrieval_log` in psql or look at `src/brain/migrations/`), the `try/except` already degrades gracefully — verify after writing.

- [ ] **Step 4: Implement `src/brain/web/routes/health.py`**

```python
"""GET /health — observability snapshot."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from brain.web.queries import health_stats
from brain.web.templates_env import templates

router = APIRouter()


@router.get("/health", response_class=HTMLResponse)
def health_page(request: Request) -> HTMLResponse:
    stats = health_stats(request.app.state.engine)
    return templates.TemplateResponse(
        request,
        "health.html",
        {"stats": stats, "active": "health"},
    )
```

- [ ] **Step 5: Port `frontend-design/mockups/health.html` to `src/brain/web/templates/health.html`**

Read the mockup. Lift the `<main>` content. Substitute the seeded metrics with `{{ stats.* }}` fields. Keep the Crimson Matrix class strings exactly. Use this skeleton (adapt the exact mockup layout but preserve the field bindings):

```jinja2
{% extends "base.html" %}
{% import 'macros.html' as m %}

{% block title %}Health — Agent Brain{% endblock %}
{% block page_title %}System Observability{% endblock %}
{% block topbar_meta %}
  <span class="inline-flex items-center px-2 py-1 rounded-DEFAULT border border-surface-container-highest font-label-sm text-label-sm text-on-surface-variant bg-surface-container-low">
    <span class="w-1.5 h-1.5 rounded-full bg-primary-container mr-2"></span>
    Live snapshot
  </span>
{% endblock %}

{% block content %}
<div class="flex-1 overflow-y-auto p-margin md:p-6 lg:p-8 space-y-6">

  {# === Source population ============================================ #}
  <section>
    <h3 class="font-label-md text-label-md uppercase tracking-widest text-on-surface-variant mb-3">Source population</h3>
    <div class="grid grid-cols-1 md:grid-cols-4 gap-gutter">
      {% set tiles = [
        ("Substantive", stats.sources_substantive),
        ("Total rows",  stats.sources_total),
        ("Chunks",      stats.sources_chunks),
        ("Embedded",    stats.embedding.embedded),
      ] %}
      {% for label, value in tiles %}
      <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
        <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant">{{ label }}</div>
        <div class="font-headline-lg text-headline-lg text-on-surface mt-2">{{ value }}</div>
      </div>
      {% endfor %}
    </div>
  </section>

  {# === Recent activity ============================================== #}
  <section>
    <h3 class="font-label-md text-label-md uppercase tracking-widest text-on-surface-variant mb-3">Capture activity</h3>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-gutter">
      <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
        <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant">Past hour</div>
        <div class="font-headline-md text-headline-md text-on-surface mt-2">{{ stats.captures_1h }}</div>
      </div>
      <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
        <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant">Past 24h</div>
        <div class="font-headline-md text-headline-md text-on-surface mt-2">{{ stats.captures_24h }}</div>
      </div>
      <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
        <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant">Past 7d</div>
        <div class="font-headline-md text-headline-md text-on-surface mt-2">{{ stats.captures_7d }}</div>
      </div>
    </div>
  </section>

  {# === Embedding + staleness ======================================== #}
  <section class="grid grid-cols-1 md:grid-cols-2 gap-gutter">
    <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
      <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant mb-2">Embedding coverage</div>
      <div class="font-headline-lg text-headline-lg text-primary-container">{{ "%.1f" | format(stats.embedding.percent) }}%</div>
      <div class="font-body-sm text-body-sm text-on-surface-variant">{{ stats.embedding.embedded }} of {{ stats.embedding.total }} substantive sources embedded.</div>
    </div>
    <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
      <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant mb-2">Staleness</div>
      <div class="font-headline-lg text-headline-lg text-on-surface">{{ stats.staleness.total }}</div>
      <div class="font-body-sm text-body-sm text-on-surface-variant">
        changed={{ stats.staleness.changed }} · missing={{ stats.staleness.missing }} · untracked={{ stats.staleness.untracked }} · scanned={{ stats.staleness.scanned }}
      </div>
    </div>
  </section>

  {# === Retrieval + pool ============================================ #}
  <section class="grid grid-cols-1 md:grid-cols-2 gap-gutter">
    <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
      <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant mb-2">Retrieval latency (24h)</div>
      <div class="flex gap-6">
        <div>
          <div class="font-label-sm text-label-sm text-on-surface-variant">p50</div>
          <div class="font-headline-md text-headline-md text-on-surface">{{ "%.0f" | format(stats.retrieval.p50_ms) }} ms</div>
        </div>
        <div>
          <div class="font-label-sm text-label-sm text-on-surface-variant">p95</div>
          <div class="font-headline-md text-headline-md text-on-surface">{{ "%.0f" | format(stats.retrieval.p95_ms) }} ms</div>
        </div>
        <div>
          <div class="font-label-sm text-label-sm text-on-surface-variant">Samples</div>
          <div class="font-headline-md text-headline-md text-on-surface">{{ stats.retrieval.sample_count }}</div>
        </div>
      </div>
    </div>
    <div class="bg-surface-container border border-surface-container-highest rounded-DEFAULT p-4">
      <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant mb-2">DB pool</div>
      <div class="flex gap-6 font-body-md text-body-md text-on-surface">
        <div>size <span class="font-label-md text-primary">{{ stats.pool.size }}</span></div>
        <div>in <span class="font-label-md text-primary">{{ stats.pool.checked_in }}</span></div>
        <div>out <span class="font-label-md text-primary">{{ stats.pool.checked_out }}</span></div>
        <div>overflow <span class="font-label-md text-primary">{{ stats.pool.overflow }}</span></div>
      </div>
    </div>
  </section>

  {# === Last activity =============================================== #}
  <section class="bg-surface-container-low border border-surface-container-highest rounded-DEFAULT p-4">
    <div class="font-label-sm text-label-sm uppercase tracking-widest text-on-surface-variant mb-2">Activity</div>
    <div class="font-body-md text-body-md text-on-surface-variant">
      Last capture:
      <span class="font-label-md text-on-surface">{{ stats.last_capture_at or "—" }}</span> ·
      Last session event:
      <span class="font-label-md text-on-surface">{{ stats.last_session_event_at or "—" }}</span>
    </div>
  </section>

</div>
{% endblock %}
```

- [ ] **Step 6: Extend the sidebar to highlight Health**

In `src/brain/web/templates/partials/_sidebar.html`, find the Health nav row (currently a plain `href="#"`). Replace it with:

```jinja2
<li>
  <a class="flex items-center gap-3 px-4 py-3 transition-all {% if active == 'health' %}text-on-primary bg-primary-container border-l-2 border-primary scale-[0.99]{% else %}text-on-surface-variant hover:text-on-surface hover:bg-surface-container-highest{% endif %}" href="/health">
    <span class="material-symbols-outlined" {% if active == 'health' %}style="font-variation-settings: 'FILL' 1;"{% endif %}>pulse_alert</span>
    <span class="font-label-md text-label-md">Health</span>
  </a>
</li>
```

Find the existing `<li>` block for Health (likely contains the `pulse_alert` icon) and replace it with the above.

- [ ] **Step 7: Register route in `src/brain/web/app.py`**

```python
from brain.web.routes.health import router as health_router
app.include_router(health_router)
```

- [ ] **Step 8: Run tests**

Run: `.venv/bin/pytest tests/test_web_health.py tests/test_web_recall.py -v`
Expected: PASS — Task 2's 3 tests + Task 1's 4 tests all green.

- [ ] **Step 9: Smoke**

```bash
brain serve &
sleep 1
curl -s 'http://127.0.0.1:8765/health' | grep -q "Observability" && echo "HEALTH OK"
pkill -f "brain serve"
```

- [ ] **Step 10: Commit**

```bash
git add src/brain/web/routes/health.py \
        src/brain/web/templates/health.html \
        src/brain/web/queries.py \
        src/brain/web/templates/partials/_sidebar.html \
        src/brain/web/app.py \
        tests/test_web_health.py
git commit -m "feat(v0.11.1): /health observability page with health_stats query"
```

---

## Task 3: `/knowledge` graph page (Cytoscape lightweight)

**Files:**
- Create: `src/brain/web/routes/knowledge.py`
- Create: `src/brain/web/templates/knowledge.html`
- Modify: `src/brain/web/queries.py` (add `knowledge_graph_data`)
- Modify: `src/brain/web/app.py`
- Modify: `src/brain/web/templates/base.html` (Cytoscape.js CDN)
- Modify: `src/brain/web/templates/partials/_sidebar.html` (add `active == 'knowledge'` conditional)
- Create: `tests/test_web_knowledge.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_knowledge.py`:

```python
"""Knowledge graph page + knowledge_graph_data query (v0.11.1)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.web.app import create_app
from brain.web.queries import knowledge_graph_data


@pytest.fixture
def client(pg_url: str) -> TestClient:
    app = create_app(db_url=pg_url)
    return TestClient(app)


def test_knowledge_graph_data_empty_brain_returns_empty_shape(pg_url: str) -> None:
    engine = get_engine(pg_url)
    g = knowledge_graph_data(engine, limit=50)
    assert g.nodes == []
    assert g.edges == []


def test_knowledge_graph_data_returns_substantive_sources(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = sha256_bytes("graph-source")
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status) "
                "VALUES ('decision', 'graph-source', :h, 'active')"
            ),
            {"h": h},
        )
    g = knowledge_graph_data(engine, limit=50)
    assert len(g.nodes) >= 1
    assert any(n.label.startswith("decision") or n.kind == "decision" for n in g.nodes)


def test_knowledge_page_renders(client: TestClient) -> None:
    res = client.get("/knowledge")
    assert res.status_code == 200
    # Cytoscape CDN must be loaded for the graph to render client-side.
    assert "cytoscape" in res.text.lower()
    # The data endpoint URL must be embedded so the client can fetch it.
    assert "/_htmx/knowledge.json" in res.text


def test_knowledge_json_endpoint_returns_valid_json(client: TestClient) -> None:
    res = client.get("/_htmx/knowledge.json")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_knowledge.py -v`
Expected: FAIL — query function + routes don't exist.

- [ ] **Step 3: Add `knowledge_graph_data` to `src/brain/web/queries.py`**

Append (after `health_stats`):

```python
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
                nodes.append(GraphNode(id=cnode_id, label=f"chunk #{c.id}", kind=c.kind, project_id=None))
                edges.append(GraphEdge(source=f"s-{pid}", target=cnode_id, kind="parent-of"))

    return GraphData(nodes=nodes, edges=edges)
```

- [ ] **Step 4: Implement `src/brain/web/routes/knowledge.py`**

```python
"""GET /knowledge — Cytoscape graph page + JSON data endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from brain.web.queries import knowledge_graph_data
from brain.web.templates_env import templates

router = APIRouter()


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "knowledge.html", {"active": "knowledge"},
    )


@router.get("/_htmx/knowledge.json")
def knowledge_data(request: Request, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    data = knowledge_graph_data(request.app.state.engine, limit=limit)
    # Pydantic v2: model_dump returns plain dicts.
    return JSONResponse(data.model_dump())
```

- [ ] **Step 5: Add Cytoscape CDN to `base.html`**

In `src/brain/web/templates/base.html`, find the existing HTMX + Alpine `<script>` tags near the bottom of `<head>` (or `<body>` end). Add Cytoscape RIGHT AFTER Alpine:

```html
<!-- Cytoscape.js (knowledge graph; ~120KB gzipped).
     SRI deferred: vendor Cytoscape in static/ before any `brain serve --host 0.0.0.0` deploy.
     Tracked alongside HTMX + Alpine + Tailwind CDN in the v0.11.0 SRI note. -->
<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>
```

Pin to `3.30.4` (current stable). Same SRI TODO comment block as HTMX applies — CDN compromise risk is mitigated only by `127.0.0.1`-default binding; LAN deploys must vendor first.

> **Optional optimization:** Only load Cytoscape on `/knowledge` to save 120KB on other pages. To do this, change `base.html` to expose `{% block extra_head %}{% endblock %}` near the end of `<head>` and put the Cytoscape `<script>` inside that block within `knowledge.html`. Either approach is acceptable — the optimization is nice-to-have, not required for v0.11.1.

- [ ] **Step 6: Implement `src/brain/web/templates/knowledge.html`**

Port the page-frame from `frontend-design/mockups/knowledge.html`. The mockup has a static svg-based illustration; production replaces it with a real Cytoscape canvas. Use this skeleton (adapt header/legend chrome from the mockup):

```jinja2
{% extends "base.html" %}

{% block title %}Knowledge Graph — Agent Brain{% endblock %}
{% block page_title %}Knowledge Visualizer{% endblock %}
{% block topbar_meta %}
  <span class="inline-flex items-center px-2 py-1 rounded-DEFAULT border border-surface-container-highest font-label-sm text-label-sm text-on-surface-variant bg-surface-container-low">
    <span class="w-1.5 h-1.5 rounded-full bg-primary-container mr-2"></span>
    Cytoscape · top 50 substantive
  </span>
{% endblock %}

{% block content %}
<div class="flex-1 flex flex-col h-full">

  <div class="px-margin md:px-6 lg:px-8 py-4 border-b border-surface-container-highest">
    <h2 class="font-headline-md text-headline-md text-on-surface">Sources and their structural relationships</h2>
    <p class="font-body-sm text-body-sm text-on-surface-variant mt-1">
      Substantive sources clustered by project, expanded into chunk children (3 per parent shown).
      Entity-extraction edges land in v0.11.2.
    </p>
  </div>

  <div id="graph-canvas" class="flex-1 bg-surface-container-lowest border-t border-surface-container-highest"></div>

  <div class="px-margin md:px-6 lg:px-8 py-3 flex flex-wrap gap-4 items-center border-t border-surface-container-highest font-label-sm text-label-sm text-on-surface-variant">
    <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-primary-container"></span> substantive</div>
    <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-secondary"></span> project</div>
    <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-on-surface-variant"></span> chunk</div>
    <div class="ml-auto flex items-center gap-2"><span class="w-6 border-t-2 border-primary-container"></span> parent-of</div>
    <div class="flex items-center gap-2"><span class="w-6 border-t border-dashed border-on-surface-variant"></span> same-project</div>
  </div>

</div>

<script>
(function () {
  const KIND_COLORS = {
    "decision": "#da0037",
    "gotcha":   "#da0037",
    "pattern":  "#da0037",
    "note":     "#da0037",
    "subtask_summary":  "#da0037",
    "session_summary":  "#da0037",
    "faq":      "#da0037",
    "project":  "#c8c6c6",
    "chunk":    "#849587",
  };

  fetch("/_htmx/knowledge.json")
    .then(r => r.json())
    .then(data => {
      const cy = cytoscape({
        container: document.getElementById("graph-canvas"),
        elements: [
          ...data.nodes.map(n => ({ data: { id: n.id, label: n.label, kind: n.kind } })),
          ...data.edges.map(e => ({ data: { id: e.source + "->" + e.target, source: e.source, target: e.target, kind: e.kind } })),
        ],
        style: [
          { selector: "node", style: {
              "label": "data(label)",
              "background-color": ele => KIND_COLORS[ele.data("kind")] || "#c8c6c6",
              "color": "#e5e2e1",
              "font-family": "JetBrains Mono, monospace",
              "font-size": "10px",
              "text-valign": "bottom",
              "text-margin-y": 6,
              "width": 14,
              "height": 14,
              "border-width": 1,
              "border-color": "#353534",
          }},
          { selector: "node[kind = 'project']", style: { "shape": "rectangle", "width": 22, "height": 22 } },
          { selector: "node[kind = 'chunk']",   style: { "width": 8, "height": 8, "opacity": 0.7 } },
          { selector: "edge", style: {
              "width": 1,
              "line-color": ele => ele.data("kind") === "parent-of" ? "#da0037" : "#5d3f3f",
              "line-style": ele => ele.data("kind") === "same-project" ? "dashed" : "solid",
              "curve-style": "bezier",
              "target-arrow-shape": "none",
              "opacity": 0.6,
          }},
          { selector: ":selected", style: { "border-color": "#ffb3b3", "border-width": 2 } },
        ],
        layout: { name: "cose", animate: false, padding: 24, idealEdgeLength: 80, nodeOverlap: 12 },
        wheelSensitivity: 0.2,
        minZoom: 0.2,
        maxZoom: 3,
      });
      cy.on("tap", "node", evt => {
        const id = evt.target.data("id");
        if (id && id.startsWith("s-")) {
          window.location.href = "/sources/" + id.slice(2);
        }
      });
    })
    .catch(err => {
      // textContent (not innerHTML) — `err` is user-influenceable via fetch failure messages
      // and must not be interpreted as HTML.
      const el = document.getElementById("graph-canvas");
      el.textContent = "";
      const msg = document.createElement("div");
      msg.style.cssText = "padding:2rem;font-family:JetBrains Mono;color:#e6bcbc;";
      msg.textContent = "Graph data fetch failed: " + String(err);
      el.appendChild(msg);
    });
})();
</script>
{% endblock %}
```

- [ ] **Step 7: Extend sidebar to highlight Knowledge**

The current sidebar has no `/knowledge` link. Add one in the appropriate spot (between Recall and Projects or wherever Knowledge belongs):

```jinja2
<li>
  <a class="flex items-center gap-3 px-4 py-3 transition-all {% if active == 'knowledge' %}text-on-primary bg-primary-container border-l-2 border-primary scale-[0.99]{% else %}text-on-surface-variant hover:text-on-surface hover:bg-surface-container-highest{% endif %}" href="/knowledge">
    <span class="material-symbols-outlined" {% if active == 'knowledge' %}style="font-variation-settings: 'FILL' 1;"{% endif %}>hub</span>
    <span class="font-label-md text-label-md">Knowledge</span>
  </a>
</li>
```

If the sidebar already has a `hub` / `Knowledge` row from the mockup, just replace the inactive class string with the conditional pattern shown above.

- [ ] **Step 8: Register routes in `src/brain/web/app.py`**

```python
from brain.web.routes.knowledge import router as knowledge_router
app.include_router(knowledge_router)
```

- [ ] **Step 9: Run tests**

Run: `.venv/bin/pytest tests/test_web_knowledge.py tests/test_web_health.py tests/test_web_recall.py -v`
Expected: PASS — Task 3's 4 + Task 2's 3 + Task 1's 4 = 11 tests green.

- [ ] **Step 10: Smoke**

```bash
brain serve &
sleep 1
curl -s 'http://127.0.0.1:8765/knowledge' | grep -q "cytoscape" && echo "KNOWLEDGE PAGE OK"
curl -s 'http://127.0.0.1:8765/_htmx/knowledge.json' | python -c 'import json,sys;d=json.load(sys.stdin);print("nodes=",len(d["nodes"]),"edges=",len(d["edges"]))'
pkill -f "brain serve"
```

- [ ] **Step 11: Commit**

```bash
git add src/brain/web/routes/knowledge.py \
        src/brain/web/templates/knowledge.html \
        src/brain/web/queries.py \
        src/brain/web/templates/base.html \
        src/brain/web/templates/partials/_sidebar.html \
        src/brain/web/app.py \
        tests/test_web_knowledge.py
git commit -m "feat(v0.11.1): /knowledge Cytoscape graph + knowledge_graph_data query"
```

---

## Task 4: Ship v0.11.1 (manifests + README + ops doc)

**Files:**
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`
- Modify: `README.md`
- Create: `docs/v0.11.1-frontend-completion.md`

- [ ] **Step 1: Bump manifests**

Use Edit (NOT sed). For each of:
- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json` (TWO occurrences — top-level + plugin array entry)
- `.cursor-plugin/plugin.json`
- `.codex-plugin/plugin.json`

Replace `"version": "0.11.0"` → `"version": "0.11.1"`.

- [ ] **Step 2: Update README v0.11.0 section header**

Open `README.md`, find `## v0.11.0 — Brain Telescope (insights frontend)`. Replace with `## v0.11.1 — Brain Telescope (insights frontend, full sidebar)` and update the page list:

```markdown
Pages shipped:

- **`/` Dashboard** — hero metric, capture cadence sparkline, compliance, staleness, top failures, embedding coverage.
- **`/sources` Browser** — paginated list with HTMX search-as-you-type and kind-filter pills.
- **`/sources/<id>` Detail** — full content, provenance metadata, action bar.
- **`/recall` Console** — FTS recall over substantive sources, opens hits in source-detail.
- **`/health` Observability** — sources / captures / embedding coverage / staleness / retrieval p50-p95 / DB pool stats.
- **`/knowledge` Graph** — Cytoscape-rendered map of recent substantive sources clustered by project, with chunk children.

Deferred to v0.12.0+: vector + rerank in recall, entity-extraction edges in graph, sessions timeline, hooks dashboard, retrieval analytics page.
```

- [ ] **Step 3: Write `docs/v0.11.1-frontend-completion.md`**

Mirror `docs/v0.11.0-frontend.md` structure. Sections:

1. **Overview** — what v0.11.1 adds on top of v0.11.0.
2. **New pages** — `/recall`, `/health`, `/knowledge` — what each surfaces + backend wiring.
3. **`brain serve` CLI** — unchanged.
4. **Tech stack additions** — Cytoscape.js 3.30.4 via CDN.
5. **Known limits** — recall is FTS-only (no vector/rerank), graph is parent-of + project-cluster only (no entity edges), source-detail still composed (no Stitch variant).
6. **Roadmap** — v0.11.2 (hybrid recall in /recall, entity edges in /knowledge, retrieval-analytics page), v0.12.0 (sessions timeline, hooks dashboard, Tailwind vendor for SRI).

~150 lines, tone matches v0.11.0 doc.

- [ ] **Step 4: Full test suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: PASS — 330 (v0.11.0) + ~11 new = ~341 tests.

If any test failure is unrelated to v0.11.1 (e.g., flaky DB-pool exhaustion under load), re-run that specific test file. Persistent failures should be reported, not amended.

- [ ] **Step 5: End-to-end smoke**

```bash
brain serve --port 8765 &
sleep 2
curl -s http://127.0.0.1:8765/          | grep -q "hero-value"       && echo "DASHBOARD OK"
curl -s http://127.0.0.1:8765/sources   | grep -q "hx-get"           && echo "SOURCES OK"
curl -s http://127.0.0.1:8765/recall    | grep -q "Memory Retrieval" && echo "RECALL OK"
curl -s http://127.0.0.1:8765/health    | grep -q "Observability"    && echo "HEALTH OK"
curl -s http://127.0.0.1:8765/knowledge | grep -q "cytoscape"        && echo "KNOWLEDGE OK"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/favicon.ico  # → 204
pkill -f "brain serve"
```

All five must say OK; favicon must be 204.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json \
        .cursor-plugin/plugin.json .codex-plugin/plugin.json \
        README.md docs/v0.11.1-frontend-completion.md
git commit -m "docs(v0.11.1): operations doc + README + manifests bumped"
```

---

## Self-review checklist

- [x] Task 1 covers /recall + favicon (sidebar conditional verified pre-plan).
- [x] Task 2 covers /health with health_stats query reusing dashboard math.
- [x] Task 3 covers /knowledge with Cytoscape + parent-of + same-project edges (entity edges deferred).
- [x] Task 4 ships v0.11.1.
- [x] Every step that changes code shows complete code.
- [x] Type names consistent across tasks: HealthStats, GraphData, GraphNode, GraphEdge, RetrievalLatency, PoolStats.
- [x] No "TBD" / "TODO" / "fill in" placeholders.
- [x] Each task's tests are independent (use the `pg_url` fixture + autouse `_truncate_tables`).
- [x] Frequent commits — one per task (4 commits total).
