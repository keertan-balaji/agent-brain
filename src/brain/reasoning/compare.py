"""reasoning.compare: pairwise comparison of two sources.

Produces structured agreements / disagreements (with typed axis) / scope_diff /
citations. Axis is documented as one of {scope, time, mechanism, evidence} in
the prompt; the schema accepts any string for forward compatibility (the
output is consumed by humans + downstream reasoning, not as enum).
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

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "compare.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v1"
_HELPER_NAME = "compare"
_SYSTEM = (
    "You compare two source documents and emit strict JSON with `agreements`, "
    "`disagreements`, `scope_diff`, and `citations` fields. No prose outside "
    "the JSON."
)


class CompareOutput(BaseModel):
    agreements: list[str]
    disagreements: list[dict]
    scope_diff: str
    citations: list[int]


def _load_source(engine: Engine, source_id: int) -> str:
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT content FROM sources "
                "WHERE id = :id AND t_valid_to IS NULL"
            ),
            {"id": source_id},
        ).one()
    return row[0]


def compare(
    engine: Engine,
    *,
    a_source_id: int,
    b_source_id: int,
    llm_client: AnthropicClient,
) -> CompareOutput:
    a_content = _load_source(engine, a_source_id)
    b_content = _load_source(engine, b_source_id)
    rendered = _PROMPT_TEMPLATE.format(
        a_id=a_source_id,
        a_content=a_content,
        b_id=b_source_id,
        b_content=b_content,
    )

    def _llm_fn(prompt: str) -> str:
        result = llm_client.haiku(
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        return result.text

    helper = GroundedHelper[CompareOutput](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=CompareOutput,
        llm_fn=_llm_fn,
        llm_model_id=HAIKU_MODEL_ID,
        llm_model_ver=HAIKU_MODEL_VER,
    )
    return helper.run(rendered)
