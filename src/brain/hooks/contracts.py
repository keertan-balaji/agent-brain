"""Pydantic schemas for Claude Code hook stdin payloads.

Shapes derived empirically from probe in Phase 3a-1 planning. Fields that
Claude Code may add later are tolerated via `model_config = {extra: 'allow'}`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SessionSource = Literal["startup", "resume", "compact", "clear"]
PreCompactTrigger = Literal["manual", "auto"]


class _HookBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str
    transcript_path: str
    cwd: str
    hook_event_name: str


class SessionStartInput(_HookBase):
    source: SessionSource
    model: str | None = None


class SessionEndInput(_HookBase):
    reason: str | None = None


class UserPromptSubmitInput(_HookBase):
    prompt: str


class StopInput(_HookBase):
    stop_hook_active: bool = False


class PreCompactInput(_HookBase):
    trigger: PreCompactTrigger | None = None
    custom_instructions: str | None = None


class SessionStartOutput(BaseModel):
    """Schema for the stdout JSON SessionStart emits."""

    hookSpecificOutput: dict
