"""Self-Query metadata extractor (Phase 3b).

LLM reads a natural-language query and extracts structured retrieval filters
(kinds, project hint, buckets, time window) plus a residual_query that holds
the semantic-search portion. The residual goes through the hybrid stack;
the filters are applied as a metadata pre-filter (post-hoc for v0.12.0 —
since/until are filtered after recall returns).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from brain.reasoning.base import GroundedHelper

_PROMPT_VER = "v1"

_PROMPT_TEMPLATE = """\
You are a query-router for a Postgres-backed second brain. Read the user's
natural-language query and extract structured retrieval filters from it.
The residual_query you produce is what the vector + FTS search will run on;
the structured filters narrow the candidate set before retrieval.

Available kinds: decision, gotcha, pattern, note, faq, subtask_summary,
session_summary, failure_memory, procedure, tool_call, command. Leave kinds
empty if the user didn't restrict to a specific type.

Available buckets: semantic, episodic, procedural, failure. Leave empty if
unspecified.

Time references — convert to ISO-8601 UTC strings (e.g. "last week" ->
"2026-05-22T00:00:00Z", "since March" -> "2026-03-01T00:00:00Z"). Anchor
relative dates to TODAY = {today_iso}. Use null if the query has no
temporal scope.

project_hint: a free-text phrase the user used to indicate a project
(e.g. "in the brain project" -> "brain"), or null. Brain matches this
against project metadata downstream — do not resolve to a project_id.

residual_query: the portion of the user's query the semantic / FTS search
should run on, with the filter language stripped. If no filters were
present, residual_query equals the original query.

Hard rules:
- residual_query MUST be non-empty.
- All ISO strings include a 'Z' suffix.
- Do not invent filters not implied by the query.

Original query (today is {today_iso}):
{query}

Return JSON matching the schema."""


class QueryFilters(BaseModel):
    kinds: list[str] = Field(default_factory=list)
    project_hint: str | None = None
    buckets: list[str] = Field(default_factory=list)
    since_iso: str | None = None
    until_iso: str | None = None
    residual_query: str = Field(min_length=1)


class QueryFilterExtractor(GroundedHelper[QueryFilters]):
    def __init__(self, *, engine: Engine) -> None:
        super().__init__(
            engine=engine,
            name="query_filter_extractor",
            prompt_ver=_PROMPT_VER,
            output_schema=QueryFilters,
        )

    def prepare(self, query: str, *, today_iso: str | None = None):  # type: ignore[override]
        if today_iso is None:
            today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        prompt = _PROMPT_TEMPLATE.format(query=query, today_iso=today_iso)
        return super().prepare(prompt)
