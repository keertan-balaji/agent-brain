"""reasoning.revise_on_ingest: A-MEM neighbor-rewrite plan, agent-driven.

prepare runs propose_links to gather neighbors, loads their extracted_claims,
renders the prompt + schema for the agent. finalize validates the agent's
JSON output against RevisionPlan.

This helper PROPOSES only — it never mutates sources.content, extracted_claims,
or edges. Execution is human-gated (future apply step).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.reasoning.base import GroundedHelper, PromptBundle
from brain.reasoning.propose_links import propose_links

_PROMPT_PATH = Path(__file__).parent / "prompts" / "revise_on_ingest.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v2"
_HELPER_NAME = "revise_on_ingest"


class ClaimUpdate(BaseModel):
    claim_id: int | None
    action: Literal["invalidate", "reassert", "create"]
    new_subject: str
    new_predicate: str
    new_object: str


class Contradiction(BaseModel):
    claim_a_id: int
    claim_b_id: int
    reason: str


class RevisionPlan(BaseModel):
    updates: list[ClaimUpdate]
    contradictions: list[Contradiction]
    affected_pages: list[int]


def _load_claims_for_sources(engine: Engine, source_ids: list[int]) -> list[dict]:
    if not source_ids:
        return []
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                """
                SELECT id, source_id, subject, predicate, object
                FROM extracted_claims
                WHERE source_id = ANY(:ids) AND t_valid_to IS NULL
                """
            ),
            {"ids": source_ids},
        ).fetchall()
    return [
        {"id": r[0], "source_id": r[1], "subject": r[2], "predicate": r[3], "object": r[4]}
        for r in rows
    ]


def _render_claims(claims: list[dict]) -> str:
    if not claims:
        return "(no neighbor claims)"
    return "\n".join(
        f"[claim_id={c['id']} from source {c['source_id']}] {c['subject']} -- {c['predicate']} -- {c['object']}"
        for c in claims
    )


def _load_source_content(engine: Engine, source_id: int) -> str:
    with session_scope(engine) as s:
        return s.execute(text("SELECT content FROM sources WHERE id = :id"), {"id": source_id}).scalar()


def _helper(engine: Engine) -> GroundedHelper[RevisionPlan]:
    return GroundedHelper[RevisionPlan](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=RevisionPlan,
    )


def revise_prepare(
    engine: Engine,
    *,
    new_source_id: int,
    embedder: BgeM3Embedder,
) -> PromptBundle[RevisionPlan]:
    proposals = propose_links(engine, source_id=new_source_id, embedder=embedder, top_k=10)
    neighbor_ids = [p.target_source_id for p in proposals.proposals]
    neighbor_claims = _load_claims_for_sources(engine, neighbor_ids)
    new_content = _load_source_content(engine, new_source_id)
    rendered = _PROMPT_TEMPLATE.format(
        new_source_id=new_source_id,
        new_content=new_content,
        neighbor_claims=_render_claims(neighbor_claims),
    )
    return _helper(engine).prepare(rendered)


def revise_finalize(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> RevisionPlan:
    return _helper(engine).finalize(cache_key=cache_key, raw_output=raw_output)
