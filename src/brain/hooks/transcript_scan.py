"""Transcript scanner for Stop hook (Phase 3a-2).

Walks the last N lines of a Claude Code transcript JSONL and emits
FailureCandidate triples for tool_results that look like failures. Pure
function — caller passes a Path, gets a list back. Silent on any error
(missing file, malformed JSON, unexpected schema) — hooks must never break
the user's session.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_FAILURE_PATTERNS = re.compile(
    r"^\s*(Traceback|Error|ERROR|FATAL|FAILED)\b"
    r"|\bcommand not found\b"  # shells emit this mid-line ("bash: foo: command not found")
    r"|\bExit\s+code\s*[:=]?\s*[1-9]",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class FailureCandidate:
    target_problem: str
    attempted_approach: str
    outcome_evidence: str


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n]


def _flatten_user_content(content: object) -> str:
    """User messages may be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return ""


def _extract_tool_use(content: object) -> tuple[str, str] | None:
    """Returns (tool_name, command_or_first_arg_summary) from an assistant content list."""
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = str(block.get("name", "unknown"))
            inp = block.get("input") or {}
            summary = ""
            if isinstance(inp, dict):
                # Prefer 'command' (Bash); else first string-valued arg.
                if "command" in inp and isinstance(inp["command"], str):
                    summary = inp["command"]
                else:
                    for v in inp.values():
                        if isinstance(v, str):
                            summary = v
                            break
            return name, summary
    return None


def _extract_tool_result(content: object) -> tuple[bool, str] | None:
    """Returns (is_error, content_text) for user messages carrying tool_result blocks."""
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            is_error = bool(block.get("is_error", False))
            raw = block.get("content", "")
            if isinstance(raw, list):
                text_parts: list[str] = []
                for b in raw:
                    if isinstance(b, dict) and b.get("type") == "text":
                        text_parts.append(str(b.get("text", "")))
                raw = "\n".join(text_parts)
            return is_error, str(raw)
    return None


def _looks_like_failure(is_error: bool, text: str) -> bool:
    if is_error:
        return True
    if _FAILURE_PATTERNS.search(text):
        return True
    return False


def scan_for_failures(path: Path, *, max_lines: int = 200) -> list[FailureCandidate]:
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = raw.splitlines()[-max_lines:]
    candidates: list[FailureCandidate] = []
    last_user_prompt = ""
    last_tool_use: tuple[str, str] | None = None
    seen_approaches: set[str] = set()  # in-memory dedup within this scan

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue

        msg = obj.get("message") or {}
        if not isinstance(msg, dict):
            continue

        ttype = obj.get("type")
        if ttype == "user":
            # May be a plain user prompt OR a tool_result wrapper.
            content = msg.get("content")
            tr = _extract_tool_result(content)
            if tr is not None:
                is_error, body = tr
                if last_tool_use is not None and _looks_like_failure(is_error, body):
                    name, cmd = last_tool_use
                    approach = f"{name}: {cmd}"
                    if approach in seen_approaches:
                        continue
                    seen_approaches.add(approach)
                    candidates.append(
                        FailureCandidate(
                            target_problem=_truncate(last_user_prompt, 400),
                            attempted_approach=_truncate(approach, 200),
                            outcome_evidence=_truncate(body, 600),
                        )
                    )
            else:
                last_user_prompt = _flatten_user_content(content)
        elif ttype == "assistant":
            tu = _extract_tool_use(msg.get("content"))
            if tu is not None:
                last_tool_use = tu

    return candidates
