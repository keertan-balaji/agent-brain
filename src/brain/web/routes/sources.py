"""GET /sources, GET /sources/<id>."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from brain.web.templates_env import templates

router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
def sources(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"rows": [], "total": 0, "page": 1, "total_pages": 1},
    )


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def source_detail(request: Request, source_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "source_detail.html",
        {"source": {"id": source_id, "kind": "—", "content": "Not found"}},
    )
