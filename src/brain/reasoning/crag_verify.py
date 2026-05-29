"""CRAG verification gate (Phase 3b).

LLM-as-judge scores each top-K retrieval candidate's relevance to the query.
Three-way verdict (spec §Retrieval hardening / Verification):
  - keep    : score >= 0.7 — surface as-is
  - merge   : 0.3 < score < 0.7 — kept with rank softened (handled by caller)
  - discard : score <= 0.3 — drop from results

This helper does NOT decide the trigger — that lives in recall_deep().
This helper just scores whatever candidates the caller hands it.
"""

from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from brain.reasoning.base import GroundedHelper

_PROMPT_VER = "v1"


class CragVerdict(str, Enum):
    KEEP = "keep"
    MERGE = "merge"
    DISCARD = "discard"


class CragCandidateVerdict(BaseModel):
    source_id: int
    score: float = Field(ge=0.0, le=1.0)
    verdict: CragVerdict
    reason: str = Field(max_length=200)


class CragVerification(BaseModel):
    verdicts: list[CragCandidateVerdict] = Field(min_length=1)


_PROMPT_TEMPLATE = """\
You are a retrieval verifier for an agent's second brain. Score each
candidate's relevance to the query. Output exactly one verdict per candidate.

Verdict bands:
  - "keep"    : score >= 0.7. The candidate directly answers or is highly
                relevant to the query.
  - "merge"   : 0.3 < score < 0.7. Tangentially relevant; provides partial
                context but not the main answer.
  - "discard" : score <= 0.3. Off-topic; would mislead the agent if kept.

Scoring discipline:
  - Anchor on whether the candidate would help the agent answer the query,
    not on surface similarity.
  - Be strict: prefer "discard" over "merge" when in doubt.
  - Score is the same number bucket: keep band uses 0.7–1.0, merge band
    uses 0.4–0.69, discard band uses 0.0–0.29. Pick a value in the chosen
    verdict's band.
  - Reason: <= 200 chars. State the load-bearing fact, not pleasantries.

Query:
{query}

Candidates (JSON list):
{candidates_json}

Return JSON matching the schema with one verdict per candidate in the SAME
order as the input."""


class CragVerifier(GroundedHelper[CragVerification]):
    def __init__(self, *, engine: Engine) -> None:
        super().__init__(
            engine=engine,
            name="crag_verifier",
            prompt_ver=_PROMPT_VER,
            output_schema=CragVerification,
        )

    def prepare(self, *, query: str, candidates: list[dict]):  # type: ignore[override]
        # Truncate candidate content to keep the prompt tight (rerank already
        # picked the small pool — content should be <= 1024 tokens / 4KB each).
        trimmed = [
            {
                "id": int(c["id"]),
                "kind": str(c.get("kind", "")),
                "content": str(c.get("content", ""))[:2000],
            }
            for c in candidates
        ]
        prompt = _PROMPT_TEMPLATE.format(
            query=query,
            candidates_json=json.dumps(trimmed, ensure_ascii=False, indent=2),
        )
        return super().prepare(prompt)
