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
