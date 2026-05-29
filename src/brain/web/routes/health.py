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
