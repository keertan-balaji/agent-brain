"""HTMX partial endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from brain.web.queries import list_sources
from brain.web.templates_env import templates

router = APIRouter(prefix="/_htmx")


@router.get("/health")
def htmx_health() -> dict[str, bool]:
    return {"ok": True}


@router.get("/sources", response_class=HTMLResponse)
def htmx_sources(
    request: Request,
    q: str = Query("", description="Free-text filter applied in-Python (FTS in v0.11.1)"),
    kind: str | None = Query(None),
    embedded_only: bool = Query(False),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    engine = request.app.state.engine
    result = list_sources(engine, kind=kind, embedded_only=embedded_only, page=page, per_page=30)
    if q:
        q_low = q.lower()
        result.rows = [
            r for r in result.rows
            if q_low in (r.content_preview or "").lower()
            or q_low in (r.uri or "").lower()
        ]
    return templates.TemplateResponse(
        request, "partials/_source_rows.html", {"rows": result.rows},
    )
