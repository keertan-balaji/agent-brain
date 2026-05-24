# Agent Brain v2 — Phase 2.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pivot all reasoning + ingest-time summarization from embedded-Haiku to agent-driven. The brain prepares prompts + JSON schemas + cache keys; the calling agent synthesizes inline (no extra API call); the brain validates against the schema and persists. Delete the entire LLM-coupled surface (`AnthropicClient`, `BudgetExceeded`, `LlmResult`, `cost_log`, `anthropic` / `pyyaml` deps). Add five per-helper skills that teach the calling agent the prepare/synthesize/finalize loop.

**Architecture:** Each Fast-tier helper (`summarize`, `compare`, `cite`, `revise`) becomes two CLI subcommands: `brain <helper> prepare ...` emits `{cache_key, schema, prompt, cached?}` JSON, and `brain <helper> finalize --cache-key <hex> --output '<json>'` validates + persists. `brain ingest` gains a `prepare-contexts`/`finalize-contexts` pair so the calling agent generates per-chunk context summaries inline before BGE-M3 embedding. `GroundedHelper.prepare()`/`finalize()` Python API mirrors the CLI for direct programmatic use. cache_key drops `llm_model_id`/`llm_model_ver` from its hash (irrelevant when there is no embedded LLM); existing Phase 2 cache rows become unreachable and migration 009 truncates the table.

**Tech Stack:** No new runtime deps. Drops `anthropic>=0.40` and `pyyaml>=6.0` from pyproject. Keeps pydantic / sqlalchemy / fastembed / sentence-transformers / tiktoken / nltk / click / rich / alembic.

**Spec reference:** `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md` — Phase 2 section + reasoning_cache DDL + cost_log + cache-key formula updated inline by Task 9. Phase 3a in the spec retains its original meaning: hooks + compaction-survival (this plan does NOT consume that label).

**Naming note:** "Phase 2.5" is a cleanup release sitting between Phase 2 ship and Phase 3a (hooks). Plugin version bumps to `v0.4.0` because the public CLI contract changes (helper subcommands become groups, prepare/finalize split).

---

## Why this refactor

Phase 2 embedded Haiku for two purposes: per-chunk Contextual Retrieval at ingest and the five reasoning helpers. Both are redundant when the brain is invoked by a Claude-family agent — the agent IS already a reasoning LLM, so the embedded-Haiku step is a second LLM call doing what the host could do inline.

The redundancy cost: API key management surface, cost guard machinery, `--api` test plumbing, second auth provider, real-money Anthropic charges that bypass any token budget the host conversation has, and per-test mock plumbing for every helper.

The agent-driven contract preserves the value parts of the grounding contract (Pydantic schema validation, sha256 prompt-versioned cache, retry-on-validation-error semantics) while eliminating the embedded LLM call.

**Trade-off:** if the brain is ever invoked headlessly (cron, CI batch ingest of 10k docs), there is no embedded LLM to do Contextual Retrieval and the agent isn't in the loop to fill chunks one by one. Phase 2.5 accepts that constraint — ingest without context summaries is the default, and a future phase can re-introduce a `--headless-llm <api_key>` opt-in if real demand emerges. Today: zero users running headlessly.

---

## Deviations from Phase 2 spec

| # | Decision | Phase 2 position | Phase 2.5 choice | Reason |
|---|---|---|---|---|
| 1 | Reasoning helpers | Wrap `AnthropicClient.haiku` per call | Two-call CLI + Python API: `prepare` then `finalize` | Agent IS the LLM; embedded-Haiku redundant |
| 2 | Contextual Retrieval | Inline per-chunk Haiku call during `ingest_source` | Agent-driven: `prepare-contexts` then `finalize-contexts` | Same redundancy argument |
| 3 | `AnthropicClient`, `BudgetExceeded`, `LlmResult` | Required wrapper around official SDK | Deleted | Zero callers after T2-T7 |
| 4 | `cost_log` table | Tracks Haiku spend per session | Dropped via migration 009 | No embedded LLM, no spend to log |
| 5 | `reasoning_cache.llm_model_id`/`_ver`/`tokens_used` | Part of cache_key hash + analytics | Columns dropped, cache_key drops these fields | No model variation when agent is the model |
| 6 | `anthropic`/`pyyaml` deps | Required | Removed from `pyproject.toml` | `pyyaml` was speculative (never used); `anthropic` no longer imported |
| 7 | `--api` pytest flag + `use_real_api` fixture | For real-API integration tests | Removed | No real API to integrate with |
| 8 | Cache key formula | `sha256(name + input + model_id + model_ver + prompt_ver)` | `sha256(name + input + prompt_ver)` | Model drops out; cache becomes cross-agent shareable |
| 9 | Existing Phase 2 cache rows | Persist across migrations | Truncated by migration 009 | Cache keys would be unreachable (different hash); dev-only data anyway |

---

## File structure (Phase 2.5 changes)

### Deletions

```
src/brain/llm/client.py                # AnthropicClient + cost guard + Haiku constants
src/brain/llm/contextual.py            # contextualize_chunk (replaced by prepare/finalize halves in ingest)
src/brain/llm/prompts/chunk_context.txt # moved + tweaked into ingest module
tests/test_llm_client.py
tests/test_contextual_retrieval.py     # replaced by contextual ingest tests in test_ingest.py
```

### Modifications

```
pyproject.toml                         # drop anthropic, pyyaml
src/brain/llm/__init__.py              # retitle, remove client/contextual re-exports
src/brain/ingest.py                    # drop llm_client param + add prepare_contexts/finalize_contexts
src/brain/reasoning/base.py            # GroundedHelper: prepare/finalize split + PromptBundle dataclass
src/brain/reasoning/summarize.py       # summarize_prepare / summarize_finalize (drop llm_client)
src/brain/reasoning/compare.py         # same shape
src/brain/reasoning/cite.py            # same shape + excerpt validation moves into finalize
src/brain/reasoning/revise_on_ingest.py # same shape (kept name)
src/brain/models.py                    # remove CostLog ORM class
src/brain/cli.py                       # add new subcommands, remove any LLM client refs
src/brain/alembic/versions/008_phase2_tables.py # unchanged; 009 supersedes
tests/conftest.py                      # drop --api flag + use_real_api fixture; keep bge/mxbai fixtures
tests/test_ingest.py                   # rewrite contextual test to use prepare-contexts/finalize-contexts
tests/test_reasoning_summarize.py      # rewrite to prepare/finalize pattern (no mocks)
tests/test_reasoning_compare.py        # same
tests/test_reasoning_cite.py           # same
tests/test_reasoning_revise_on_ingest.py # same
tests/test_reasoning_cache.py          # update for new GroundedHelper API
tests/test_end_to_end_phase2.py        # delete or rewrite as phase-2.5 e2e
README.md                              # add Phase 2.5 section
.claude-plugin/plugin.json             # version 0.4.0; add 5 new skills
docs/phase2.md                         # replaced by 1-paragraph redirect stub pointing to phase2_5.md
docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md  # spec inline edits (4 sections)
```

### Creations

```
src/brain/alembic/versions/009_drop_llm_coupling.py
skills/brain-summarize/SKILL.md
skills/brain-summarize/scripts/summarize.sh
skills/brain-compare/SKILL.md
skills/brain-compare/scripts/compare.sh
skills/brain-cite/SKILL.md
skills/brain-cite/scripts/cite.sh
skills/brain-revise/SKILL.md
skills/brain-revise/scripts/revise.sh
skills/brain-ingest-contextual/SKILL.md
skills/brain-ingest-contextual/scripts/ingest-contextual.sh
docs/phase2_5.md
tests/test_end_to_end_phase2_5.py
```

---

## The new contract (worked example)

### CLI shape — summarize

```bash
$ brain summarize prepare --source-ids 1,2,5
{
  "cache_key": "5f3a7c8b...",
  "schema": {"type": "object", "required": ["summary", "citations"], "properties": {...}},
  "prompt": "You are summarizing the following sources for a coding agent...\n\n[id=1]\n...",
  "cached": null
}
```

If `cached` is non-null, the agent uses it directly and skips the finalize step.

Agent synthesizes per the prompt + schema, then:

```bash
$ brain summarize finalize --cache-key 5f3a7c8b... --output '{"summary":"...","citations":[1,2,5]}'
{"summary": "...", "citations": [1, 2, 5]}
```

On validation failure, exit code is non-zero and stderr has the Pydantic error message — the agent retries inline.

### Python API shape

```python
from brain.reasoning.summarize import summarize_prepare, summarize_finalize

bundle = summarize_prepare(engine, source_ids=[1, 2, 5])
if bundle.cached is not None:
    out = bundle.cached
else:
    raw_output = agent_synthesize(bundle.prompt, bundle.schema_json)  # caller's job
    out = summarize_finalize(engine, cache_key=bundle.cache_key, raw_output=raw_output)
```

### Skill shape (SKILL.md teaches the agent)

```markdown
# brain-summarize

## When to use
After recalling 2+ sources and wanting a cited, structured synthesis the user (or you) can refer back to.

## How
1. Run `brain summarize prepare --source-ids <comma-sep>`.
2. If `cached` is non-null, use it directly. Done.
3. Else: render the JSON in `prompt` into your reasoning. Emit a JSON object matching `schema`.
4. Run `brain summarize finalize --cache-key <hex> --output '<your json>'` to validate + persist.
5. If finalize errors, fix the JSON per stderr and retry.

## Output budget
≤300 tokens. Just confirm cite + report the summary; don't repeat the schema.
```

---

## Task 1: Migration 009 — drop LLM-coupling tables and columns

**Files:**
- Create: `src/brain/alembic/versions/009_drop_llm_coupling.py`
- Modify: `tests/test_migrations.py`

### Step 1: failing test additions

Append to `tests/test_migrations.py`:

```python
def test_phase2_5_drops_cost_log(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        ).fetchall()
    names = {r[0] for r in rows}
    assert "cost_log" not in names, "cost_log should be dropped in migration 009"


def test_phase2_5_drops_reasoning_cache_llm_columns(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='reasoning_cache'"
            )
        ).fetchall()
    col_names = {r[0] for r in cols}
    for dead in ("llm_model_id", "llm_model_ver", "tokens_used"):
        assert dead not in col_names, f"{dead} should be dropped by migration 009"
    # The structural cache columns must still exist
    for kept in ("cache_key", "helper_name", "input_hash", "prompt_ver", "output_json", "hit_count"):
        assert kept in col_names
```

### Step 2: verify fails

```bash
source .venv/bin/activate && pytest tests/test_migrations.py::test_phase2_5_drops_cost_log tests/test_migrations.py::test_phase2_5_drops_reasoning_cache_llm_columns -v
```

Expected: fail (columns still present, table still present).

### Step 3: write migration 009

Create `src/brain/alembic/versions/009_drop_llm_coupling.py`:

```python
"""Drop LLM-coupling artifacts (cost_log table + reasoning_cache LLM columns).

Phase 2.5 pivots reasoning helpers from embedded-Haiku to agent-driven, so
per-call cost tracking and per-model cache keying become dead weight.

Existing reasoning_cache rows are truncated because their cache_key hashes
include model_id/model_ver and would be unreachable after the column drop.

Revision ID: 009_drop_llm_coupling
Revises: 008_phase2_tables
"""

from __future__ import annotations

from alembic import op

revision = "009_drop_llm_coupling"
down_revision = "008_phase2_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE reasoning_cache")
    op.drop_column("reasoning_cache", "llm_model_id")
    op.drop_column("reasoning_cache", "llm_model_ver")
    op.drop_column("reasoning_cache", "tokens_used")
    op.execute("DROP INDEX IF EXISTS cost_log_session_idx")
    op.drop_table("cost_log")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "cost_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id")),
        sa.Column("helper", sa.Text, nullable=False),
        sa.Column("llm_model", sa.Text, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("usd", sa.Float, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("cost_log_session_idx", "cost_log", ["session_id", "occurred_at"])
    op.add_column("reasoning_cache", sa.Column("llm_model_id", sa.Text, nullable=True))
    op.add_column("reasoning_cache", sa.Column("llm_model_ver", sa.Text, nullable=True))
    op.add_column(
        "reasoning_cache",
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
    )
```

### Step 4: verify pass

```bash
pytest tests/test_migrations.py -v
```

All migration tests pass.

### Step 5: commit

```bash
git add src/brain/alembic/versions/009_drop_llm_coupling.py tests/test_migrations.py
git commit -m "feat: migration 009 — drop cost_log + reasoning_cache LLM columns"
```

---

## Task 2: GroundedHelper refactor — prepare/finalize split + PromptBundle

**Files:**
- Modify: `src/brain/reasoning/base.py`
- Modify: `tests/test_reasoning_cache.py`

### New API shape

```python
@dataclass
class PromptBundle[T: BaseModel]:
    cache_key: bytes
    cache_key_hex: str
    schema_json: dict[str, object]
    prompt: str
    cached: T | None


class GroundedHelper[T: BaseModel]:
    def __init__(self, *, engine: Engine, name: str, prompt_ver: str, output_schema: Type[T]) -> None: ...
    def prepare(self, prompt: str) -> PromptBundle[T]: ...
    def finalize(self, *, cache_key: bytes, raw_output: str) -> T: ...
```

- `prepare`: hash prompt, compute cache_key, lookup; on hit, return PromptBundle with `cached` filled and `prompt` echoed for traceability. On miss, return PromptBundle with `cached=None` so the caller fills in raw_output via `finalize`.
- `finalize`: validate raw_output against `output_schema` (using `model_validate_json`); on ValidationError, raise immediately (the agent retries). On success, persist via `ON CONFLICT (cache_key) DO UPDATE SET hit_count = hit_count + 1`.
- cache_key drops `llm_model_id`/`llm_model_ver`: `sha256(name + b"\\x00" + input_hash + b"\\x00" + prompt_ver)`.

### Step 1: rewrite tests for new shape

Replace `tests/test_reasoning_cache.py` with:

```python
"""GroundedHelper: prepare / finalize / cache via sha256(name+input+prompt_ver)."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel
from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.reasoning.base import GroundedHelper, PromptBundle, cache_key_for


class _Out(BaseModel):
    answer: str


def test_cache_key_is_deterministic_three_field() -> None:
    a = cache_key_for("summarize", b"\x00" * 32, "v1")
    b = cache_key_for("summarize", b"\x00" * 32, "v1")
    assert a == b
    assert len(a) == 32


def test_cache_key_differs_on_input() -> None:
    base = cache_key_for("summarize", b"\x00" * 32, "v1")
    assert cache_key_for("compare", b"\x00" * 32, "v1") != base
    assert cache_key_for("summarize", b"\x01" * 32, "v1") != base
    assert cache_key_for("summarize", b"\x00" * 32, "v2") != base


def test_prepare_returns_bundle_with_no_cache(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t1", prompt_ver="v1", output_schema=_Out
    )
    bundle = helper.prepare("hello prompt")
    assert isinstance(bundle, PromptBundle)
    assert bundle.cached is None
    assert bundle.prompt == "hello prompt"
    assert "answer" in bundle.schema_json["properties"]
    assert bundle.cache_key_hex == bundle.cache_key.hex()


def test_finalize_validates_and_persists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t2", prompt_ver="v1", output_schema=_Out
    )
    bundle = helper.prepare("prompt-a")
    out = helper.finalize(cache_key=bundle.cache_key, raw_output='{"answer":"42"}')
    assert out.answer == "42"
    with session_scope(engine) as s:
        row = s.execute(
            text("SELECT helper_name, hit_count FROM reasoning_cache WHERE cache_key = :k"),
            {"k": bundle.cache_key},
        ).one()
    assert row[0] == "t2"
    assert row[1] == 1


def test_prepare_returns_cached_on_second_call(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t3", prompt_ver="v1", output_schema=_Out
    )
    bundle1 = helper.prepare("prompt-b")
    helper.finalize(cache_key=bundle1.cache_key, raw_output='{"answer":"cached-value"}')
    bundle2 = helper.prepare("prompt-b")
    assert bundle2.cached is not None
    assert bundle2.cached.answer == "cached-value"
    with session_scope(engine) as s:
        n = s.execute(
            text("SELECT hit_count FROM reasoning_cache WHERE cache_key = :k"),
            {"k": bundle2.cache_key},
        ).scalar()
    assert n >= 2  # prepare lookup bumped it


def test_finalize_raises_on_invalid_json(pg_url: str) -> None:
    engine = get_engine(pg_url)
    helper = GroundedHelper[_Out](
        engine=engine, name="t4", prompt_ver="v1", output_schema=_Out
    )
    bundle = helper.prepare("prompt-c")
    with pytest.raises(Exception):
        helper.finalize(cache_key=bundle.cache_key, raw_output="not json")
```

### Step 2: verify failing (or stubs missing)

`source .venv/bin/activate && pytest tests/test_reasoning_cache.py -v` — expect ImportError on PromptBundle and cache_key_for signature mismatch.

### Step 3: rewrite `src/brain/reasoning/base.py`

```python
"""Grounding contract for agent-driven Fast-tier reasoning helpers.

The brain prepares the prompt + JSON schema + cache key; the calling agent
synthesizes inline; the brain validates against the schema and persists.

There is no embedded LLM call. cache_key = sha256(name + input + prompt_ver),
so the same prompt yields the same cache row regardless of which agent runs it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope

T = TypeVar("T", bound=BaseModel)


def cache_key_for(helper_name: str, input_hash: bytes, prompt_ver: str) -> bytes:
    h = hashlib.sha256()
    h.update(helper_name.encode("utf-8"))
    h.update(b"\x00")
    h.update(input_hash)
    h.update(b"\x00")
    h.update(prompt_ver.encode("utf-8"))
    return h.digest()


def _hash_prompt(prompt: str) -> bytes:
    return hashlib.sha256(prompt.encode("utf-8")).digest()


@dataclass
class PromptBundle[T: BaseModel]:
    cache_key: bytes
    cache_key_hex: str
    schema_json: dict[str, object]
    prompt: str
    cached: T | None


class GroundedHelper[T: BaseModel]:
    def __init__(
        self,
        *,
        engine: Engine,
        name: str,
        prompt_ver: str,
        output_schema: Type[T],
    ) -> None:
        self.engine = engine
        self.name = name
        self.prompt_ver = prompt_ver
        self.output_schema = output_schema

    def prepare(self, prompt: str) -> PromptBundle[T]:
        input_hash = _hash_prompt(prompt)
        key = cache_key_for(self.name, input_hash, self.prompt_ver)
        cached: T | None = None
        with session_scope(self.engine) as s:
            row = s.execute(
                text("SELECT output_json FROM reasoning_cache WHERE cache_key = :k"),
                {"k": key},
            ).fetchone()
            if row is not None:
                cached = self.output_schema.model_validate(row[0])
                s.execute(
                    text(
                        "UPDATE reasoning_cache SET hit_count = hit_count + 1 "
                        "WHERE cache_key = :k"
                    ),
                    {"k": key},
                )
        return PromptBundle[T](
            cache_key=key,
            cache_key_hex=key.hex(),
            schema_json=self.output_schema.model_json_schema(),
            prompt=prompt,
            cached=cached,
        )

    def finalize(self, *, cache_key: bytes, raw_output: str) -> T:
        parsed = self.output_schema.model_validate_json(raw_output)
        with session_scope(self.engine) as s:
            input_hash = b""  # not strictly needed at finalize time; column kept for traceability
            s.execute(
                text(
                    """
                    INSERT INTO reasoning_cache(
                        cache_key, helper_name, input_hash, prompt_ver, output_json
                    ) VALUES (
                        :k, :n, :ih, :pv, CAST(:oj AS jsonb)
                    )
                    ON CONFLICT (cache_key) DO UPDATE SET hit_count = reasoning_cache.hit_count + 1
                    """
                ),
                {
                    "k": cache_key,
                    "n": self.name,
                    "ih": input_hash,
                    "pv": self.prompt_ver,
                    "oj": json.dumps(parsed.model_dump(mode="json")),
                },
            )
        return parsed
```

### Step 4: verify pass

`pytest tests/test_reasoning_cache.py -v` — all green.

### Step 5: commit

```bash
git add src/brain/reasoning/base.py tests/test_reasoning_cache.py
git commit -m "refactor: GroundedHelper -> prepare/finalize (agent-driven, no llm_fn)"
```

---

## Task 3: summarize — agent-driven CLI + Python API + SKILL.md

**Files:**
- Modify: `src/brain/reasoning/summarize.py`
- Modify: `src/brain/cli.py` (add `summarize prepare` / `summarize finalize` subcommand group)
- Create: `skills/brain-summarize/SKILL.md`
- Create: `skills/brain-summarize/scripts/summarize.sh`
- Modify: `tests/test_reasoning_summarize.py`

### Step 1: rewrite `src/brain/reasoning/summarize.py`

```python
"""reasoning.summarize: prepare a cited synthesis prompt; finalize validates output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import Engine, text

from brain.db import session_scope
from brain.reasoning.base import GroundedHelper, PromptBundle

_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "summarize.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()
_PROMPT_VER = "v2"  # bumped: prompt unchanged but cache contract changed
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
```

### Step 2: rewrite tests

Replace `tests/test_reasoning_summarize.py` with:

```python
"""summarize_prepare / summarize_finalize: prompt rendering + cache + validation."""

from __future__ import annotations

import json

from brain.db import get_engine
from brain.reasoning.summarize import SummarizeOutput, summarize_finalize, summarize_prepare
from brain.schemas import SourceInput
from brain.write import write


def test_prepare_emits_prompt_with_source_markers(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("alpha source", "beta source"):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    bundle = summarize_prepare(engine, source_ids=ids)
    assert bundle.cached is None
    for sid in ids:
        assert f"[id={sid}]" in bundle.prompt
    assert "summary" in bundle.schema_json["properties"]
    assert "citations" in bundle.schema_json["properties"]


def test_finalize_validates_and_returns_typed(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("postgres is open source",):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    bundle = summarize_prepare(engine, source_ids=ids)
    raw = json.dumps({"summary": "postgres summary", "citations": ids})
    out = summarize_finalize(engine, cache_key=bundle.cache_key, raw_output=raw)
    assert isinstance(out, SummarizeOutput)
    assert out.summary == "postgres summary"
    assert out.citations == ids


def test_prepare_second_call_returns_cached(pg_url: str) -> None:
    engine = get_engine(pg_url)
    ids = []
    for body in ("alpha", "beta"):
        r = write(engine, SourceInput(kind="note", content=body))
        ids.append(r.source_id)
    bundle1 = summarize_prepare(engine, source_ids=ids)
    raw = json.dumps({"summary": "alpha and beta", "citations": ids})
    summarize_finalize(engine, cache_key=bundle1.cache_key, raw_output=raw)
    bundle2 = summarize_prepare(engine, source_ids=ids)
    assert bundle2.cached is not None
    assert bundle2.cached.summary == "alpha and beta"
```

### Step 3: add CLI subcommand group

In `src/brain/cli.py`, replace any existing `summarize` reference and add (use Click sub-group):

```python
@main.group()
@click.pass_context
def summarize(ctx: click.Context) -> None:
    """Prepare/finalize the summarize reasoning helper."""


@summarize.command("prepare")
@click.option("--source-ids", required=True, help="Comma-separated source ids")
@click.pass_context
def summarize_prepare_cmd(ctx: click.Context, source_ids: str) -> None:
    from brain.reasoning.summarize import summarize_prepare as _prep

    ids = [int(x) for x in source_ids.split(",") if x.strip()]
    bundle = _prep(ctx.obj["engine"], source_ids=ids)
    payload = {
        "cache_key": bundle.cache_key_hex,
        "schema": bundle.schema_json,
        "prompt": bundle.prompt,
        "cached": bundle.cached.model_dump(mode="json") if bundle.cached else None,
    }
    click.echo(json.dumps(payload, indent=2))


@summarize.command("finalize")
@click.option("--cache-key", required=True, help="Hex cache key from prepare")
@click.option("--output", required=True, help="JSON output string to validate")
@click.pass_context
def summarize_finalize_cmd(ctx: click.Context, cache_key: str, output: str) -> None:
    from brain.reasoning.summarize import summarize_finalize as _fin

    out = _fin(ctx.obj["engine"], cache_key=bytes.fromhex(cache_key), raw_output=output)
    click.echo(json.dumps(out.model_dump(mode="json"), indent=2))
```

### Step 4: skill files

Create `skills/brain-summarize/SKILL.md`:

```markdown
---
name: brain-summarize
description: Use after recalling 2+ sources to produce a cited, structured synthesis you (or the user) can refer back to. Brain prepares the prompt + JSON schema + cache key; you synthesize inline (no extra API call); brain validates + persists. Pure JSON output, ≤500 tokens summary.
---

# brain-summarize

Structured cited synthesis without burning a second LLM call.

## When to use

- After `brain recall` returns 2+ relevant hits and the user wants a synthesis.
- Before answering "what does the brain say about X" — produces a citation-grounded answer you can quote.

## When NOT to use

- Single-source recall (just summarize that source directly).
- Asking about content you can read in 50 tokens.
- The exact same source set was summarized this session.

## How

### Step 1 — prepare

```bash
bash skills/brain-summarize/scripts/summarize.sh prepare --source-ids 1,2,5
```

Returns `{cache_key, schema, prompt, cached}`. If `cached` is non-null, use it directly. Done.

### Step 2 — synthesize inline

Read `prompt`. Emit a JSON object matching `schema`. Keep `summary` ≤500 tokens. `citations` is an array of integer source ids you drew from.

### Step 3 — finalize

```bash
bash skills/brain-summarize/scripts/summarize.sh finalize --cache-key <hex> --output '<your json>'
```

If finalize errors, read the stderr message and retry the JSON.

## Output budget

≤300 tokens to the user. Quote the summary; cite sources by id.
```

Create `skills/brain-summarize/scripts/summarize.sh`:

```bash
#!/usr/bin/env bash
# brain-summarize: thin wrapper around `brain summarize`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <prepare|finalize> [args...]\n" "$0" >&2
  exit 1
fi

exec brain summarize "$@"
```

`chmod +x`.

### Step 5: verify + commit

```bash
pytest tests/test_reasoning_summarize.py -v
brain summarize --help  # should show prepare + finalize
git add src/brain/reasoning/summarize.py src/brain/cli.py skills/brain-summarize/ tests/test_reasoning_summarize.py
git commit -m "feat: summarize agent-driven (prepare/finalize + CLI group + skill)"
```

---

## Task 4: compare — same shape as Task 3

**Files:**
- Modify: `src/brain/reasoning/compare.py`
- Modify: `src/brain/cli.py` (add `compare prepare` / `compare finalize` group)
- Create: `skills/brain-compare/SKILL.md`
- Create: `skills/brain-compare/scripts/compare.sh`
- Modify: `tests/test_reasoning_compare.py`

Apply the exact pattern from Task 3 to compare:

- `compare_prepare(engine, *, a_source_id, b_source_id) -> PromptBundle[CompareOutput]`
- `compare_finalize(engine, *, cache_key, raw_output) -> CompareOutput`
- Click group `@main.group()` named `compare` with `prepare` and `finalize` subcommands
- SKILL.md teaches: when comparing two sources (decisions, gotchas, conflicting docs), prepare/synthesize/finalize loop
- Bump `_PROMPT_VER` to `"v2"`
- Tests use the prepare/finalize pattern, not MagicMock

Commit: `git commit -m "feat: compare agent-driven (prepare/finalize + CLI group + skill)"`.

---

## Task 5: cite — same shape, excerpt validation in finalize

**Files:**
- Modify: `src/brain/reasoning/cite.py`
- Modify: `src/brain/cli.py` (add `cite` group)
- Create: `skills/brain-cite/SKILL.md`
- Create: `skills/brain-cite/scripts/cite.sh`
- Modify: `tests/test_reasoning_cite.py`

Same pattern as Task 3, with one extra: `cite_finalize` does the verbatim-excerpt validation that Phase 2's helper did. After Pydantic parsing, drop any `Support` entry whose `excerpt` is not a substring of its `source_id`'s content (the entries are simply removed; finalize does not raise on a drop).

```python
def cite_finalize(
    engine: Engine,
    *,
    claim_text: str,
    candidate_source_ids: list[int],
    cache_key: bytes,
    raw_output: str,
) -> CiteOutput:
    helper = _helper(engine)
    parsed: CiteOutput = helper.finalize(cache_key=cache_key, raw_output=raw_output)
    sources = _load_sources(engine, candidate_source_ids)
    kept = [s for s in parsed.supporting_sources if s.excerpt in sources.get(s.source_id, "")]
    parsed.supporting_sources = kept
    # NOTE: we don't re-persist; the cached raw output is preserved as-is.
    return parsed
```

The mutated `parsed` is returned without re-persisting — the cache retains the raw model output (including any hallucinated excerpts) so re-running with a different candidate set still benefits from the cache. Validation is idempotent per-call.

Tests: assert `cite_finalize` returns only verbatim-grounded supports; raw output with hallucinated excerpts → returned `supporting_sources` is filtered.

CLI signature for `cite prepare` needs `--claim` and `--source-ids`; `cite finalize` needs the same plus `--cache-key` and `--output` so it can re-validate excerpts.

Commit: `git commit -m "feat: cite agent-driven (prepare/finalize + excerpt validation + skill)"`.

---

## Task 6: revise — same shape (keep name `revise_on_ingest` in Python, alias `revise` in CLI)

**Files:**
- Modify: `src/brain/reasoning/revise_on_ingest.py`
- Modify: `src/brain/cli.py` (add `revise` group)
- Create: `skills/brain-revise/SKILL.md`
- Create: `skills/brain-revise/scripts/revise.sh`
- Modify: `tests/test_reasoning_revise_on_ingest.py`

`revise_prepare(engine, *, new_source_id, embedder) -> PromptBundle[RevisionPlan]` still calls `propose_links` to gather neighbors + neighbor claims; renders the prompt; calls `helper.prepare`.

`revise_finalize(engine, *, cache_key, raw_output) -> RevisionPlan` is pure pass-through to `helper.finalize` (Pydantic enforces the `action` Literal set already).

CLI subcommand named `revise` (shorter than `revise-on-ingest`). Skill file at `skills/brain-revise/`.

Tests use prepare/finalize pattern. The new source must still be ingested (embeddings populated) before `revise_prepare` so `propose_links` has neighbors to work with.

Commit: `git commit -m "feat: revise agent-driven (prepare/finalize + CLI group + skill)"`.

---

## Task 7: ingest — agent-driven Contextual Retrieval

**Files:**
- Modify: `src/brain/ingest.py`
- Modify: `src/brain/cli.py` (rework `ingest` into a group; add `prepare-contexts` and `finalize-contexts`)
- Create: `skills/brain-ingest-contextual/SKILL.md`
- Create: `skills/brain-ingest-contextual/scripts/ingest-contextual.sh`
- Modify: `tests/test_ingest.py`
- Move: `src/brain/llm/prompts/chunk_context.txt` → `src/brain/ingest_prompts/chunk_context.txt` (so the `llm` package can be slimmed down to nothing in Task 8)

### New shape

```python
@dataclass
class ContextPreparation:
    source_id: int
    doc_body: str
    chunks: list[ChunkPrep]


@dataclass
class ChunkPrep:
    chunk_idx: int
    child_text: str
    prompt: str  # rendered chunk-context prompt for this chunk
```

```python
def ingest_source(
    engine: Engine,
    *,
    source_id: int,
    embedder: BgeM3Embedder,
    child_max_tokens: int = 256,
    parent_max_tokens: int = 1024,
) -> IngestSummary:
    """Chunk + embed without context summaries (default ingest path)."""
    # body identical to current ingest_source minus the llm_client branch


def ingest_prepare_contexts(
    engine: Engine,
    *,
    source_id: int,
    child_max_tokens: int = 256,
    parent_max_tokens: int = 1024,
) -> ContextPreparation:
    """Render per-chunk context prompts so the calling agent can fulfill them
    inline. Caller passes the result back to ingest_finalize_contexts after
    generating one context summary per chunk."""


def ingest_finalize_contexts(
    engine: Engine,
    *,
    source_id: int,
    embedder: BgeM3Embedder,
    contexts: list[ChunkContext],
    child_max_tokens: int = 256,
    parent_max_tokens: int = 1024,
) -> IngestSummary:
    """Insert chunk + chunk_context source rows + contextualized embeddings.
    `contexts` parallels the ChunkPrep list from prepare_contexts."""


@dataclass
class ChunkContext:
    chunk_idx: int
    context: str  # the 1-3 sentence summary the agent produced
```

The chunker runs again inside `ingest_finalize_contexts` (recomputed deterministically) so the agent doesn't have to pass back chunk text. Each `chunk_idx` lines up by position. The finalize call validates `len(contexts) == len(chunks)` and rejects with a clear error if not.

### CLI

`brain ingest` becomes a Click group:

```python
@main.group()
def ingest() -> None: ...

@ingest.command("source")
@click.argument("source_id", type=int)
def ingest_source_cmd(...) -> None:
    # plain ingest, no contexts

@ingest.command("prepare-contexts")
@click.argument("source_id", type=int)
def ingest_prepare_contexts_cmd(...) -> None:
    # emits {source_id, doc_body, chunks: [{chunk_idx, child_text, prompt}]} JSON

@ingest.command("finalize-contexts")
@click.argument("source_id", type=int)
@click.option("--contexts-json", required=True, help="JSON array of {chunk_idx, context}")
def ingest_finalize_contexts_cmd(...) -> None:
    # parses, calls ingest_finalize_contexts, prints IngestSummary
```

### Skill

`skills/brain-ingest-contextual/SKILL.md`:

```markdown
---
name: brain-ingest-contextual
description: Use when ingesting a long source where retrieval quality matters (long technical docs, multi-section ADRs). Three-step: prepare-contexts emits per-chunk prompts, you generate 1-3 sentence context summaries inline, finalize-contexts embeds them. Skip for short notes — default ingest is fine.
---

# brain-ingest-contextual

Anthropic's Contextual Retrieval (35-50% recall lift on long docs) without an embedded LLM call.

## When to use

- The source is >2000 tokens AND will be retrieved frequently.
- You want retrieval to find chunks even when the query terms appear only in the surrounding doc context, not the chunk itself.

## When NOT to use

- Short note (default `brain ingest source` is sufficient).
- One-off paste you won't recall.

## How

1. `brain ingest prepare-contexts <source_id>` — returns `{doc_body, chunks: [{chunk_idx, child_text, prompt}]}`
2. For each chunk: read `prompt`, emit a 1-3 sentence context summary that situates the chunk within the doc. Keep it short and search-friendly.
3. Assemble `[{chunk_idx, context}, ...]` JSON.
4. `brain ingest finalize-contexts <source_id> --contexts-json '<json>'` — embeds with contexts prepended.

## Output budget

Don't read the doc back to the user. Confirm ingest with `chunks_created` count.
```

### Tests

Rewrite `tests/test_ingest.py`:
- `test_short_source_one_chunk_one_embedding` — unchanged (default ingest_source path)
- `test_long_source_multiple_children_with_embeddings` — unchanged
- `test_contextualize_inserts_chunk_context_rows` becomes:

```python
def test_prepare_then_finalize_contexts_inserts_chunk_context_rows(
    pg_url: str, bge_m3_embedder
) -> None:
    engine = get_engine(pg_url)
    body = _make_text(40)
    src = write(engine, SourceInput(kind="note", content=body)).source_id

    prep = ingest_prepare_contexts(engine, source_id=src, child_max_tokens=64, parent_max_tokens=256)
    assert len(prep.chunks) > 1
    contexts = [
        ChunkContext(chunk_idx=c.chunk_idx, context=f"Context summary number {c.chunk_idx}.")
        for c in prep.chunks
    ]
    summary = ingest_finalize_contexts(
        engine,
        source_id=src,
        embedder=bge_m3_embedder,
        contexts=contexts,
        child_max_tokens=64,
        parent_max_tokens=256,
    )
    assert summary.context_summaries_inserted == len(prep.chunks)
    assert summary.embeddings_inserted == len(prep.chunks)
```

Commit: `git commit -m "feat: ingest agent-driven contextual retrieval (prepare/finalize-contexts + skill)"`.

---

## Task 8: cleanup — delete LLM coupling

**Files:**
- Delete: `src/brain/llm/client.py`
- Delete: `src/brain/llm/contextual.py`
- Delete: `tests/test_llm_client.py`
- Delete: `tests/test_contextual_retrieval.py`
- Delete: `tests/test_end_to_end_phase2.py` (replaced by phase-2.5 e2e in Task 9)
- Modify: `src/brain/llm/__init__.py` (now just hosts `prompts/` for chunk_context if not moved; or fully removed)
- Modify: `src/brain/models.py` (drop `CostLog` ORM class; keep ExtractedClaim, ReasoningCache, Embedding1024)
- Modify: `src/brain/ingest.py` (remove any leftover `from brain.llm.client import AnthropicClient`)
- Modify: `pyproject.toml` (remove `anthropic>=0.40` and `pyyaml>=6.0` from `dependencies`)
- Modify: `tests/conftest.py` (remove `pytest_addoption(--api)` block and `use_real_api` fixture)
- Modify: `uv.lock` (regenerate)

### Step 1: scan + delete

```bash
git rm src/brain/llm/client.py src/brain/llm/contextual.py tests/test_llm_client.py tests/test_contextual_retrieval.py tests/test_end_to_end_phase2.py
```

### Step 2: prune imports

```bash
grep -rn "AnthropicClient\|HAIKU_MODEL\|LlmResult\|BudgetExceeded\|CostLog\|from brain.llm.client\|from brain.llm.contextual" src/ tests/
```

For each hit (excluding the files just deleted), remove the import or the dead reference. The reasoning helpers should already be clean after Tasks 3-6.

### Step 3: drop ORM class

In `src/brain/models.py`, delete the `CostLog` class entirely. Keep `Embedding1024`, `ExtractedClaim`, `ReasoningCache`.

### Step 4: drop deps

In `pyproject.toml`, remove the two lines:

```toml
    "anthropic>=0.40",
    "pyyaml>=6.0",
```

Then:

```bash
source .venv/bin/activate && uv pip install -e ".[dev]" && uv lock
```

### Step 5: drop conftest --api flag

Remove `pytest_addoption` and `use_real_api` fixture from `tests/conftest.py`. Keep all other fixtures (`pg_url`, `bge_m3_embedder`, `mxbai_reranker`, autouse truncate fixture).

### Step 6: verify

```bash
pytest -q
```

All tests pass with no `anthropic` import anywhere. Expected count: roughly 134 − (T2 deletes ~5 cache tests + adds ~5 new) − (T3-T6 each replaces 2-3 tests but keeps same count) − (T11 deletes test_llm_client.py = 7 tests) − (deletes test_contextual_retrieval.py = 4 tests) − (deletes test_end_to_end_phase2.py = 1 test) + (T7 keeps test_ingest.py count). Roughly ~125 tests after this task, before T9 adds the new e2e.

### Step 7: commit

```bash
git add -A
git commit -m "chore: delete AnthropicClient + LLM coupling (anthropic/pyyaml deps removed)"
```

---

## Task 9: docs + end-to-end + plugin v0.4.0 + spec inline edits

**Files:**
- Create: `tests/test_end_to_end_phase2_5.py`
- Create: `docs/phase2_5.md`
- Modify: `README.md`
- Modify: `.claude-plugin/plugin.json`
- Modify: `docs/phase2.md` (shrink to redirect stub)
- Modify: `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md` (4 inline edits)

### End-to-end test

Create `tests/test_end_to_end_phase2_5.py`:

```python
"""End-to-end Phase 2.5: write -> ingest -> recall (hybrid+rerank) -> summarize agent-driven."""

from __future__ import annotations

import json

from sqlalchemy import text

from brain.db import get_engine, session_scope
from brain.embed.bge_m3 import BgeM3Embedder
from brain.ingest import ingest_source
from brain.read import recall
from brain.reasoning.summarize import SummarizeOutput, summarize_finalize, summarize_prepare
from brain.retrieval.rerank import MxbaiReranker
from brain.schemas import SourceInput
from brain.write import write


def test_phase2_5_full_pipeline_agent_driven(
    pg_url: str, bge_m3_embedder: BgeM3Embedder, mxbai_reranker: MxbaiReranker
) -> None:
    engine = get_engine(pg_url)
    ids = []
    for kind, body in (
        ("note", "postgres has full text search."),
        ("decision", "we chose pgvector for ops simplicity."),
        ("note", "postgres pgvector supports HNSW with halfvec storage."),
    ):
        r = write(engine, SourceInput(kind=kind, content=body))
        ingest_source(engine, source_id=r.source_id, embedder=bge_m3_embedder)
        ids.append(r.source_id)

    hits = recall(
        engine,
        "postgres pgvector HNSW",
        k=3,
        embedder=bge_m3_embedder,
        reranker=mxbai_reranker,
    )
    assert hits
    assert ids[2] in [h.id for h in hits]

    hit_ids = [h.id for h in hits]
    bundle = summarize_prepare(engine, source_ids=hit_ids)
    assert bundle.cached is None
    assert all(f"[id={sid}]" in bundle.prompt for sid in hit_ids)

    # Agent would synthesize here. Test stand-in:
    fake_output = json.dumps({"summary": "pgvector supports HNSW + halfvec.", "citations": hit_ids})
    out = summarize_finalize(engine, cache_key=bundle.cache_key, raw_output=fake_output)
    assert isinstance(out, SummarizeOutput)
    assert "pgvector" in out.summary

    # Second prepare returns cached
    bundle2 = summarize_prepare(engine, source_ids=hit_ids)
    assert bundle2.cached is not None
    assert bundle2.cached.summary == out.summary

    # retrieval_log captured the recall
    with session_scope(engine) as s:
        row = s.execute(
            text(
                "SELECT query, abstained, top1_score "
                "FROM retrieval_log ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
    assert row[0] == "postgres pgvector HNSW"
    assert row[1] is False
    assert row[2] is not None
```

### docs/phase2_5.md

Create with sections:

- "What changed (vs. Phase 2)" — the pivot in two sentences
- "Setup" — no API key needed; uv install; brain-setup
- "Using reasoning helpers" — copy the worked summarize example from this plan
- "When to use brain-ingest-contextual" — default off; opt in for long docs
- "Migration from Phase 2" — `alembic upgrade head` runs 009; cache is truncated; no other action
- "Known limitations" — same as phase2.md minus the embedded-LLM bits; add: "Headless batch ingest (no agent in loop) cannot use Contextual Retrieval; either run inside an agent session or skip context summaries."

### docs/phase2.md — replace with redirect stub

Overwrite the existing file body with a single-paragraph stub. Keep the title for searchability:

```markdown
# Agent Brain v2 — Phase 2 Operations

> **Superseded by Phase 2.5 (agent-driven reasoning).** The original Phase 2 ops doc described an embedded-Haiku flow that no longer ships: `AnthropicClient`, `BudgetExceeded`, the `cost_log` table, and the `--api` pytest flag were all removed. The hybrid retrieval pipeline (BGE-M3 + RRF + mxbai rerank) and the provenance defenses (down-weight + diversity + tau abstain) are unchanged.
>
> See **[`docs/phase2_5.md`](./phase2_5.md)** for current setup, the prepare/finalize CLI shape, and migration notes.
```

### README

Add a Phase 2.5 section after the Phase 2 section (don't replace), highlighting:
- 5 new agent-facing skills (`brain-summarize`, `brain-compare`, `brain-cite`, `brain-revise`, `brain-ingest-contextual`)
- No Anthropic API key required
- Same hybrid retrieval + reranker stack as Phase 2
- The Phase 2 quick-start block (which exports `BRAIN_ANTHROPIC_API_KEY`) is removed; replace with a Phase 2.5 block that doesn't set the env var

### plugin.json

- Version `0.3.0` → `0.4.0`
- Description: replace "Phase 2 ships hybrid retrieval + Fast-tier reasoning helpers + 4 new skills" with "Phase 2.5 ships agent-driven reasoning helpers (no Anthropic API key required) and 5 new agent-facing skills"
- Append to `skills:` array:
  - `"skills/brain-summarize"`
  - `"skills/brain-compare"`
  - `"skills/brain-cite"`
  - `"skills/brain-revise"`
  - `"skills/brain-ingest-contextual"`
- Keep all existing entries

### Spec inline edits

Open `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md` and make these four edits:

**Edit 1 — line ~1004, cache key formula:**

Before:
> 4. **Cache key = `(helper_name, canonicalized_input_hash, llm_model_id, llm_model_ver, prompt_template_ver)`.** Stored as `reasoning_cache` rows joined to the input sources. Cache hits are exact; prompt-version bump invalidates the cache.

After:
> 4. **Cache key = `(helper_name, canonicalized_input_hash, prompt_template_ver)`.** Stored as `reasoning_cache` rows joined to the input sources. Cache hits are exact; prompt-version bump invalidates the cache. *(Phase 2.5 dropped `llm_model_id`/`llm_model_ver` from the hash — the calling agent IS the model, so per-model partitioning no longer applies. Cache becomes cross-agent shareable.)*

**Edit 2 — lines ~1030-1041, reasoning_cache DDL:**

Before:
```sql
CREATE TABLE reasoning_cache (
  cache_key    BYTEA PRIMARY KEY,
  helper_name  TEXT NOT NULL,
  input_hash   BYTEA NOT NULL,
  llm_model_id TEXT NOT NULL,
  llm_model_ver TEXT NOT NULL,
  prompt_ver   TEXT NOT NULL,
  output_json  JSONB NOT NULL,
  tokens_used  INT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  hit_count    INT NOT NULL DEFAULT 1
);
```

After:
```sql
CREATE TABLE reasoning_cache (
  cache_key    BYTEA PRIMARY KEY,           -- sha256(helper_name + input_hash + prompt_ver)
  helper_name  TEXT NOT NULL,
  input_hash   BYTEA NOT NULL,
  prompt_ver   TEXT NOT NULL,
  output_json  JSONB NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  hit_count    INT NOT NULL DEFAULT 1
);
-- Phase 2.5 dropped llm_model_id, llm_model_ver, tokens_used (no embedded LLM call to track).
```

**Edit 3 — line ~1278, cost_log:**

Before:
> Costs are tracked in `cost_log(session_id, helper, llm_model, tokens_in, tokens_out, usd, occurred_at)`. `brain status` shows current session spend. Strict mode (opt-in) makes caps non-overridable; default mode lets the agent override with `--allow-cost-override` after surfacing the overage.

After:
> *(Phase 2.5 removed cost_log and the cost-cap subsystem entirely; reasoning is now agent-driven, so all token cost is borne by the host agent's session — already budgeted by the host runtime. The cost-cap table above describes the legacy Phase 2 embedded-Haiku model retained for historical context only.)*

**Edit 4 — lines ~1151-1166, Phase 2 description:**

Append a single paragraph at the END of the Phase 2 section (after line 1166):

```markdown
**Post-ship pivot (Phase 2.5):** all five reasoning helpers and Contextual Retrieval were refactored to be agent-driven. The brain prepares the prompt + JSON schema + cache key; the calling agent synthesizes inline; the brain validates and persists. `AnthropicClient`, `BudgetExceeded`, `cost_log`, and the `anthropic` / `pyyaml` dependencies were removed. The schema (embeddings_1024, extracted_claims, reasoning_cache) and the retrieval pipeline (FTS + dense + RRF + cross-encoder + provenance defenses + tau abstain) are unchanged. See `docs/phase2_5.md` and `docs/superpowers/plans/2026-05-24-agent-brain-v2-phase-2-5.md`.
```

This preserves the original Phase 2 record (what shipped + the Haiku coupling that was correct at the time) while telling readers what was reworked.

### Verify

```bash
pytest -q
brain --help
brain summarize --help
brain compare --help
brain cite --help
brain revise --help
brain ingest --help
```

Final test count should be roughly 125-130 (deletes balance new e2e). Commit:

```bash
git add tests/test_end_to_end_phase2_5.py docs/phase2_5.md docs/phase2.md README.md .claude-plugin/plugin.json docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md
git commit -m "docs(phase-2.5): end-to-end test + docs + spec edits + plugin v0.4.0"
```

---

## Self-Review

### Spec coverage

| Goal | Tasks |
|---|---|
| Drop AnthropicClient + dependencies | T8 |
| Drop cost_log + reasoning_cache LLM cols | T1 |
| GroundedHelper prepare/finalize split | T2 |
| Agent-driven CLI + Python API + skill for `summarize` | T3 |
| Same for `compare`, `cite`, `revise` | T4-T6 |
| Agent-driven Contextual Retrieval at ingest | T7 |
| Cleanup + verification | T8 |
| Docs + e2e + plugin bump | T9 |

### Dependency ordering

- T1 (migration) must run first so subsequent tests can persist into the new cache shape.
- T2 (GroundedHelper) before T3-T6 (helpers depend on the new API).
- T3 must finish before T4-T6 because the CLI group pattern + skill template established in T3 is the model the others copy.
- T7 is independent of helpers but depends on T8 NOT yet having deleted `chunk_context.txt` — T7 moves the prompt first, then T8 prunes `src/brain/llm/`.
- T8 (cleanup) runs after T3-T7 so no live imports of the deleted classes remain.
- T9 wraps up.

### Type consistency

Reused: `SourceInput`, `WriteResult`, `RecallHit`, `BgeM3Embedder`, `MxbaiReranker`, `Engine`. New: `PromptBundle[T]`, `ChunkPrep`, `ChunkContext`, `ContextPreparation`. Renamed: `summarize_prepare`/`summarize_finalize` etc. (helper signature changes are documented per task). `SummarizeOutput` / `CompareOutput` / `CiteOutput` / `Support` / `RevisionPlan` / `ClaimUpdate` / `Contradiction` / `LinkProposalList` / `Proposal` unchanged.

### No placeholders

Each task lists exact file paths, full code blocks for the structural pieces, and concrete pytest invocations. Tasks 4 and 6 say "same pattern as Task 3" — and Task 3 carries the full pattern in its body, including code, so the engineer reading T4/T6 has a complete template at hand.

### Risk register

- **prompt_ver bump (`v1` → `v2`)**: invalidates all Phase 2 reasoning_cache rows (already truncated by migration 009). Intentional, documented.
- **Click group renames** (`@main.command(...)` becoming `@main.group()`): any Phase 2 CLI tests relying on `brain summarize <args>` directly will need `brain summarize prepare/finalize ...`. No Phase 2 tests exercise CLI invocation directly; only the helpers' Python API is tested. Skills' shell scripts are the only callers of the CLI.
- **Excerpt validation moves into `cite_finalize` not the cache path**: cache stores raw model output; validation runs per-call. Documented at T5.
- **`ingest_prepare_contexts` + `ingest_finalize_contexts` re-run the chunker independently**: must be deterministic. The chunker (`src/brain/embed/chunker.py`) is pure — same input + same params always yields the same chunks. Guarded by the existing T4 Phase 2 tests.

---

## Execution

Plan complete and saved. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session via executing-plans with checkpoints.

Which approach?
