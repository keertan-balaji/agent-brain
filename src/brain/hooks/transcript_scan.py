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

# Noise filters (v0.8.5) — Stop hook false positives observed in real sessions.
# Each filter trims captures that look like failures but aren't worth recording.

# 1. System-injected metadata that ends up in user content (IDE markers, harness
#    reminders, system reminders). These are never real failures; treating them
#    as target_problem creates rows that are pure noise.
_SYSTEM_MARKER_RE = re.compile(
    r"^\s*<(ide_opened_file|system-reminder|task-notification|command-message|command-name)\b",
    re.IGNORECASE,
)

# 2. CLI-usage errors — "Try 'brain --help'", "Usage: brain decide [OPTIONS] TITLE",
#    "Error: Missing argument 'TITLE'". These are legitimate flag/arg mistakes,
#    not real failures worth flagging for retry-protection.
_CLI_USAGE_ERROR_RE = re.compile(
    r"(Usage:\s+\S|Try ['\"]?\S+ --help|Error: (Missing|Invalid|No such (option|command|argument)))",
    re.IGNORECASE,
)

# 3. Bash exit code 1 on commands that conventionally exit-1 on no-match
#    (grep, find -quit, test, head/tail on pipe closure). Hard to detect
#    without parsing the command; conservatively skip Bash exits where the
#    output is short AND non-traceback. Captured below in _is_noise.

# 4. Tool names that should never be flagged. The agent invoking brain CLI to
#    capture failures should not auto-flag the brain CLI invocations themselves
#    (recursive noise). TodoWrite / Skill etc. are agent-internal and don't
#    represent user-visible failures.
_TOOL_BLOCKLIST = frozenset({
    "TodoWrite", "Skill", "AskUserQuestion", "ToolSearch",
    "TaskStop", "ScheduleWakeup", "PushNotification",
})


def _is_noise(target_problem: str, attempted_approach: str, outcome_evidence: str) -> bool:
    """True if this failure candidate looks like noise rather than a real failure.

    Filters (v0.8.5) — calibrated against ~60% FP rate observed in early sessions:
      - System-injected target_problem (IDE markers, system reminders)
      - Empty / whitespace-only target_problem
      - Recursive Bash invocations of the brain CLI (self-flagging)
      - Blocklisted tool names (TodoWrite etc — agent-internal)
      - CLI usage errors (Usage:, Try '... --help', Error: Missing/Invalid argument)
      - Very short outcome evidence with no traceback signature
    """
    if not target_problem.strip():
        return True
    if _SYSTEM_MARKER_RE.match(target_problem):
        return True
    tool, _, command = attempted_approach.partition(": ")
    if tool in _TOOL_BLOCKLIST:
        return True
    # Bash invocations of the brain CLI itself — agent flagging its own brain calls.
    if tool == "Bash" and command.lstrip().startswith("brain "):
        return True
    # CLI usage errors are agent flag-mistakes, not real failures.
    if _CLI_USAGE_ERROR_RE.search(outcome_evidence):
        return True
    # Very short outcome that doesn't contain a real failure signature.
    # grep no-match (exit 1, empty output) lands here.
    if len(outcome_evidence.strip()) < 20 and not _FAILURE_PATTERNS.search(outcome_evidence):
        return True
    return False


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
                    target = _truncate(last_user_prompt, 400)
                    approach_trunc = _truncate(approach, 200)
                    evidence_trunc = _truncate(body, 600)
                    if _is_noise(target, approach_trunc, evidence_trunc):
                        continue
                    seen_approaches.add(approach)
                    candidates.append(
                        FailureCandidate(
                            target_problem=target,
                            attempted_approach=approach_trunc,
                            outcome_evidence=evidence_trunc,
                        )
                    )
            else:
                last_user_prompt = _flatten_user_content(content)
        elif ttype == "assistant":
            tu = _extract_tool_use(msg.get("content"))
            if tu is not None:
                last_tool_use = tu

    return candidates
