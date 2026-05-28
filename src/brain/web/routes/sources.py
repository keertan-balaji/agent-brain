"""GET /sources, GET /sources/<id>."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from brain.web.queries import list_sources, source_by_id
from brain.web.templates_env import templates

router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
def sources(
    request: Request,
    kind: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    page_data = list_sources(request.app.state.engine, kind=kind, page=page, per_page=30)
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"page": page_data, "kind": kind, "active": "sources"},
    )


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def source_detail(request: Request, source_id: int) -> HTMLResponse:
    src = source_by_id(request.app.state.engine, source_id=source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return templates.TemplateResponse(
        request,
        "source_detail.html",
        {"source": src, "active": "sources"},
    )
