"""Pydantic schemas for hook stdin payloads. Validate Claude Code 2.1.150 shapes."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from brain.hooks.contracts import (
    PreCompactInput,
    SessionEndInput,
    SessionStartInput,
    StopInput,
    UserPromptSubmitInput,
)


def test_session_start_input_parses_real_payload() -> None:
    raw = json.dumps(
        {
            "session_id": "0668cf02-bc9d-4f33-a8ed-a9c16df53222",
            "transcript_path": "/home/keertan/.claude/projects/-home-keertan-codes-brain/0668cf02.jsonl",
            "cwd": "/home/keertan/codes/brain",
            "hook_event_name": "SessionStart",
            "source": "resume",
            "model": "claude-opus-4-7[1m]",
        }
    )
    parsed = SessionStartInput.model_validate_json(raw)
    assert parsed.session_id == "0668cf02-bc9d-4f33-a8ed-a9c16df53222"
    assert parsed.source == "resume"
    assert parsed.cwd == "/home/keertan/codes/brain"


def test_session_start_input_accepts_known_sources() -> None:
    for src in ("startup", "resume", "compact", "clear"):
        SessionStartInput.model_validate({
            "session_id": "x",
            "transcript_path": "/tmp/x.jsonl",
            "cwd": "/tmp",
            "hook_event_name": "SessionStart",
            "source": src,
        })


def test_session_start_input_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        SessionStartInput.model_validate({
            "session_id": "x",
            "transcript_path": "/tmp/x.jsonl",
            "cwd": "/tmp",
            "hook_event_name": "SessionStart",
            "source": "BOGUS",
        })


def test_user_prompt_submit_parses() -> None:
    payload = {
        "session_id": "abc",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "UserPromptSubmit",
        "prompt": "hello there",
    }
    parsed = UserPromptSubmitInput.model_validate(payload)
    assert parsed.prompt == "hello there"


def test_pre_compact_parses() -> None:
    payload = {
        "session_id": "abc",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "hook_event_name": "PreCompact",
        "trigger": "manual",
        "custom_instructions": "preserve decisions",
    }
    parsed = PreCompactInput.model_validate(payload)
    assert parsed.trigger == "manual"


def test_stop_and_session_end_parse() -> None:
    base = {
        "session_id": "abc",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
    }
    StopInput.model_validate({**base, "hook_event_name": "Stop", "stop_hook_active": False})
    SessionEndInput.model_validate({**base, "hook_event_name": "SessionEnd", "reason": "clear"})
