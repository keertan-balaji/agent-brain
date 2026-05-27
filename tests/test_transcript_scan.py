"""src/brain/hooks/transcript_scan.py — JSONL tail + failure-signature detection."""

from __future__ import annotations

import json
from pathlib import Path

from brain.hooks.transcript_scan import FailureCandidate, scan_for_failures


def _write_transcript(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def test_scan_detects_is_error_tool_result(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(p, [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": "run the tests"}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "pytest tests/test_x.py"}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result", "is_error": True,
                                  "content": "Traceback (most recent call last):\n  ..."}]}},
    ])
    cands = scan_for_failures(p, max_lines=200)
    assert len(cands) == 1
    c = cands[0]
    assert "run the tests" in c.target_problem
    assert "pytest" in c.attempted_approach
    assert "Traceback" in c.outcome_evidence


def test_scan_detects_traceback_in_non_is_error_result(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(p, [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": "build the project"}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "make build"}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result",
                                  "content": "Error: target 'build' not found\n"}]}},
    ])
    cands = scan_for_failures(p, max_lines=200)
    assert len(cands) == 1
    assert "Error: target" in cands[0].outcome_evidence


def test_scan_ignores_successful_tool_results(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(p, [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": "list files"}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "ls"}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result",
                                  "content": "a.txt\nb.txt\n"}]}},
    ])
    cands = scan_for_failures(p, max_lines=200)
    assert cands == []


def test_scan_dedups_repeated_failures_within_60s_in_memory(tmp_path: Path) -> None:
    """Two consecutive failures for the same approach produce one candidate."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": "fix the build"}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "make build"}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result", "is_error": True,
                                  "content": "Error: 1"}]}},
        # same approach attempted again
        {"type": "assistant", "uuid": "a2",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "make build"}}]}},
        {"type": "user", "uuid": "u3",
         "message": {"role": "user",
                     "content": [{"type": "tool_result", "is_error": True,
                                  "content": "Error: 2"}]}},
    ])
    cands = scan_for_failures(p, max_lines=200)
    assert len(cands) == 1  # in-memory dedup; DB UNIQUE handles cross-session


def test_scan_handles_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "nope.jsonl"
    cands = scan_for_failures(p, max_lines=200)
    assert cands == []  # silent, non-fatal


def test_scan_handles_malformed_json_line(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('{"type": "user"}\nnot-json\n{"type": "user"}\n')
    cands = scan_for_failures(p, max_lines=200)
    assert cands == []  # silent on malformed lines, returns empty


def test_scan_truncates_oversized_fields(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    long_prompt = "x" * 2000
    long_output = "Traceback " + ("y" * 2000)
    _write_transcript(p, [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": long_prompt}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "a" * 1000}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result", "is_error": True,
                                  "content": long_output}]}},
    ])
    cands = scan_for_failures(p, max_lines=200)
    assert len(cands) == 1
    c = cands[0]
    assert len(c.target_problem) <= 400
    assert len(c.attempted_approach) <= 200
    assert len(c.outcome_evidence) <= 600


def test_scan_detects_command_not_found_mid_line(tmp_path: Path) -> None:
    """Shells emit `command not found` mid-line (e.g. `bash: foo: command not found`)."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": "run the helper"}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash",
                                  "input": {"command": "fooooobar"}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result",
                                  "content": "bash: fooooobar: command not found\n"}]}},
    ])
    cands = scan_for_failures(p, max_lines=200)
    assert len(cands) == 1
    assert "command not found" in cands[0].outcome_evidence


# Noise-filter tests (v0.8.5) — these target_problems / approaches / evidence
# combinations should all be skipped as noise rather than producing failures.


def _failure_transcript(user_prompt: str, tool_name: str, command: str, error_body: str):
    return [
        {"type": "user", "uuid": "u1",
         "message": {"role": "user", "content": user_prompt}},
        {"type": "assistant", "uuid": "a1",
         "message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": tool_name,
                                  "input": {"command": command} if tool_name == "Bash" else {"x": command}}]}},
        {"type": "user", "uuid": "u2",
         "message": {"role": "user",
                     "content": [{"type": "tool_result", "is_error": True,
                                  "content": error_body}]}},
    ]


def test_scan_filters_ide_opened_file_marker(tmp_path: Path) -> None:
    """`<ide_opened_file>...` system markers as user prompts are not real targets."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, _failure_transcript(
        user_prompt="<ide_opened_file>The user opened the file /temp/x.md",
        tool_name="Bash",
        command="cargo build",
        error_body="error[E0432]: unresolved import",
    ))
    assert scan_for_failures(p, max_lines=200) == []


def test_scan_filters_system_reminder_marker(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(p, _failure_transcript(
        user_prompt="<system-reminder>The TodoWrite tool hasn't been used recently",
        tool_name="Bash",
        command="make build",
        error_body="Error: build failed",
    ))
    assert scan_for_failures(p, max_lines=200) == []


def test_scan_filters_recursive_brain_cli_calls(tmp_path: Path) -> None:
    """Bash invocations of the brain CLI itself shouldn't be auto-flagged."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, _failure_transcript(
        user_prompt="check the brain status",
        tool_name="Bash",
        command="brain --version",
        error_body="Error: No such option '--version'",
    ))
    assert scan_for_failures(p, max_lines=200) == []


def test_scan_filters_cli_usage_errors(tmp_path: Path) -> None:
    """Usage / Try '... --help' / Error: Missing argument patterns are agent
    mistakes on argument shape, not real failures."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, _failure_transcript(
        user_prompt="capture an ADR",
        tool_name="Bash",
        command="some-other-cli decide",
        error_body=(
            "Usage: some-other-cli decide [OPTIONS] TITLE\n"
            "Try 'some-other-cli decide --help' for help.\n\n"
            "Error: Missing argument 'TITLE'."
        ),
    ))
    assert scan_for_failures(p, max_lines=200) == []


def test_scan_filters_short_evidence_without_failure_signature(tmp_path: Path) -> None:
    """grep no-match returns exit 1 with empty output. Not worth flagging."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, _failure_transcript(
        user_prompt="find the token",
        tool_name="Bash",
        command="grep zzznonexistent /tmp/file",
        error_body="",  # empty output
    ))
    assert scan_for_failures(p, max_lines=200) == []


def test_scan_filters_blocklisted_tools(tmp_path: Path) -> None:
    """TodoWrite, Skill, etc. shouldn't produce failure captures."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, _failure_transcript(
        user_prompt="add a todo",
        tool_name="TodoWrite",
        command="some-input",
        error_body="Error: validation failed",
    ))
    assert scan_for_failures(p, max_lines=200) == []


def test_scan_keeps_real_failure_after_noise_filters(tmp_path: Path) -> None:
    """Sanity: a legitimate Bash compile failure still passes through."""
    p = tmp_path / "t.jsonl"
    _write_transcript(p, _failure_transcript(
        user_prompt="compile the rust crate",
        tool_name="Bash",
        command="cargo build --release",
        error_body="error[E0432]: unresolved import `std::nope`",
    ))
    cands = scan_for_failures(p, max_lines=200)
    assert len(cands) == 1
    assert "cargo build" in cands[0].attempted_approach
