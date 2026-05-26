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
