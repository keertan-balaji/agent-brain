"""Default bucket-assignment rules. See spec §Memory taxonomy."""

from __future__ import annotations

from brain.schemas import Bucket, SourceKind

_RULES: dict[SourceKind, list[Bucket]] = {
    "tool_call_output": ["episodic"],
    "command": ["episodic"],
    "edit": ["episodic"],
    "session_summary": ["episodic"],
    "subtask_summary": ["episodic"],
    "decision": ["episodic", "semantic"],  # curated=True trims to semantic only
    "gotcha": ["episodic", "failure"],
    "pattern": ["procedural"],
    "note": ["episodic"],
    "paper": ["semantic"],
    "code_file": ["semantic"],
    "web_page": ["semantic"],
    "chunk_context": ["semantic"],
    "faq": ["semantic"],
    "image": ["episodic"],
    "binary_artifact": ["episodic"],
    "project_index": ["semantic"],
}


def buckets_for_kind(kind: SourceKind, *, curated: bool) -> list[Bucket]:
    """Return the buckets a fresh source of this kind should be classified into.

    `curated=True` means the source is being explicitly promoted by curation —
    decisions in this mode drop their episodic membership in favor of semantic only.
    """
    buckets = list(_RULES.get(kind, ["episodic"]))
    if curated and kind == "decision":
        return ["semantic"]
    return buckets
