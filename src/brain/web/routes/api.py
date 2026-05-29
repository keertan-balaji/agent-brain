"""JSON/HTMX action endpoints under /api.

Spec: v0.11.0 — Telescope action bar.
- `POST /api/sources/{id}/invalidate` sets t_valid_to=now() directly. Per the
  spec's "Known limits / gaps", this does not yet route through
  `brain.write.invalidate` and does not emit a session_event. Behaviour is
  correct; the helper handoff is a v0.11.1 task.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from brain.db import session_scope

router = APIRouter(prefix="/api")


@router.post("/sources/{source_id}/invalidate", response_class=HTMLResponse)
def invalidate_source(request: Request, source_id: int) -> HTMLResponse:
    engine = request.app.state.engine
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "UPDATE sources SET t_valid_to = :now "
                "WHERE id = :id AND t_valid_to IS NULL RETURNING id"
            ),
            {"now": datetime.now(timezone.utc), "id": source_id},
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Source not found or already invalidated")
    # HTMX swap target — replace the action bar pills with an invalidated marker.
    return HTMLResponse(
        '<span class="px-2 py-0.5 border border-error/40 text-error '
        'font-label-sm text-label-sm rounded uppercase">Invalidated</span>'
    )
