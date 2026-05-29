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
