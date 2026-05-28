"""GET / — dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from brain.web.templates_env import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    # For Task 1, stub out the stats — Task 2 wires the live queries.
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "hero": {"total": 0, "delta_week": 0, "last_capture": "—"},
            "cards": {},
            "failures": [],
        },
    )
