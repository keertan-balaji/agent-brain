"""Shared Jinja2 environment for all routes."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["app_version"] = "v0.11.0"
