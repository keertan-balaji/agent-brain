"""reasoning.summarize: produce a cited synthesis of a set of sources.

Loads source bodies by id, renders them into the summarize prompt template,
runs the call through GroundedHelper for cache + retry-validate + persistence.

Citations are int source_ids the LLM claims to draw from; the wrapper does
not validate they actually appear in the input set — that's the model's job
to behave per prompt. A follow-up `cite` helper validates per-span entailment.
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

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "summarize.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v1"
_HELPER_NAME = "summarize"
_SYSTEM = (
    "You are a concise technical summarizer. You return strict JSON with a "
    "`summary` string and a `citations` array of integer source ids. No prose "
    "outside the JSON."
)


class SummarizeOutput(BaseModel):
    summary: str
    citations: list[int]


def _load_sources(engine: Engine, source_ids: list[int]) -> list[tuple[int, str]]:
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, content FROM sources "
                "WHERE id = ANY(:ids) AND t_valid_to IS NULL "
                "ORDER BY id"
            ),
            {"ids": source_ids},
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _render_sources(sources: list[tuple[int, str]]) -> str:
    return "\n\n".join(f"[id={sid}]\n{content}" for sid, content in sources)


def summarize(
    engine: Engine,
    *,
    source_ids: list[int],
    llm_client: AnthropicClient,
) -> SummarizeOutput:
    sources = _load_sources(engine, source_ids)
    rendered = _PROMPT_TEMPLATE.format(sources=_render_sources(sources))

    def _llm_fn(prompt: str) -> str:
        result = llm_client.haiku(
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )
        return result.text

    helper = GroundedHelper[SummarizeOutput](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=SummarizeOutput,
        llm_fn=_llm_fn,
        llm_model_id=HAIKU_MODEL_ID,
        llm_model_ver=HAIKU_MODEL_VER,
    )
    return helper.run(rendered)
