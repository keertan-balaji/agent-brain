"""reasoning.compare: prepare a pairwise comparison prompt; finalize validates output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.reasoning.base import GroundedHelper, PromptBundle

_PROMPT_PATH = Path(__file__).parent / "prompts" / "compare.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v2"
_HELPER_NAME = "compare"


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


def _helper(engine: Engine) -> GroundedHelper[CompareOutput]:
    return GroundedHelper[CompareOutput](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=CompareOutput,
    )


def compare_prepare(
    engine: Engine, *, a_source_id: int, b_source_id: int
) -> PromptBundle[CompareOutput]:
    a_content = _load_source(engine, a_source_id)
    b_content = _load_source(engine, b_source_id)
    rendered = _PROMPT_TEMPLATE.format(
        a_id=a_source_id,
        a_content=a_content,
        b_id=b_source_id,
        b_content=b_content,
    )
    return _helper(engine).prepare(rendered)


def compare_finalize(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> CompareOutput:
    return _helper(engine).finalize(cache_key=cache_key, raw_output=raw_output)
