"""Pydantic 2 input/output schemas for brain.write() / brain.read() / helpers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProvenanceKind = Literal["captured", "ingested", "synthesized", "user_authored"]
SourceKind = Literal[
    "tool_call_output",
    "command",
    "edit",
    "decision",
    "note",
    "gotcha",
    "pattern",
    "paper",
    "code_file",
    "web_page",
    "chunk_context",
    "faq",
    "session_summary",
    "subtask_summary",
    "image",
    "binary_artifact",
    "project_index",
]
Bucket = Literal["semantic", "episodic", "procedural", "failure"]
Status = Literal["active", "archived", "draft"]


class SourceInput(BaseModel):
    """Caller-facing input to brain.write()."""

    model_config = ConfigDict(frozen=True)

    kind: SourceKind
    content: str
    uri: str | None = None
    mime: str | None = None
    lang: str | None = None
    project_id: int | None = None
    status: Status = "active"
    provenance_kind: ProvenanceKind = "captured"
    synthesized_from: list[int] | None = None
    parent_id: int | None = None
    span_start: int | None = None
    span_end: int | None = None
    flags: dict[str, object] = Field(default_factory=dict)
    classifier: str = "agent"
    buckets: list[Bucket] = Field(default_factory=list)


class WriteResult(BaseModel):
    """Return shape from brain.write()."""

    source_id: int
    created: bool  # False if existing active row returned (dedup hit)
    generation_depth: int
