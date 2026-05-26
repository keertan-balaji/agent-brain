"""Sanitization minimum (Phase 3a-2).

Three responsibilities:
- strip_ansi: remove ANSI CSI escape sequences + non-printable control
  characters (including CR) from text. Preserves only \\t and \\n.
  Known gap: OSC sequences (`ESC ] ... BEL`) are not yet matched and
  will leave literal payload garbage after the control-char pass —
  Phase 4 hardening covers this.
- instruction_density: heuristic score (matches per 1000 chars) of phrases
  that look like prompt-injection instructions.
- sanitize_for_ingest: applied by brain.write() to high-risk kinds; cleans
  content and flags suspicious-but-still-ingested rows.

Flag-only — never reject. The agent sees the flag and decides whether to
trust the content. See spec § "Sanitization at ingest".
"""

from __future__ import annotations

import re

from brain.schemas import SourceInput

_ANSI_RE = re.compile(r"\x1b\[[\d;?]*[a-zA-Z]")
_NONPRINT_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0d\x0e-\x1f]")

_SUSPICIOUS_PHRASES = [
    r"ignore (the )?previous instructions?",
    r"disregard (the )?(previous|above|prior)",
    r"you are now",
    r"new instructions?:",
    r"system:\s",
    r"<\s*system\s*>",
    r"override (your|the) (instructions?|directives?|rules?)",
]
_SUSPICIOUS_RE = re.compile("|".join(_SUSPICIOUS_PHRASES), re.IGNORECASE)

_HIGH_RISK_KINDS: frozenset[str] = frozenset(
    {"tool_call_output", "command", "web_page", "code_file"}
)


def strip_ansi(text: str) -> str:
    if not text:
        return text
    return _NONPRINT_RE.sub("", _ANSI_RE.sub("", text))


def instruction_density(text: str) -> float:
    if not text:
        return 0.0
    hits = len(_SUSPICIOUS_RE.findall(text))
    return (hits * 1000.0) / len(text)


def sanitize_for_ingest(source: SourceInput) -> SourceInput:
    if source.kind not in _HIGH_RISK_KINDS:
        return source
    cleaned = strip_ansi(source.content)
    density = instruction_density(cleaned)
    new_flags: dict[str, object] = dict(source.flags)
    if density > 1.0:
        new_flags["suspicious"] = True
        new_flags["suspicion_reason"] = "instruction_density"
        new_flags["suspicion_score"] = round(density, 3)
    return source.model_copy(update={"content": cleaned, "flags": new_flags})
