"""Cross-cutting meta endpoints (favicon, robots.txt etc.)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Silence the browser's automatic /favicon.ico probe.

    Returning 204 No Content stops browsers from logging a 404 and is cheaper
    than serving a real icon for a CLI-style local tool.
    """
    return Response(status_code=204)
