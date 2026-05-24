"""reasoning.cite: ground a claim in verbatim source spans.

Given a claim and a set of candidate source ids, asks the LLM which sources
support the claim and where. Validates each returned excerpt actually appears
verbatim in the cited source's content; entries whose excerpt cannot be found
are dropped, treating them as model hallucinations.

The post-LLM validation is the load-bearing safeguard: it converts the helper
from "trust the model's spans" into "the spans came from this source, period."
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.llm.client import (
    HAIKU_MODEL_ID,
    HAIKU_MODEL_VER,
    AnthropicClient,
)
from brain.reasoning.base import GroundedHelper

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "cite.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v1"
_HELPER_NAME = "cite"
_SYSTEM = (
    "You ground claims in verbatim source spans. You return strict JSON with a "
    "`supporting_sources` array. Each excerpt must be copied verbatim from the "
    "cited source. No prose outside the JSON."
)


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


def _validate_supports(
    raw: CiteOutput, sources: dict[int, str]
) -> list[Support]:
    """Drop supports whose excerpt doesn't appear verbatim in the cited source."""
    kept: list[Support] = []
    for sup in raw.supporting_sources:
        content = sources.get(sup.source_id)
        if content is None:
            continue
        if sup.excerpt in content:
            kept.append(sup)
    return kept


def cite(
    engine: Engine,
    *,
    claim_text: str,
    candidate_source_ids: list[int],
    llm_client: AnthropicClient,
) -> CiteOutput:
    sources = _load_sources(engine, candidate_source_ids)
    rendered = _PROMPT_TEMPLATE.format(
        claim_text=claim_text,
        sources=_render_sources(sources),
    )

    def _llm_fn(prompt: str) -> str:
        result = llm_client.haiku(
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        return result.text

    helper = GroundedHelper[CiteOutput](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=CiteOutput,
        llm_fn=_llm_fn,
        llm_model_id=HAIKU_MODEL_ID,
        llm_model_ver=HAIKU_MODEL_VER,
    )
    raw = helper.run(rendered)
    validated = _validate_supports(raw, sources)
    return CiteOutput(supporting_sources=validated)
