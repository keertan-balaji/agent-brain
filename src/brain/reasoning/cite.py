"""reasoning.cite: ground a claim in verbatim source spans.

prepare renders the prompt + schema; finalize validates JSON, then strips
Support entries whose excerpt is not a substring of the cited source's content.
The cache stores the RAW LLM output (un-filtered) so re-running with a
different candidate set still hits the cache; validation runs per-call.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.reasoning.base import GroundedHelper, PromptBundle

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "cite.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v2"
_HELPER_NAME = "cite"


class Support(BaseModel):
    source_id: int
    span_start: int
    span_end: int
    excerpt: str


class CiteOutput(BaseModel):
    supporting_sources: list[Support]


def _load_sources(engine: Engine, source_ids: list[int]) -> dict[int, str]:
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, content FROM sources "
                "WHERE id = ANY(:ids) AND t_valid_to IS NULL"
            ),
            {"ids": source_ids},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def _render_sources(sources: dict[int, str]) -> str:
    return "\n\n".join(f"[id={sid}]\n{content}" for sid, content in sources.items())


def _helper(engine: Engine) -> GroundedHelper[CiteOutput]:
    return GroundedHelper[CiteOutput](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=CiteOutput,
    )


def cite_prepare(
    engine: Engine,
    *,
    claim_text: str,
    candidate_source_ids: list[int],
) -> PromptBundle[CiteOutput]:
    sources = _load_sources(engine, candidate_source_ids)
    rendered = _PROMPT_TEMPLATE.format(
        claim_text=claim_text,
        sources=_render_sources(sources),
    )
    bundle = _helper(engine).prepare(rendered)
    # If cached, run the same validation pass on the cached output to maintain invariants.
    if bundle.cached is not None:
        kept = [
            s for s in bundle.cached.supporting_sources
            if s.excerpt in sources.get(s.source_id, "")
        ]
        bundle.cached.supporting_sources = kept
    return bundle


def cite_finalize(
    engine: Engine,
    *,
    candidate_source_ids: list[int],
    cache_key: bytes,
    raw_output: str,
) -> CiteOutput:
    parsed: CiteOutput = _helper(engine).finalize(cache_key=cache_key, raw_output=raw_output)
    sources = _load_sources(engine, candidate_source_ids)
    kept = [s for s in parsed.supporting_sources if s.excerpt in sources.get(s.source_id, "")]
    parsed.supporting_sources = kept
    return parsed
