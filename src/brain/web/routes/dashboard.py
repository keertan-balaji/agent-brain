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
        request,
        "dashboard.html",
        {
            "hero": {"total": 0, "delta_week": 0, "last_capture": "—"},
            "cards": {},
            "failures": [],
        },
    )
