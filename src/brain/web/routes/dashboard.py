"""GET / — dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from brain.web.queries import dashboard_stats
from brain.web.templates_env import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    stats = dashboard_stats(request.app.state.engine)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"stats": stats, "active": "dashboard"},
    )
