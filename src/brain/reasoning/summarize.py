"""reasoning.summarize: prepare a cited synthesis prompt; finalize validates output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.reasoning.base import GroundedHelper, PromptBundle

_PROMPT_PATH = Path(__file__).parent / "prompts" / "summarize.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v2"
_HELPER_NAME = "summarize"


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


def _helper(engine: Engine) -> GroundedHelper[SummarizeOutput]:
    return GroundedHelper[SummarizeOutput](
        engine=engine,
        name=_HELPER_NAME,
        prompt_ver=_PROMPT_VER,
        output_schema=SummarizeOutput,
    )


def summarize_prepare(
    engine: Engine, *, source_ids: list[int]
) -> PromptBundle[SummarizeOutput]:
    sources = _load_sources(engine, source_ids)
    rendered = _PROMPT_TEMPLATE.format(sources=_render_sources(sources))
    return _helper(engine).prepare(rendered)


def summarize_finalize(
    engine: Engine, *, cache_key: bytes, raw_output: str
) -> SummarizeOutput:
    return _helper(engine).finalize(cache_key=cache_key, raw_output=raw_output)
