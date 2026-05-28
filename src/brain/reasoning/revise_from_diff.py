"""brain-revise --from-diff (v0.10.0) — propose invalidations from a diff hunk.

Reuses Phase 2.5 GroundedHelper machinery and _load_claims_for_sources /
_render_claims helpers from revise_on_ingest; differs from revise_on_ingest
in the output schema (diff-centric: invalidations/reassertions/creations) and
the prepare-time prompt (diff hunk vs new source body).

The agent synthesizes the response inline; finalize validates the JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.reasoning.base import GroundedHelper, PromptBundle
from brain.reasoning.propose_links import propose_links
from brain.reasoning.revise_on_ingest import (
    _load_claims_for_sources,
    _render_claims,
)

_HELPER_NAME = "revise_from_diff"
_PROMPT_VER = "v1"

_PROMPT_TEMPLATE = """\
You are revising the brain's captured knowledge given a NEW DIFF.

# Anchor source
Source ID: {source_id}
URI: {uri}
Captured content:
{content}

# Diff that may invalidate it
{diff_hunk}

# Neighboring claims (top hits from propose_links)
{neighbor_claims}

# Task
For each captured claim that the diff CONTRADICTS, propose an invalidation
with a one-sentence reason quoting the relevant diff line. For each claim
the diff REINFORCES, propose a reassertion. Use the strict JSON schema.

Respond with a single JSON object only.
"""


# ---------------------------------------------------------------------------
# Output schema — distinct from RevisionPlan in revise_on_ingest because the
# diff workflow uses source-level invalidations, not claim-level updates.
# ---------------------------------------------------------------------------


class Invalidation(BaseModel):
    source_id: int
    reason: str


class Reassertion(BaseModel):
    source_id: int
    reason: str


class Creation(BaseModel):
    kind: str
    content: str
    reason: str


class DiffRevisionPlan(BaseModel):
    invalidations: list[Invalidation]
    reassertions: list[Reassertion]
    creations: list[Creation]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _helper(engine: Engine) -> GroundedHelper[DiffRevisionPlan]:
    return GroundedHelper[DiffRevisionPlan](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=DiffRevisionPlan,
    )


def _load_source_meta(engine: Engine, source_id: int) -> tuple[str, str | None]:
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT content, uri FROM sources "
                "WHERE id = :i AND t_valid_to IS NULL"
            ),
            {"i": source_id},
        ).one()
    return row.content, row.uri


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def revise_prepare_from_diff(
    engine: Engine,
    *,
    source_id: int,
    diff_hunk: str,
    embedder: BgeM3Embedder,
) -> PromptBundle[DiffRevisionPlan]:
    """Prepare the prompt for an agent to propose invalidations given a diff."""
    content, uri = _load_source_meta(engine, source_id)
    proposals = propose_links(
        engine, source_id=source_id, embedder=embedder, top_k=8
    )
    neighbor_ids = [p.target_source_id for p in proposals.proposals]
    neighbor_claims = _load_claims_for_sources(engine, neighbor_ids)
    rendered = _PROMPT_TEMPLATE.format(
        source_id=source_id,
        uri=uri or "",
        content=content,
        diff_hunk=diff_hunk,
        neighbor_claims=_render_claims(neighbor_claims),
    )
    return _helper(engine).prepare(rendered)


def revise_finalize_from_diff(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> DiffRevisionPlan:
    """Validate agent JSON output and persist to reasoning_cache."""
    return _helper(engine).finalize(cache_key=cache_key, raw_output=raw_output)
