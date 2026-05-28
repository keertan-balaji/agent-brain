"""HTMX partial endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/_htmx")


@router.get("/health")
def htmx_health() -> dict:
    return {"ok": True}
