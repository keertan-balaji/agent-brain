"""FastAPI application factory + route registration."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from brain.db import get_engine


def create_app(*, db_url: str | None = None) -> FastAPI:
    """Build the Telescope FastAPI app.

    db_url is optional; if absent, `brain.config.load_config().db_url` is used.
    Lets tests pass a per-test pg_url.
    """
    if db_url is None:
        from brain.config import load_config
        db_url = load_config().db_url

    app = FastAPI(
        title="agent-brain",
        description="Brain Telescope — local insights frontend",
        version="0.11.0",
    )

    # Persist engine on app.state so route handlers can access it.
    app.state.engine = get_engine(db_url)

    web_root = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=str(web_root / "static")), name="static")

    from brain.web.routes.api import router as api_router
    from brain.web.routes.dashboard import router as dashboard_router
    from brain.web.routes.health import router as health_router
    from brain.web.routes.htmx import router as htmx_router
    from brain.web.routes.knowledge import router as knowledge_router
    from brain.web.routes.meta import router as meta_router
    from brain.web.routes.recall import router as recall_router
    from brain.web.routes.sources import router as sources_router
    app.include_router(dashboard_router)
    app.include_router(sources_router)
    app.include_router(htmx_router)
    app.include_router(recall_router)
    app.include_router(health_router)
    app.include_router(knowledge_router)
    app.include_router(api_router)
    app.include_router(meta_router)

    return app
