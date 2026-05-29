"""Multi-query fusion expander (Phase 3b).

LLM generates 3–5 paraphrases / reformulations of the user query. Each variant
gets run through the Fast-tier recall stack; results are RRF-fused. Closes
recall-side FNs from vocabulary mismatch.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from brain.reasoning.base import GroundedHelper

_PROMPT_VER = "v1"

_PROMPT_TEMPLATE = """\
You are an information-retrieval query expander for a Postgres-backed second
brain. Given the original query below, produce 3-5 reformulations that
capture the same information need with different vocabulary, level of
specificity, and structural framing. The original query MUST be included
verbatim as the first variant. Subsequent variants should differ
substantively (synonyms, related concepts, narrower / broader phrasings).

Hard rules:
- The first variant equals the original query, character-for-character.
- 3 to 5 variants total (including the original).
- Each variant is a single English sentence or phrase, <= 200 chars.
- No duplicates. No empty strings.
- No filler ("alternatively, ..."), no leading numbering, no commentary.

Original query:
{query}

Return JSON matching the schema."""


class MultiQueryExpansion(BaseModel):
    variants: list[str] = Field(min_length=3, max_length=5)


class MultiQueryExpander(GroundedHelper[MultiQueryExpansion]):
    def __init__(self, *, engine: Engine) -> None:
        super().__init__(
            engine=engine,
            name="multi_query_expander",
            prompt_ver=_PROMPT_VER,
            output_schema=MultiQueryExpansion,
        )

    def prepare(self, query: str):  # type: ignore[override]
        prompt = _PROMPT_TEMPLATE.format(query=query)
        return super().prepare(prompt)
