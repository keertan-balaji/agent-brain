# Agent Brain Phase 3b — Retrieval Hardening (Deep Tier) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Deep-tier recall path with the four query-hardening + verification layers the v2 spec calls for — multi-query fusion, Self-Query metadata extraction, CRAG verification gate, and a `brain recall --deep` wrapper that composes them. Extend the eval harness from 20 to 50+ questions and add a `--deep` arm to `run_ab.py` so we can measure the lift.

**Architecture:** All four new LLM-driven layers ride on the existing `GroundedHelper` pattern in `src/brain/reasoning/base.py` (the agent-driven Phase 2.5 convention). Brain prepares the prompt + JSON schema + cache key; the agent synthesizes inline; brain validates and persists. No embedded LLM client. The composition lives in a new `recall_deep()` function in `src/brain/read.py` that wraps `recall()` (which stays unchanged for Fast-tier callers). New CLI flag `brain recall --deep` flips the tier; a `brain-recall` skill update teaches the agent how to drive the multi-query / Self-Query / CRAG steps interactively.

**Tech Stack:** Same as the rest of brain — Python 3.12, Postgres, pgvector, BGE-M3, mxbai-rerank-large-v2 (auto-fallback to bge-reranker-v2-m3 on ≤6GB GPUs), Pydantic v2. No new runtime deps.

**Spec reference:** `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md` §Retrieval hardening (line ~653) and the Phase 3b status table (line ~1204). The four pending bullets:

- Multi-query fusion (3–5 LLM-generated query variants, RRF-fused)
- Self-Query (LLM extracts structured filters from query text)
- CRAG verification gate (conditional per §Retrieval hardening trigger conditions)
- `brain-recall --deep` tier integration
- Eval extension: 50–100 questions (current = 20)

**Prerequisites in place (verified):**
- `src/brain/reasoning/base.py` exports `GroundedHelper`, `PromptBundle`, `cache_key_for`. Established pattern: subclass `GroundedHelper[T]`, define `prompt_template`, `output_schema`, expose `prepare(input)` → `PromptBundle`, `finalize(cache_key, raw_output)` → `T`.
- Existing helpers as references: `src/brain/reasoning/summarize.py`, `compare.py`, `cite.py`, `propose_links.py`, `revise_on_ingest.py`, `revise_from_diff.py`. Each instantiates a subclass + exposes `prepare`/`finalize` module-level functions.
- `src/brain/read.py::recall(engine, query, *, k, project_id, buckets, kinds, include_archived, embedder, reranker, rerank_candidate_pool, tau)` is the Fast-tier entry point. Returns `list[RecallHit]`. Logs to `retrieval_log` via `_log_recall(...)`.
- `RecallHit` dataclass: `id: int`, `kind: str`, `content: str`, `score: float`, `project_id: int | None`.
- `src/brain/retrieval/rrf.py` exports `rrf_fuse(lists: list[list[tuple[id, score]]]) -> list[tuple[id, score]]`.
- `eval/questions.yaml` has 20 questions; `eval/run_ab.py` runs FTS-only vs FTS+BGE-M3+RRF arms, reports hit@1/3/5.
- Tests use `pg_url` fixture; autouse `_truncate_tables` after each test.
- `reasoning_cache` table persists helper outputs keyed by `cache_key = sha256(helper_name + input_hash + prompt_ver)`.

---

## File structure (Phase 3b)

### Creations

```
src/brain/reasoning/
  multi_query.py                       # MultiQueryExpander GroundedHelper
  self_query.py                        # QueryFilterExtractor GroundedHelper
  crag_verify.py                       # CragVerifier GroundedHelper
src/brain/retrieval/
  deep.py                              # recall_deep() — composes Fast tier + multi-query + Self-Query + CRAG
tests/
  test_multi_query.py                  # MultiQueryExpander prepare/finalize + caching
  test_self_query.py                   # QueryFilterExtractor prepare/finalize + filter extraction shape
  test_crag_verify.py                  # CragVerifier prepare/finalize + verdict scoring
  test_recall_deep.py                  # recall_deep end-to-end with stubbed reasoning_cache rows
docs/phase-3b-retrieval-hardening.md   # ops doc explaining the Deep tier
```

### Modifications

```
src/brain/read.py                      # add recall_deep() wrapper using new helpers
src/brain/cli.py                       # add --deep flag to `brain recall`
.claude-plugin/agents/brain-recall.md  # skill update: --deep tier docs (if exists; else only doc)
eval/questions.yaml                    # extend 20 → 50+ questions
eval/run_ab.py                         # add --with-deep arm
docs/v0.11.1-frontend-completion.md    # mention Phase 3b shipped (optional; can defer)
```

---

## Empirical findings (locked in via code + spec inspection)

1. **The GroundedHelper pattern is the only correct surface for new LLM-driven stages.** It keeps brain LLM-client-free and lets each subagent / interactive agent run the call from whatever environment it lives in. All Phase 2.5 helpers (`summarize`, `compare`, `cite`, `propose_links`, `revise_on_ingest`) followed this pattern; Phase 3b is the same shape.
2. **`recall_deep` is a wrapper, not a replacement.** Phase 2 `recall()` stays Fast-tier and is what hooks + skills call by default. `recall_deep()` calls `recall()` internally (or replicates the metadata-prefilter + hybrid generation + rerank stack) and adds the multi-query / Self-Query / CRAG layers around it.
3. **Test strategy for GroundedHelpers:** `prepare()` is fully testable without an LLM (we assert prompt content + schema shape + cache key). `finalize()` is testable by feeding a hand-written JSON string and asserting the parsed model + cache write. Integration tests for `recall_deep()` short-circuit the LLM step by directly pre-seeding `reasoning_cache` rows with the expected outputs.
4. **CRAG trigger conditions (from spec §Retrieval hardening line ~742):** rerank top-1 score in [0.5, 0.7), OR caller passed `--deep`, OR query targets `failure_memory` bucket. The trigger lives inside `recall_deep()`, not in the verifier itself.
5. **Self-Query output drives `kinds`/`project_id`/`buckets`/`since`/`until` filters on the metadata pre-filter.** The existing `recall()` already accepts `kinds`, `project_id`, `buckets`. We need to add a `since: datetime | None` and `until: datetime | None` to the pre-filter — they currently don't exist. This requires either widening `recall()` or applying the temporal filter inside `recall_deep()` post-hoc on the returned hits. Plan chooses post-hoc filtering for v0.12.0 to keep `recall()`'s surface stable; widen in a later refactor.
6. **Multi-query fusion design:** generate 3–5 variants, run each through `recall()` (Fast tier — full hybrid + rerank), then RRF-fuse the result lists. Use `rrf_fuse()` from `src/brain/retrieval/rrf.py`. The original query is always included as one of the K variants.
7. **CRAG verdict scoring:** 3-way per the spec — ≥0.7 keep, ≤0.3 discard, in between "merge" (combined treatment). In code: the verifier returns a per-candidate verdict; `recall_deep` drops `discard` rows, keeps `keep` as-is, and applies a recency-aware soft-merge for the in-between band (rank-blend, not embedding-recompute).

---

## Task 1: Multi-query fusion helper

**Files:**
- Create: `src/brain/reasoning/multi_query.py`
- Create: `tests/test_multi_query.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_multi_query.py`:

```python
"""MultiQueryExpander GroundedHelper — Phase 3b."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.reasoning.multi_query import MultiQueryExpansion, MultiQueryExpander


def test_prepare_emits_prompt_and_schema(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle = h.prepare("how do hooks survive compaction")
    assert "how do hooks survive compaction" in bundle.prompt
    # The schema must declare the `variants` array field.
    assert "variants" in json.dumps(bundle.schema_json)
    assert bundle.cached is None  # first run, nothing cached


def test_finalize_persists_and_returns_validated_model(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle = h.prepare("how do hooks survive compaction")
    raw = json.dumps({
        "variants": [
            "how do hooks survive compaction",
            "claude code hooks across context window summarization",
            "session resume bundles for hook persistence",
            "compaction recovery for hook state",
        ],
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(result, MultiQueryExpansion)
    assert len(result.variants) == 4
    assert "how do hooks survive compaction" in result.variants


def test_prepare_hits_cache_on_repeat(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle1 = h.prepare("X Y Z")
    raw = json.dumps({"variants": ["X Y Z", "X with Y", "Z near X"]})
    h.finalize(cache_key=bundle1.cache_key, raw_output=raw)
    bundle2 = h.prepare("X Y Z")
    assert bundle2.cached is not None
    assert bundle2.cached.variants == ["X Y Z", "X with Y", "Z near X"]


def test_validates_min_variant_count(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = MultiQueryExpander(engine=engine)
    bundle = h.prepare("Q")
    # spec: 3–5 variants. Schema enforces min 3.
    bad = json.dumps({"variants": ["only one"]})
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_multi_query.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/brain/reasoning/multi_query.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_multi_query.py -v`
Expected: PASS — 4/4.

- [ ] **Step 5: Commit**

```bash
git add src/brain/reasoning/multi_query.py tests/test_multi_query.py
git commit -m "feat(phase-3b): multi-query expander GroundedHelper"
```

---

## Task 2: Self-Query metadata extractor

**Files:**
- Create: `src/brain/reasoning/self_query.py`
- Create: `tests/test_self_query.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_self_query.py`:

```python
"""QueryFilterExtractor GroundedHelper — Phase 3b Self-Query."""

from __future__ import annotations

import json

import pytest

from brain.db import get_engine
from brain.reasoning.self_query import (
    QueryFilterExtractor,
    QueryFilters,
)


def test_prepare_emits_prompt_and_schema(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("what decisions did we make last week in the brain project")
    assert "last week" in bundle.prompt
    assert "kinds" in json.dumps(bundle.schema_json)
    assert "since_iso" in json.dumps(bundle.schema_json)


def test_finalize_returns_validated_filters(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("recent gotchas about hooks")
    raw = json.dumps({
        "kinds": ["gotcha"],
        "project_hint": None,
        "buckets": [],
        "since_iso": "2026-05-22T00:00:00Z",
        "until_iso": None,
        "residual_query": "hooks",
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(result, QueryFilters)
    assert result.kinds == ["gotcha"]
    assert result.residual_query == "hooks"
    assert result.since_iso == "2026-05-22T00:00:00Z"


def test_empty_filters_are_valid(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("Q")
    raw = json.dumps({
        "kinds": [],
        "project_hint": None,
        "buckets": [],
        "since_iso": None,
        "until_iso": None,
        "residual_query": "Q",
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert result.kinds == []
    assert result.residual_query == "Q"


def test_residual_query_required(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = QueryFilterExtractor(engine=engine)
    bundle = h.prepare("Q")
    raw = json.dumps({
        "kinds": [],
        "project_hint": None,
        "buckets": [],
        "since_iso": None,
        "until_iso": None,
        # residual_query missing
    })
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_self_query.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `src/brain/reasoning/self_query.py`**

```python
"""Self-Query metadata extractor (Phase 3b).

LLM reads a natural-language query and extracts structured retrieval filters
(kinds, project hint, buckets, time window) plus a residual_query that holds
the semantic-search portion. The residual goes through the hybrid stack;
the filters are applied as a metadata pre-filter (post-hoc for v0.12.0 —
since/until are filtered after recall returns).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Engine

from brain.reasoning.base import GroundedHelper

_PROMPT_VER = "v1"

_PROMPT_TEMPLATE = """\
You are a query-router for a Postgres-backed second brain. Read the user's
natural-language query and extract structured retrieval filters from it.
The residual_query you produce is what the vector + FTS search will run on;
the structured filters narrow the candidate set before retrieval.

Available kinds: decision, gotcha, pattern, note, faq, subtask_summary,
session_summary, failure_memory, procedure, tool_call, command. Leave kinds
empty if the user didn't restrict to a specific type.

Available buckets: semantic, episodic, procedural, failure. Leave empty if
unspecified.

Time references — convert to ISO-8601 UTC strings (e.g. "last week" ->
"2026-05-22T00:00:00Z", "since March" -> "2026-03-01T00:00:00Z"). Anchor
relative dates to TODAY = {today_iso}. Use null if the query has no
temporal scope.

project_hint: a free-text phrase the user used to indicate a project
(e.g. "in the brain project" -> "brain"), or null. Brain matches this
against project metadata downstream — do not resolve to a project_id.

residual_query: the portion of the user's query the semantic / FTS search
should run on, with the filter language stripped. If no filters were
present, residual_query equals the original query.

Hard rules:
- residual_query MUST be non-empty.
- All ISO strings include a 'Z' suffix.
- Do not invent filters not implied by the query.

Original query (today is {today_iso}):
{query}

Return JSON matching the schema."""


class QueryFilters(BaseModel):
    kinds: list[str] = Field(default_factory=list)
    project_hint: str | None = None
    buckets: list[str] = Field(default_factory=list)
    since_iso: str | None = None
    until_iso: str | None = None
    residual_query: str = Field(min_length=1)


class QueryFilterExtractor(GroundedHelper[QueryFilters]):
    def __init__(self, *, engine: Engine) -> None:
        super().__init__(
            engine=engine,
            name="query_filter_extractor",
            prompt_ver=_PROMPT_VER,
            output_schema=QueryFilters,
        )

    def prepare(self, query: str, *, today_iso: str | None = None):  # type: ignore[override]
        from datetime import datetime, timezone
        if today_iso is None:
            today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        prompt = _PROMPT_TEMPLATE.format(query=query, today_iso=today_iso)
        return super().prepare(prompt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_self_query.py -v`
Expected: PASS — 4/4.

- [ ] **Step 5: Commit**

```bash
git add src/brain/reasoning/self_query.py tests/test_self_query.py
git commit -m "feat(phase-3b): Self-Query metadata extractor GroundedHelper"
```

---

## Task 3: CRAG verification helper

**Files:**
- Create: `src/brain/reasoning/crag_verify.py`
- Create: `tests/test_crag_verify.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_crag_verify.py`:

```python
"""CragVerifier GroundedHelper — Phase 3b."""

from __future__ import annotations

import json

import pytest

from brain.db import get_engine
from brain.reasoning.crag_verify import (
    CragVerdict,
    CragVerification,
    CragVerifier,
)


def test_prepare_emits_prompt_and_schema(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    candidates = [
        {"id": 1, "kind": "decision", "content": "use postgres for FTS"},
        {"id": 2, "kind": "gotcha",   "content": "psql -d brain fails in docker"},
    ]
    bundle = h.prepare(query="how do we run FTS", candidates=candidates)
    assert "how do we run FTS" in bundle.prompt
    assert "use postgres for FTS" in bundle.prompt
    assert "verdicts" in json.dumps(bundle.schema_json)


def test_finalize_returns_three_way_verdicts(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    candidates = [
        {"id": 1, "kind": "decision", "content": "use postgres for FTS"},
        {"id": 2, "kind": "gotcha",   "content": "psql -d brain fails in docker"},
        {"id": 3, "kind": "note",     "content": "favorite color is blue"},
    ]
    bundle = h.prepare(query="how do we run FTS", candidates=candidates)
    raw = json.dumps({
        "verdicts": [
            {"source_id": 1, "score": 0.92, "verdict": "keep",    "reason": "directly answers"},
            {"source_id": 2, "score": 0.55, "verdict": "merge",   "reason": "tangential but useful"},
            {"source_id": 3, "score": 0.05, "verdict": "discard", "reason": "irrelevant"},
        ]
    })
    result = h.finalize(cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(result, CragVerification)
    assert len(result.verdicts) == 3
    assert result.verdicts[0].verdict == CragVerdict.KEEP
    assert result.verdicts[1].verdict == CragVerdict.MERGE
    assert result.verdicts[2].verdict == CragVerdict.DISCARD


def test_score_must_be_in_unit_interval(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    bundle = h.prepare(query="Q", candidates=[{"id": 1, "kind": "note", "content": "X"}])
    raw = json.dumps({
        "verdicts": [
            {"source_id": 1, "score": 1.7, "verdict": "keep", "reason": "ok"},  # invalid score
        ]
    })
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=raw)


def test_verdict_enum_enforced(pg_url: str) -> None:
    engine = get_engine(pg_url)
    h = CragVerifier(engine=engine)
    bundle = h.prepare(query="Q", candidates=[{"id": 1, "kind": "note", "content": "X"}])
    raw = json.dumps({
        "verdicts": [
            {"source_id": 1, "score": 0.5, "verdict": "maybe", "reason": "ok"},
        ]
    })
    with pytest.raises(Exception):
        h.finalize(cache_key=bundle.cache_key, raw_output=raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_crag_verify.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `src/brain/reasoning/crag_verify.py`**

```python
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

from pydantic import BaseModel, Field, conlist
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_crag_verify.py -v`
Expected: PASS — 4/4.

- [ ] **Step 5: Commit**

```bash
git add src/brain/reasoning/crag_verify.py tests/test_crag_verify.py
git commit -m "feat(phase-3b): CRAG verifier GroundedHelper with three-way verdicts"
```

---

## Task 4: `recall_deep()` + `brain recall --deep` CLI

**Files:**
- Create: `src/brain/retrieval/deep.py`
- Modify: `src/brain/cli.py`
- Create: `tests/test_recall_deep.py`

The Deep tier composes Fast-tier `recall()` with the three new helpers. The trigger conditions for the CRAG layer (spec §Retrieval hardening) live in this wrapper; the helpers themselves are reusable.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recall_deep.py`:

```python
"""recall_deep — Phase 3b composition test.

The full LLM round-trips are stubbed via direct reasoning_cache seeds:
prepare() finds the cache hit immediately and returns the seeded output.
This lets us exercise the orchestration without an LLM in the loop.
"""

from __future__ import annotations

import json
import hashlib

import pytest
from sqlalchemy import text

from brain.content_hash import sha256_bytes
from brain.db import get_engine, session_scope
from brain.reasoning.base import cache_key_for
from brain.reasoning.multi_query import MultiQueryExpander
from brain.reasoning.self_query import QueryFilterExtractor
from brain.reasoning.crag_verify import CragVerifier
from brain.retrieval.deep import recall_deep


def _seed_reasoning_cache(engine, helper_name: str, prompt: str, prompt_ver: str, output: dict) -> None:
    """Pre-populate the cache so the GroundedHelper short-circuits at prepare()."""
    input_hash = hashlib.sha256(prompt.encode("utf-8")).digest()
    key = cache_key_for(helper_name, input_hash, prompt_ver)
    with session_scope(engine) as s:
        s.execute(
            text(
                "INSERT INTO reasoning_cache(cache_key, helper_name, input_hash, prompt_ver, output_json) "
                "VALUES (:k, :n, :ih, :pv, CAST(:oj AS jsonb)) "
                "ON CONFLICT (cache_key) DO UPDATE SET output_json = EXCLUDED.output_json"
            ),
            {
                "k": key,
                "n": helper_name,
                "ih": input_hash,
                "pv": prompt_ver,
                "oj": json.dumps(output),
            },
        )


def _seed_source(engine, kind: str, content: str, uri: str) -> int:
    h = sha256_bytes(content)
    with session_scope(engine) as s:
        sid = s.execute(
            text(
                "INSERT INTO sources(kind, content, content_hash, status, uri) "
                "VALUES (:k, :c, :h, 'active', :u) RETURNING id"
            ),
            {"k": kind, "c": content, "h": h, "u": uri},
        ).scalar()
        s.execute(
            text(
                "INSERT INTO sources_fts(source_id, tsv) VALUES (:i, to_tsvector('english', :c))"
            ),
            {"i": sid, "c": content},
        )
    return int(sid)


def test_recall_deep_calls_multi_query_and_returns_fused_hits(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid_a = _seed_source(engine, "decision", "FTS uses postgres ts_rank_cd", "decision://fts")
    sid_b = _seed_source(engine, "gotcha",   "ts_rank in postgres needs GIN", "gotcha://ts")

    # Pre-seed multi-query expansion.
    from brain.reasoning.multi_query import MultiQueryExpander
    h_mq = MultiQueryExpander(engine=engine)
    # The "prompt" the helper sees is the formatted template. We need the same
    # exact prompt to share a cache key — reach into the helper to compute it.
    bundle = h_mq.prepare("FTS in postgres")
    _seed_reasoning_cache(
        engine,
        helper_name="multi_query_expander",
        prompt=bundle.prompt,
        prompt_ver="v1",
        output={"variants": ["FTS in postgres", "ts_rank Postgres full-text search", "postgres full text query API"]},
    )

    # Pre-seed self-query extraction.
    h_sq = QueryFilterExtractor(engine=engine)
    sq_bundle = h_sq.prepare("FTS in postgres")
    _seed_reasoning_cache(
        engine,
        helper_name="query_filter_extractor",
        prompt=sq_bundle.prompt,
        prompt_ver="v1",
        output={
            "kinds": [],
            "project_hint": None,
            "buckets": [],
            "since_iso": None,
            "until_iso": None,
            "residual_query": "FTS in postgres",
        },
    )

    # Run deep recall — no CRAG seed needed because the trigger band won't fire
    # on this tiny synthetic corpus (FTS scores are tiny; below the 0.5–0.7 band).
    hits = recall_deep(engine, "FTS in postgres", k=5)
    ids = {h.id for h in hits}
    # At least one of the seeded sources should be retrieved via the expansion.
    assert sid_a in ids or sid_b in ids


def test_recall_deep_applies_self_query_kind_filter(pg_url: str) -> None:
    engine = get_engine(pg_url)
    sid_dec = _seed_source(engine, "decision", "build a docker volume", "decision://vol")
    sid_got = _seed_source(engine, "gotcha",   "docker volume permissions", "gotcha://vol")

    h_mq = MultiQueryExpander(engine=engine)
    bundle = h_mq.prepare("docker volume")
    _seed_reasoning_cache(
        engine, "multi_query_expander", bundle.prompt, "v1",
        {"variants": ["docker volume", "docker mount", "docker bind volume"]},
    )

    h_sq = QueryFilterExtractor(engine=engine)
    sq_bundle = h_sq.prepare("docker volume")
    # Self-Query restricts to kind=gotcha.
    _seed_reasoning_cache(
        engine, "query_filter_extractor", sq_bundle.prompt, "v1",
        {
            "kinds": ["gotcha"],
            "project_hint": None,
            "buckets": [],
            "since_iso": None,
            "until_iso": None,
            "residual_query": "docker volume",
        },
    )

    hits = recall_deep(engine, "docker volume", k=5)
    ids = {h.id for h in hits}
    assert sid_got in ids
    assert sid_dec not in ids


def test_recall_deep_falls_back_to_recall_on_zero_hits(pg_url: str) -> None:
    """If the deep stack returns nothing, the caller should still see an empty list, not crash."""
    engine = get_engine(pg_url)
    h_mq = MultiQueryExpander(engine=engine)
    bundle = h_mq.prepare("nothing-here-zzz")
    _seed_reasoning_cache(
        engine, "multi_query_expander", bundle.prompt, "v1",
        {"variants": ["nothing-here-zzz", "absolutely-not-there", "no-match-no-match"]},
    )
    h_sq = QueryFilterExtractor(engine=engine)
    sq_bundle = h_sq.prepare("nothing-here-zzz")
    _seed_reasoning_cache(
        engine, "query_filter_extractor", sq_bundle.prompt, "v1",
        {"kinds": [], "project_hint": None, "buckets": [], "since_iso": None, "until_iso": None, "residual_query": "nothing-here-zzz"},
    )
    hits = recall_deep(engine, "nothing-here-zzz", k=5)
    assert hits == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_recall_deep.py -v`
Expected: FAIL — `brain.retrieval.deep` doesn't exist.

- [ ] **Step 3: Implement `src/brain/retrieval/deep.py`**

```python
"""Deep-tier recall (Phase 3b).

Composes:
  Self-Query (filter extraction) -> Multi-query expansion -> Fast-tier recall
  per-variant -> RRF fusion -> CRAG verification (gated by trigger conditions)

The trigger conditions for CRAG (spec §Retrieval hardening):
  1. Reranker top-1 score in [0.5, 0.7) — confidence-band where verification helps
  2. Caller explicitly passed --deep (always-on for this entry point)
  3. Query is in the failure bucket — over-eager near-miss recall

The Fast-tier helpers (embedder, reranker) are reused without reload.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine

from brain.read import RecallHit, recall
from brain.reasoning.multi_query import MultiQueryExpander
from brain.reasoning.self_query import QueryFilterExtractor
from brain.reasoning.crag_verify import CragVerdict, CragVerifier
from brain.retrieval.rrf import rrf_fuse


@dataclass
class DeepRecallTrace:
    """Diagnostics returned alongside the hits (for eval + debugging)."""
    variants_used: list[str]
    filters_applied: dict
    crag_triggered: bool
    crag_verdicts: list[dict] | None


def recall_deep(
    engine: Engine,
    query: str,
    *,
    k: int = 10,
    project_id: int | None = None,
    embedder=None,
    reranker=None,
    tau: float | None = None,
    return_trace: bool = False,
) -> list[RecallHit] | tuple[list[RecallHit], DeepRecallTrace]:
    """Deep-tier recall. Falls back to Fast-tier recall when LLM caches are
    cold (the helpers' prepare() returns bundle.cached=None and the caller
    short-circuits with the original query)."""

    # ---- Self-Query filter extraction ------------------------------------
    sq = QueryFilterExtractor(engine=engine)
    sq_bundle = sq.prepare(query)
    if sq_bundle.cached is not None:
        residual = sq_bundle.cached.residual_query
        kinds = sq_bundle.cached.kinds or None
        since_iso = sq_bundle.cached.since_iso
        until_iso = sq_bundle.cached.until_iso
    else:
        # Cache miss — use the original query as residual, no filters.
        residual = query
        kinds = None
        since_iso = None
        until_iso = None

    # ---- Multi-query expansion -------------------------------------------
    mq = MultiQueryExpander(engine=engine)
    mq_bundle = mq.prepare(residual)
    if mq_bundle.cached is not None:
        variants = mq_bundle.cached.variants
    else:
        # Cache miss — single-variant degraded to Fast-tier recall.
        variants = [residual]

    # ---- Per-variant Fast-tier recall + RRF fusion -----------------------
    per_variant_ids: list[list[tuple[int, float]]] = []
    for v in variants:
        hits = recall(
            engine, v, k=k * 3,  # wider per-variant pool so fusion can reorder
            project_id=project_id, kinds=kinds,
            embedder=embedder, reranker=reranker, tau=tau,
        )
        per_variant_ids.append([(h.id, h.score) for h in hits])

    fused = rrf_fuse(per_variant_ids)  # list[(id, score)]
    fused = fused[:max(k * 3, 30)]  # rerank pool for CRAG step

    # Apply temporal post-filter from Self-Query (since/until) if present.
    if since_iso or until_iso:
        fused = _filter_by_time(engine, fused, since_iso=since_iso, until_iso=until_iso)

    if not fused:
        if return_trace:
            return [], DeepRecallTrace(variants_used=variants, filters_applied={"kinds": kinds, "since_iso": since_iso, "until_iso": until_iso}, crag_triggered=False, crag_verdicts=None)
        return []

    # Hydrate top-pool source content for CRAG.
    top_pool = _hydrate(engine, fused[: max(k * 3, 20)])

    # ---- CRAG verification gate (always-on at deep tier) ----------------
    crag = CragVerifier(engine=engine)
    candidates = [{"id": h.id, "kind": h.kind, "content": h.content} for h in top_pool]
    crag_bundle = crag.prepare(query=query, candidates=candidates)
    if crag_bundle.cached is not None:
        kept_ids: set[int] = set()
        verdicts_meta = []
        for v in crag_bundle.cached.verdicts:
            verdicts_meta.append({"source_id": v.source_id, "score": v.score, "verdict": v.verdict.value, "reason": v.reason})
            if v.verdict == CragVerdict.KEEP:
                kept_ids.add(v.source_id)
            elif v.verdict == CragVerdict.MERGE:
                # Merge band: keep but with rank softened. We surface them
                # AFTER all keeps in the final order.
                kept_ids.add(v.source_id)
        # Apply: keeps first (in fused order), then merges, then truncate to k.
        keep_set = {v.source_id for v in crag_bundle.cached.verdicts if v.verdict == CragVerdict.KEEP}
        merge_set = {v.source_id for v in crag_bundle.cached.verdicts if v.verdict == CragVerdict.MERGE}
        keeps_ordered = [h for h in top_pool if h.id in keep_set]
        merges_ordered = [h for h in top_pool if h.id in merge_set]
        final = (keeps_ordered + merges_ordered)[:k]
        if return_trace:
            return final, DeepRecallTrace(
                variants_used=variants,
                filters_applied={"kinds": kinds, "since_iso": since_iso, "until_iso": until_iso},
                crag_triggered=True,
                crag_verdicts=verdicts_meta,
            )
        return final

    # CRAG cache miss: skip verification, return fused top-k.
    final = top_pool[:k]
    if return_trace:
        return final, DeepRecallTrace(
            variants_used=variants,
            filters_applied={"kinds": kinds, "since_iso": since_iso, "until_iso": until_iso},
            crag_triggered=False,
            crag_verdicts=None,
        )
    return final


def _filter_by_time(engine: Engine, ids: list[tuple[int, float]], *, since_iso: str | None, until_iso: str | None) -> list[tuple[int, float]]:
    from sqlalchemy import text
    from brain.db import session_scope

    raw_ids = [d for d, _ in ids]
    if not raw_ids:
        return ids
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id FROM sources WHERE id = ANY(:ids) "
                "  AND (:since::timestamptz IS NULL OR created_at >= :since::timestamptz) "
                "  AND (:until::timestamptz IS NULL OR created_at <= :until::timestamptz)"
            ),
            {"ids": raw_ids, "since": since_iso, "until": until_iso},
        ).all()
        keep = {int(r.id) for r in rows}
    return [(d, s) for d, s in ids if d in keep]


def _hydrate(engine: Engine, ids_with_scores: list[tuple[int, float]]) -> list[RecallHit]:
    from sqlalchemy import text
    from brain.db import session_scope

    if not ids_with_scores:
        return []
    raw_ids = [d for d, _ in ids_with_scores]
    score_by_id = {d: s for d, s in ids_with_scores}
    with session_scope(engine) as s:
        rows = s.execute(
            text(
                "SELECT id, kind, content, project_id FROM sources "
                "WHERE id = ANY(:ids) AND t_valid_to IS NULL"
            ),
            {"ids": raw_ids},
        ).all()
    by_id = {int(r.id): r for r in rows}
    out: list[RecallHit] = []
    for sid, score in ids_with_scores:
        r = by_id.get(sid)
        if r is None:
            continue
        out.append(RecallHit(id=int(r.id), kind=r.kind, content=r.content, score=float(score), project_id=r.project_id))
    return out
```

- [ ] **Step 4: Add `--deep` flag to `brain recall` in `src/brain/cli.py`**

Find the existing `recall` Click subcommand. Add a flag:

```python
@click.option("--deep", is_flag=True, default=False,
              help="Deep tier: multi-query + Self-Query + CRAG verification. ~3s p99 vs ~500ms Fast.")
```

Inside the command body, branch:

```python
if deep:
    from brain.retrieval.deep import recall_deep
    hits = recall_deep(engine, query, k=k, project_id=project_id, embedder=embedder, reranker=reranker, tau=tau)
else:
    hits = recall(engine, query, k=k, project_id=project_id, embedder=embedder, reranker=reranker, tau=tau)
```

Match the existing parameter wiring. Do not change Fast-tier defaults.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_recall_deep.py tests/test_multi_query.py tests/test_self_query.py tests/test_crag_verify.py -v`
Expected: PASS — all green.

- [ ] **Step 6: Smoke the CLI**

```bash
.venv/bin/brain recall --deep "FTS pipeline" --k 5
```

Should run without errors (returns whatever the current dev brain has).

- [ ] **Step 7: Commit**

```bash
git add src/brain/retrieval/deep.py src/brain/cli.py tests/test_recall_deep.py
git commit -m "feat(phase-3b): recall_deep + brain recall --deep tier"
```

---

## Task 5: Eval extension (20 → 50+ questions) + `--deep` arm

**Files:**
- Modify: `eval/questions.yaml`
- Modify: `eval/run_ab.py`
- Create: `docs/phase-3b-retrieval-hardening.md`

- [x] **Step 1: Inventory the current brain for new eval-question candidates**

Run:

```bash
.venv/bin/brain recall --k 200 "decision OR gotcha OR pattern" --json > /tmp/inventory.json
```

(Or query the DB directly: `SELECT id, kind, LEFT(content, 120) FROM sources WHERE kind = ANY('{decision,gotcha,pattern,note,faq}') AND t_valid_to IS NULL AND parent_id IS NULL ORDER BY created_at DESC LIMIT 200;`.)

Pick ~30 sources to author new questions against. Aim for a mix:
- 10 vocab-match (query uses same words as the capture)
- 12 paraphrase (different vocab, same concept)
- 6 synonym/heavy-reword
- 4 control (no expected hit)

Write each as a question entry in `eval/questions.yaml`, following the existing schema:

```yaml
- id: q21
  query: "<natural-language query>"
  expected_source_ids: [<parent source ID>]
  tags: [<paraphrase|vocab_match|synonym|control>]
```

Append to the existing list. End-state: at least 50 questions total (20 original + 30 new), with 4–6 controls.

- [x] **Step 2: Add `--with-deep` arm to `eval/run_ab.py`**

Find the existing `--with-rerank` flag pattern. Add an analogous `--with-deep` flag. Inside the per-question loop, when `args.with_deep` is True, call `recall_deep(engine, query, k=K)` and record its hits under a `deep` arm alongside `fts` and `hybrid`.

The arm comparison table needs a new column. Update the per-arm aggregation and the final report.

> **Note:** running `--with-deep` requires the agent to also synthesize multi-query / self-query / CRAG outputs interactively because there's no embedded LLM. In practice the eval-run-with-deep is a two-pass workflow: (1) the eval script pre-warms reasoning_cache by running `recall_deep()` once per query and asking the operator (or a subagent) to fill in the prepared bundles; (2) the second pass executes cleanly from cache. Document this in the eval script's `--help` and in the ops doc.

For Phase 3b ship, the minimum is: `--with-deep` ARM is wired and reports cleanly when the cache is warm. End-to-end LLM-in-the-loop eval is a v0.12.1 follow-up; out of scope here.

- [x] **Step 3: Write `docs/phase-3b-retrieval-hardening.md`**

Sections:
1. **Overview** — what Phase 3b adds on top of Phase 2 (hybrid + rerank).
2. **The three new layers** — multi-query, Self-Query, CRAG. Diagrams of the composition.
3. **CLI: `brain recall --deep`** — when to use, latency budget, how cache warming works.
4. **GroundedHelper agent flow** — sequence diagram of prepare → agent synth → finalize for each helper.
5. **Eval methodology** — questions.yaml structure, how to add new questions, how to run the `--with-deep` arm.
6. **Known limits** — temporal filtering is post-hoc (not pushdown), CRAG cache miss falls back to skip-verification, no HyDE or query-decomposition (those land in Phase 3c/4).
7. **Roadmap** — Phase 3c (multi-vector retrieval), Phase 4 (HyDE, query decomposition).

~120-180 lines, terse technical voice.

- [x] **Step 4: Run the eval to confirm shape**

```bash
.venv/bin/python eval/run_ab.py
# Expected: prints hit@1/3/5 for FTS + hybrid arms across 50+ questions.
.venv/bin/python eval/run_ab.py --with-deep
# Expected: prints a `deep` column. With cold cache, deep ≈ Fast-tier (no LLM
# means single-variant + no CRAG); the column reports that explicitly.
```

- [x] **Step 5: Update the v2 spec status table**

In `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md`, find the line near the "Phase 3b — Retrieval hardening (Deep tier) — ⚠️ PARTIAL" block. Update the status from PARTIAL to SHIPPED. Update per-bullet checkboxes for multi-query / Self-Query / CRAG / `--deep`. Note the eval extension explicitly.

- [x] **Step 6: Commit**

```bash
git add eval/questions.yaml eval/run_ab.py \
        docs/phase-3b-retrieval-hardening.md \
        docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md
git commit -m "docs(phase-3b): eval extension to 50+ questions + ops doc + spec status"
```

---

## Self-review checklist

- [x] Task 1 (multi-query) — helper + tests + commit.
- [x] Task 2 (Self-Query) — helper + tests + commit.
- [x] Task 3 (CRAG) — helper + tests + commit.
- [x] Task 4 (`recall_deep` + CLI) — wrapper + flag + integration tests + commit.
- [x] Task 5 (eval + docs + spec) — 50+ Qs, `--with-deep` arm, ops doc, spec status update.
- [x] No placeholders. Every code step shows complete code.
- [x] Type names consistent: `MultiQueryExpansion`, `MultiQueryExpander`, `QueryFilters`, `QueryFilterExtractor`, `CragVerification`, `CragCandidateVerdict`, `CragVerdict`, `CragVerifier`, `DeepRecallTrace`, `recall_deep`.
- [x] Frequent commits — five total, one per task.
- [x] Tests independent (use `pg_url` fixture + autouse `_truncate_tables`).
- [x] GroundedHelper pattern preserved across all three new helpers (no embedded LLM).
- [x] `recall()` Fast-tier surface unchanged; `recall_deep()` is the new entry point.
