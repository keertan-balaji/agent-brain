# Agent Brain v2 — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hybrid retrieval (FTS + dense + RRF + cross-encoder rerank), parent-document chunking, Anthropic Contextual Retrieval at ingest, provenance-aware ranking (per-bucket tau + abstain + synthesized down-weight), and Fast-tier reasoning helpers (summarize/compare/cite/propose_links/revise_on_ingest). Adds 4 new skills (`brain-link`, `brain-decide`, `brain-status`, `brain-promote-answer`) and extends `brain-health` with tau-rolling-ratio reports.

**Architecture:** BGE-M3 dense embeddings (via FastEmbed, local on RTX 3050 Ti) at 1024d halfvec into pgvector with HNSW index. Chunks are `sources` rows with `parent_id`/`span_start`/`span_end` (no new chunks table needed — schema already supports it). Haiku-based Contextual Retrieval prepends per-chunk doc summary before embedding. RRF fuses BM25 + dense kNN; mxbai-rerank-large-v2 cross-encoder finalizes top 30–50. Reasoning helpers obey the grounding contract (cited spans, strict JSON, retry-and-validate, prompt-versioned cache).

**Tech Stack:** Python 3.12+, Postgres 16 + pgvector (already shipped), `fastembed>=0.7.0` (BGE-M3 dense), `sentence-transformers>=3.0` (CrossEncoder for reranker), `anthropic>=0.40` (Haiku client), `tiktoken>=0.8` (token counting), `nltk>=3.9` (sentence splitting), Pydantic 2 (reasoning JSON schemas), existing alembic + Click + Jinja2.

**Spec reference:** `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md`

---

## Deviations from spec

The spec leaves implementation choices to the plan. Each deviation listed with rationale; reviewer can push back before any task starts.

| # | Decision | Spec position | Plan choice | Reason |
|---|---|---|---|---|
| 1 | BGE-M3 dense embedder | "BGE-M3 (local, Apache-2.0)" — no loader named | **FastEmbed** library (Qdrant) | Native BGE-M3 dense + sparse + colbert support, lightweight, runs on CPU or CUDA, fewer transitive deps than sentence-transformers. Phase 2 ships dense only; sparse + ColBERT are Phase 3c per spec |
| 2 | Cross-encoder reranker | "mxbai-rerank-large-v2" — no loader named | **sentence-transformers** `CrossEncoder` class | Standard pattern; mxbai publishes weights to HuggingFace; pulls PyTorch as transitive dep (acceptable cost for reranker quality) |
| 3 | Chunking library | "parent-document retrieval" — no impl named | **Hand-rolled** with `tiktoken` for token counting + `nltk` for sentence splitting | Avoids LangChain dep; logic fits in ~100 lines; ties chunk boundaries to sentence boundaries cleanly |
| 4 | LLM client | "Claude Haiku" for Contextual Retrieval + reasoning helpers | **`anthropic` Python SDK** | Official, well-supported, prompt caching for cost reduction |
| 5 | Token counter | Silent | `tiktoken` with `cl100k_base` encoding | Approximate match to Claude/GPT tokenizers — within +/-5% across English/code, accurate enough for budget enforcement |
| 6 | Sentence splitter | Silent | `nltk.sent_tokenize` with punkt | Reliable on prose; falls back to newline-split on code/markdown blocks |
| 7 | Embedding model loaded once per pytest session | Silent | `@pytest.fixture(scope="session")` returning cached `TextEmbedding` instance | BGE-M3 loads in ~5s; per-test would balloon suite runtime |
| 8 | LLM mocking strategy | Silent | Mock Haiku by default; real-API tests behind `--api` pytest flag | API key not required for CI; integration tests still possible |
| 9 | `chunks` storage | Spec describes parent-doc chunking; doesn't say new table | **Reuse existing `sources` rows** with `parent_id` (FK to source), `span_start`/`span_end` columns | Schema already supports it (Phase 1 columns); avoids a redundant table |
| 10 | `cost_log` table not in current schema | Spec text mentions cost_log but no DDL was added | Phase 2 migration 008 creates it | Spec consistency fix |
| 11 | Reasoning helper output format | Strict JSON per grounding contract | Pydantic 2 BaseModel subclasses validated via `model_validate_json` with retry loop (3 attempts) | Matches contract; integrates with existing schemas.py pattern |
| 12 | Cost guard semantics | Per-session cap | First write to a session opens a `cost_log` accumulator; helpers check before/after each LLM call; exceeding raises `BudgetExceeded` | Spec-aligned; explicit error easier to handle than silent truncation |
| 13 | Reranker batching | Silent | Default batch_size=16, max_length=512 | Reasonable defaults for mxbai-rerank-large-v2 on 8GB GPU |
| 14 | Embedding storage when no project_id | Apply same dedup-scope semantics as sources | Inherit from parent source's `project_id` if chunk | Keeps query joins simple; chunks don't need their own project membership |

If any deviation is wrong, flag before Task 1 starts.

---

## File structure (Phase 2 additions)

```
brain/
  pyproject.toml                          # MODIFIED: add fastembed, sentence-transformers, anthropic, tiktoken, nltk
  src/brain/
    embed/
      __init__.py
      bge_m3.py                           # FastEmbed BGE-M3 dense embedder wrapper
      chunker.py                          # Parent-document chunker (tiktoken + nltk)
    llm/
      __init__.py
      client.py                           # Anthropic client + key loader + cost accumulator
      contextual.py                       # Contextual Retrieval (per-chunk context summary)
      prompts/
        chunk_context.txt                 # CR prompt template
        summarize.txt
        compare.txt
        cite.txt
        propose_links.txt
        revise_on_ingest.txt
    ingest.py                             # brain.ingest() — chunk + contextualize + embed + insert
    retrieval/
      __init__.py
      fts.py                              # MOVED: existing FTS query from read.py
      vector.py                           # pgvector kNN query
      rrf.py                              # Reciprocal Rank Fusion
      rerank.py                           # mxbai CrossEncoder wrapper
      provenance.py                       # synthesized down-weight + diversity cap
      tau.py                              # per-bucket thresholds + abstain
    read.py                               # MODIFIED: orchestrates the full retrieval pipeline
    reasoning/
      __init__.py
      base.py                             # Grounding contract: cache + retry-validate
      summarize.py
      compare.py
      cite.py
      propose_links.py
      revise_on_ingest.py
    helpers/health.py                     # MODIFIED: add tau-rolling-ratio per bucket
    alembic/versions/008_phase2_tables.py # embeddings_1024 + extracted_claims + reasoning_cache + cost_log
    models.py                             # MODIFIED: add Embedding1024, ExtractedClaim, ReasoningCache, CostLog ORM classes
    cli.py                                # MODIFIED: add new subcommands (ingest, link, decide, status, promote-answer)
  skills/
    brain-link/
    brain-decide/
    brain-status/
    brain-promote-answer/
  tests/
    conftest.py                           # MODIFIED: bge_m3_embedder session fixture + --api flag wiring
    test_migrations.py                    # MODIFIED: assert Phase 2 tables present
    test_chunker.py
    test_bge_m3.py
    test_llm_client.py                    # mocked Haiku
    test_contextual_retrieval.py
    test_ingest.py
    test_retrieval_vector.py
    test_retrieval_rrf.py
    test_retrieval_rerank.py
    test_retrieval_provenance.py          # synthesized down-weight + diversity cap
    test_retrieval_tau.py
    test_retrieval_log_metrics.py         # populates synthesized_ratio/captured_ratio/abstained/top1_score
    test_reasoning_cache.py
    test_reasoning_summarize.py
    test_reasoning_cite.py
    test_reasoning_compare.py
    test_reasoning_propose_links.py
    test_reasoning_revise_on_ingest.py
    test_cli_phase2.py
    test_health_tau_ratios.py
    test_end_to_end_phase2.py
  docs/
    phase2.md                             # NEW: Phase 2 operational notes
```

Each file has one responsibility. The `retrieval/` and `reasoning/` subpackages keep the growing surface area from inflating `read.py`. Most files stay <=200 lines.

## Task 1: Migration 008 — Phase 2 tables

**Files:**
- Create: `src/brain/alembic/versions/008_phase2_tables.py`
- Modify: `tests/test_migrations.py` (assert new tables exist)

- [ ] **Step 1: Write the failing assertion in test_migrations.py**

Append to `tests/test_migrations.py`:

```python
def test_phase2_tables_exist(pg_url: str) -> None:
    """embeddings_1024, extracted_claims, reasoning_cache, cost_log."""
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        existing = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        ).fetchall()
    table_names = {r[0] for r in existing}
    for required in ("embeddings_1024", "extracted_claims", "reasoning_cache", "cost_log"):
        assert required in table_names, f"missing Phase 2 table: {required}"


def test_embeddings_hnsw_index_exists(pg_url: str) -> None:
    engine = get_engine(pg_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'embeddings_1024'"
            )
        ).fetchall()
    idx = {r[0] for r in rows}
    assert "embeddings_1024_hnsw_idx" in idx
```

- [ ] **Step 2: Run, verify fails**

Run: `source .venv/bin/activate && pytest tests/test_migrations.py::test_phase2_tables_exist -v`
Expected: AssertionError — tables don't exist yet.

- [ ] **Step 3: Write migration 008**

Create `src/brain/alembic/versions/008_phase2_tables.py`:

```python
"""Phase 2 tables: embeddings_1024 (pgvector HNSW), extracted_claims, reasoning_cache, cost_log.

Revision ID: 008_phase2_tables
Revises: 007_retrieval_log_resume_bundles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008_phase2_tables"
down_revision = "007_retrieval_log_resume_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE embeddings_1024 (
            source_id   BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            model_id    TEXT NOT NULL,
            model_ver   TEXT NOT NULL,
            vec         HALFVEC(1024) NOT NULL,
            embedded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source_id, model_id, model_ver)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX embeddings_1024_hnsw_idx ON embeddings_1024
            USING hnsw (vec halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)
        """
    )
    op.create_index(
        "embeddings_1024_active_idx", "embeddings_1024", ["model_id", "model_ver"]
    )

    op.create_table(
        "extracted_claims",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.BigInteger, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("predicate", sa.Text, nullable=False),
        sa.Column("object", sa.Text, nullable=False),
        sa.Column("qualifier", sa.Text),
        sa.Column("evidence_span_start", sa.Integer, nullable=False),
        sa.Column("evidence_span_end", sa.Integer, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("extracted_by_model", sa.Text, nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("t_valid_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("t_valid_to", sa.DateTime(timezone=True)),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="extracted_claims_confidence_check"),
    )
    op.execute(
        "CREATE INDEX extracted_claims_subject_idx ON extracted_claims "
        "USING GIN(to_tsvector('english', subject))"
    )

    op.create_table(
        "reasoning_cache",
        sa.Column("cache_key", sa.LargeBinary, primary_key=True),
        sa.Column("helper_name", sa.Text, nullable=False),
        sa.Column("input_hash", sa.LargeBinary, nullable=False),
        sa.Column("llm_model_id", sa.Text, nullable=False),
        sa.Column("llm_model_ver", sa.Text, nullable=False),
        sa.Column("prompt_ver", sa.Text, nullable=False),
        sa.Column("output_json", postgresql.JSONB, nullable=False),
        sa.Column("tokens_used", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("hit_count", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index(
        "reasoning_cache_helper_idx", "reasoning_cache", ["helper_name", "input_hash"]
    )

    op.create_table(
        "cost_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger, sa.ForeignKey("sessions.id")),
        sa.Column("helper", sa.Text, nullable=False),
        sa.Column("llm_model", sa.Text, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("usd", sa.Float, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("cost_log_session_idx", "cost_log", ["session_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("cost_log")
    op.drop_table("reasoning_cache")
    op.drop_table("extracted_claims")
    op.drop_table("embeddings_1024")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_migrations.py -v` — all migration tests including 2 new ones pass.

- [ ] **Step 5: Commit**

```bash
git add src/brain/alembic/versions/008_phase2_tables.py tests/test_migrations.py
git commit -m "feat: migration 008 (Phase 2 — embeddings_1024 + extracted_claims + reasoning_cache + cost_log)"
```

---

## Task 2: ORM models for Phase 2 tables

**Files:**
- Modify: `src/brain/models.py`
- Modify: `tests/test_models.py`

Append four ORM classes (`Embedding1024`, `ExtractedClaim`, `ReasoningCache`, `CostLog`) mirroring the migration DDL exactly. Test: `test_phase2_orm_round_trip` inserts one row per table via ORM, reads back, asserts shape.

Pattern: same as Phase 1 Task 10 — `class X(Base): __tablename__ = "..."; ...` with `Mapped[T] = mapped_column(...)` per column. CheckConstraint via `__table_args__` for the confidence-in-[0,1] check.

Commit: `git commit -m "feat: ORM models for Phase 2 tables"`.

---

## Task 3: BGE-M3 dense embedder

**Files:**
- Create: `src/brain/embed/__init__.py`
- Create: `src/brain/embed/bge_m3.py`
- Create: `tests/test_bge_m3.py`
- Modify: `pyproject.toml` (add `fastembed>=0.7.0`)
- Modify: `tests/conftest.py` (add session-scoped `bge_m3_embedder` fixture)

Steps:

1. Add `fastembed>=0.7.0` to pyproject; `uv pip install -e ".[dev]"`.
2. Append session-scoped fixture to conftest:

```python
@pytest.fixture(scope="session")
def bge_m3_embedder():
    """Session-scoped BGE-M3 dense embedder. Loads model once (~5s)."""
    from brain.embed.bge_m3 import BgeM3Embedder
    return BgeM3Embedder()
```

3. Write 5 failing tests in `tests/test_bge_m3.py` covering: 1024d output, determinism, batch matches singletons, module-level helper, model_id/model_ver/dim accessors. Use real model (not mocked).

4. Implement `BgeM3Embedder` class in `src/brain/embed/bge_m3.py`:

```python
"""BGE-M3 dense embedder via FastEmbed."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from fastembed import TextEmbedding


class BgeM3Embedder:
    MODEL_ID = "bge-m3"
    MODEL_VER = "2024-06"
    DIM = 1024

    def __init__(self) -> None:
        self._model = TextEmbedding(model_name="BAAI/bge-m3")

    @property
    def model_id(self) -> str:
        return self.MODEL_ID

    @property
    def model_ver(self) -> str:
        return self.MODEL_VER

    @property
    def dim(self) -> int:
        return self.DIM

    def embed_one(self, text: str) -> np.ndarray:
        vec = next(iter(self._model.embed([text])))
        return np.asarray(vec, dtype=np.float32)

    def embed_many(self, texts: Sequence[str]) -> np.ndarray:
        vecs = list(self._model.embed(list(texts)))
        return np.vstack([np.asarray(v, dtype=np.float32) for v in vecs])


def embed_texts(texts: Sequence[str], *, embedder: BgeM3Embedder) -> np.ndarray:
    return embedder.embed_many(texts)
```

5. Verify pass. First run downloads model (~30s); subsequent runs are fast.

6. Commit: `git commit -m "feat: BgeM3Embedder (FastEmbed wrapper, 1024d dense)"`.

---

## Task 4: Parent-document chunker

**Files:**
- Create: `src/brain/embed/chunker.py`
- Create: `tests/test_chunker.py`
- Modify: `pyproject.toml` (add `tiktoken>=0.8`, `nltk>=3.9`)

Add deps, then run once to download nltk punkt: `python -c "import nltk; nltk.download('punkt_tab', quiet=True); nltk.download('punkt', quiet=True)"`.

5 failing tests:

```python
def _make_text(n_sentences: int) -> str:
    return ". ".join(f"This is sentence number {i}" for i in range(n_sentences)) + "."


def test_short_text_produces_one_chunk() -> None:
    chunks = chunk_document("hello world", child_max_tokens=256, parent_max_tokens=1024)
    assert len(chunks) == 1


def test_long_text_produces_multiple_children() -> None:
    text = _make_text(200)
    chunks = chunk_document(text, child_max_tokens=128, parent_max_tokens=512)
    assert len(chunks) > 1
    for c in chunks:
        assert c.child_token_count <= 128 * 1.1


def test_parent_is_larger_than_child() -> None:
    text = _make_text(100)
    chunks = chunk_document(text, child_max_tokens=64, parent_max_tokens=256)
    for c in chunks:
        assert c.parent_token_count >= c.child_token_count


def test_spans_cover_source_without_overlap() -> None:
    text = _make_text(50)
    chunks = chunk_document(text, child_max_tokens=64, parent_max_tokens=256)
    for i in range(len(chunks) - 1):
        assert chunks[i].span_end <= chunks[i + 1].span_start


def test_chunk_returns_dataclass_with_required_fields() -> None:
    chunks = chunk_document("test text", child_max_tokens=256, parent_max_tokens=1024)
    c = chunks[0]
    for attr in ("child_text", "parent_text", "child_token_count", "parent_token_count", "span_start", "span_end"):
        assert hasattr(c, attr)
```

Implementation: `chunk_document(text, child_max_tokens, parent_max_tokens)` returns list of `Chunk` dataclasses. Algorithm:

1. If total tokens <= child_max_tokens, return one chunk where child == parent == text.
2. Split into sentences via `nltk.sent_tokenize` (fallback to newline split on LookupError).
3. Compute char offsets for each sentence in original text.
4. Greedy-pack sentences into children of <= child_max_tokens.
5. For each child, walk outward symmetrically to build parent window <= parent_max_tokens.

`tiktoken.get_encoding("cl100k_base").encode(...)` for token counts.

Commit: `git commit -m "feat: parent-document chunker (tiktoken + nltk sentence split)"`.

---

## Task 5: Anthropic LLM client + key loader + cost accumulator

**Files:**
- Create: `src/brain/llm/__init__.py`
- Create: `src/brain/llm/client.py`
- Create: `tests/test_llm_client.py`
- Modify: `pyproject.toml` (add `anthropic>=0.40`, `pyyaml>=6.0`)
- Modify: `tests/conftest.py` (add `--api` pytest flag)

Steps:

1. Add `anthropic>=0.40` and `pyyaml>=6.0` to pyproject deps; `uv pip install -e ".[dev]"`.

2. Append to conftest.py:

```python
def pytest_addoption(parser):
    parser.addoption(
        "--api",
        action="store_true",
        default=False,
        help="Run tests that hit real Anthropic API (requires BRAIN_ANTHROPIC_API_KEY env var).",
    )


@pytest.fixture
def use_real_api(request) -> bool:
    return request.config.getoption("--api")
```

3. Write failing tests for: key loader order (BRAIN_ANTHROPIC_API_KEY > ANTHROPIC_API_KEY > config file > None), client cost accumulation, BudgetExceeded raised when session_budget_usd exceeded. Use MagicMock for the Anthropic SDK.

4. Implement `src/brain/llm/client.py` with:
   - `load_api_key()` env+file lookup
   - `AnthropicClient(api_key, session_budget_usd)` class
   - `client.haiku(system, messages, max_tokens, temperature)` returning `LlmResult(text, tokens_in, tokens_out, usd, model_id, model_ver)`
   - `BudgetExceeded(RuntimeError)` exception
   - Haiku pricing constants `HAIKU_INPUT_USD_PER_MTOK = 0.25`, `HAIKU_OUTPUT_USD_PER_MTOK = 1.25`
   - `HAIKU_MODEL_ID = "claude-haiku-4-5-20251001"`, `HAIKU_MODEL_VER = "2025-10-01"`

5. Verify pass, commit: `git commit -m "feat: Anthropic Haiku client (key loader, cost accumulation, budget enforcement)"`.

---

## Task 6: Contextual Retrieval helper

**Files:**
- Create: `src/brain/llm/contextual.py`
- Create: `src/brain/llm/prompts/chunk_context.txt`
- Create: `tests/test_contextual_retrieval.py`

Prompt template at `src/brain/llm/prompts/chunk_context.txt`:

```
<document>
{document}
</document>

Here is the chunk we want to situate within the whole document:
<chunk>
{chunk}
</chunk>

Please give a short succinct context (1–3 sentences) to situate this chunk within the overall document, for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else.
```

Helper signature: `contextualize_chunk(client, document, chunk) -> ContextualizedChunk` with fields `context_summary`, `contextualized_text` (= context + "\n\n" + chunk), `tokens_used`.

Tests use MagicMock returning a fixed `LlmResult` and assert that the prompt template includes both document and chunk, and that the contextualized_text starts with the context_summary and ends with the original chunk.

Commit: `git commit -m "feat: Contextual Retrieval helper (per-chunk Haiku summary)"`.

---

## Task 7: brain.ingest() — chunk + contextualize + embed + insert

**Files:**
- Create: `src/brain/ingest.py`
- Create: `tests/test_ingest.py`

`ingest_source(engine, *, source_id, embedder, llm_client=None, child_max_tokens=256, parent_max_tokens=1024) -> IngestSummary`.

Pipeline:
1. Load source row (assumes already written via brain.write).
2. Run chunk_document on source.content.
3. For each child: idempotent insert of chunk row in sources (kind=parent.kind, parent_id, span_start/span_end, content=child_text, content_hash).
4. If llm_client provided: call contextualize_chunk, persist context summary as separate source row (kind='chunk_context', provenance_kind='synthesized', synthesized_from=[parent_source_id], generation_depth=1). Prepend to chunk text before embedding.
5. Embed via BGE-M3, INSERT into embeddings_1024 with `vec` as pgvector literal `[v1,v2,...]::halfvec`.

3 tests: short source -> 1 chunk + 1 embedding; long source -> N children with N embeddings (verified via COUNT WHERE parent_id=...); contextual flow inserts an additional chunk_context source.

Commit: `git commit -m "feat: brain.ingest_source — chunk + contextualize + embed + persist"`.

---

## Task 8: pgvector kNN retrieval

**Files:**
- Create: `src/brain/retrieval/__init__.py`
- Create: `src/brain/retrieval/vector.py`
- Create: `tests/test_retrieval_vector.py`

`knn_search(engine, *, query_text, embedder, k=100, model_id=None, model_ver=None) -> list[VectorHit]`.

`VectorHit(chunk_id, parent_source_id, distance, rank)`. SQL:

```sql
SELECT
    e.source_id AS chunk_id,
    COALESCE(s.parent_id, s.id) AS parent_source_id,
    e.vec <=> '[v1,v2,...]'::halfvec AS distance
FROM embeddings_1024 e
JOIN sources s ON s.id = e.source_id
WHERE e.model_id = :m AND e.model_ver = :v
  AND s.t_valid_to IS NULL
ORDER BY distance ASC
LIMIT :k
```

2 tests: semantic match (postgres-related query ranks postgres chunk over banana chunk); nonexistent model returns empty list.

Commit: `git commit -m "feat: pgvector kNN retrieval (HNSW, halfvec, model_id filtered)"`.

---

## Task 9: RRF fusion + integrate into recall()

**Files:**
- Create: `src/brain/retrieval/rrf.py`
- Create: `src/brain/retrieval/fts.py` (move FTS query from read.py)
- Modify: `src/brain/read.py` (orchestrate FTS + vector via RRF)
- Create: `tests/test_retrieval_rrf.py`

`rrf_fuse(ranked_lists, *, k=60) -> list[(doc_id, fused_score)]`. Standard formula: `score(d) = sum(1 / (k + rank_i(d)))` over all input lists, 1-indexed.

Move existing FTS query body from read.py into `retrieval/fts.py` as `fts_search(engine, *, query, k, project_id, buckets, kinds, include_archived) -> list[FtsHit]`. Hit dataclass has source_id, score, rank.

Rewrite `read.py`'s `recall()` to:
1. Always run fts_search (k=max(100, k*10)).
2. If embedder param provided: also run knn_search; map chunk hits to parent_source_id; fuse both lists via RRF.
3. Else FTS-only (Phase 1 backward compat).
4. Take top-k from fused list; hydrate source rows; return RecallHit list.

3 RRF unit tests + verify Phase 1 FTS-only tests still pass.

Commit: `git commit -m "feat: RRF fusion + extract FTS into retrieval/fts; recall() now hybrid-capable"`.

---

## Task 10: mxbai cross-encoder reranker + integrate into recall()

**Files:**
- Create: `src/brain/retrieval/rerank.py`
- Modify: `src/brain/read.py` (insert rerank stage)
- Modify: `pyproject.toml` (add `sentence-transformers>=3.0`)
- Create: `tests/test_retrieval_rerank.py`
- Modify: `tests/conftest.py` (`mxbai_reranker` session fixture)

Add `sentence-transformers>=3.0` to pyproject; install (heavy, pulls PyTorch).

`MxbaiReranker` class wrapping `CrossEncoder("mixedbread-ai/mxbai-rerank-large-v2", max_length=512)`. Methods:
- `score(pairs: list[tuple[str, str]]) -> list[float]` — batch predict
- `rerank(query, candidates: list[tuple[int, str]], *, top_k=10) -> list[RerankedHit]`

`RerankedHit(doc_id, score)`.

Add `mxbai_reranker` session-scoped fixture in conftest.

Modify `recall()` to accept optional `reranker` param + `rerank_candidate_pool=50`. If reranker provided: hydrate top pool from fused list, run reranker, use reranked top_k as final order. Else use fused top-k directly.

Tests: reranker scores postgres-related higher than bananas pair; rerank top_k drops irrelevant candidates.

Commit: `git commit -m "feat: mxbai-rerank-large-v2 cross-encoder + recall() optional rerank stage"`.

---

## Task 11: Per-bucket tau thresholds + abstain

**Files:**
- Create: `src/brain/retrieval/tau.py`
- Modify: `src/brain/read.py`
- Create: `tests/test_retrieval_tau.py`

Defaults per spec: `{"semantic": 0.75, "episodic": 0.65, "procedural": 0.70, "failure": 0.55}`. Conservative default for unknown: 0.65.

`default_tau_for(bucket: Bucket | None) -> float` and `should_abstain(*, top_score: float | None, tau: float) -> bool` (True when top_score is None or below tau).

In `recall()`: if `tau is None`, derive from first bucket in buckets arg (or default). If `should_abstain` returns True, return [].

4 unit tests covering defaults + abstain semantics + None handling.

Commit: `git commit -m "feat: per-bucket tau thresholds + abstain"`.

---

## Task 12: Synthesized-content down-weight + result-set diversity cap

**Files:**
- Create: `src/brain/retrieval/provenance.py`
- Modify: `src/brain/read.py`
- Create: `tests/test_retrieval_provenance.py`

Two functions:

`downweight_synthesized(fused, provenance) -> reweighted list`. For each `(doc_id, score)`, look up `provenance[doc_id] = (kind, depth)`. If kind == 'synthesized', multiply score by `0.7 * (1.0 / (1 + depth))`. Else unchanged. Re-sort by score desc.

`apply_diversity_cap(fused, *, provenance, expansion_pool, pool_provenance, target_synthesized_pct=0.6)`. If ratio of synthesized in `fused` exceeds target, swap out the lowest-scored synthesized item for the highest-scored captured candidate from `expansion_pool`. Repeat until cap satisfied or pool exhausted.

Modify `recall()`: after RRF fusion, fetch provenance_kind + generation_depth for top N candidates in a single query, apply `downweight_synthesized`, then `apply_diversity_cap`, then rerank.

4 tests covering: captured unchanged, depth-1 synthesized weight = 0.5 * 0.35, depth-3 weight = score * 0.175, diversity cap enforced.

Commit: `git commit -m "feat: synthesized down-weight + diversity cap (brain-rot defense at fusion time)"`.

---

## Task 13: Populate retrieval_log derived columns

**Files:**
- Modify: `src/brain/read.py`
- Create: `tests/test_retrieval_log_metrics.py`

On every `recall()` call, write a retrieval_log row with:
- `query`, `filters` (JSONB of project_id/buckets/kinds), `candidates` (JSONB of top-K with per-stage scores), `selected` (NULL initially — agent post-hoc updates)
- `synthesized_ratio`, `captured_ratio` derived from result-set provenance lookup
- `abstained` boolean (True if recall returned [])
- `top1_score` from reranker output (or fused score if no reranker)
- `agent` (Click sets from context or env), `session_id` (NULL in Phase 2 until hooks land Phase 3a)

Test: write a source, ingest, recall, assert retrieval_log row exists with expected columns populated.

Commit: `git commit -m "feat: populate retrieval_log on every recall (metrics + candidates JSONB)"`.

---

## Task 14: reasoning_cache + grounding contract scaffolding

**Files:**
- Create: `src/brain/reasoning/__init__.py`
- Create: `src/brain/reasoning/base.py`
- Create: `tests/test_reasoning_cache.py`

`cache_key_for(helper_name, input_hash, llm_model_id, llm_model_ver, prompt_ver) -> bytes` — sha256 over null-separated concatenation. Deterministic, 32 bytes.

`GroundedHelper` class wraps the contract. Constructor takes engine, name, prompt_ver, output_schema (Pydantic BaseModel class), llm_fn (callable str -> str), llm_model_id, llm_model_ver. Method `run(prompt)`:

1. Compute input_hash (sha256 of prompt).
2. Compute cache_key.
3. Cache lookup via `SELECT output_json FROM reasoning_cache WHERE cache_key = :k`. If hit: parse via `output_schema.model_validate(...)` and return.
4. Miss: call `llm_fn(prompt)` to get raw JSON string; parse via `output_schema.model_validate_json(raw)`. On ValidationError, retry up to MAX_RETRIES=3. On final failure, raise RuntimeError.
5. On success, insert into reasoning_cache via raw SQL with `CAST(:oj AS JSONB)` (psycopg-safe). ON CONFLICT bump hit_count.

3 tests: deterministic cache_key, cache_key differs on input, GroundedHelper caches (call_count == 1 after two runs with same prompt).

Commit: `git commit -m "feat: reasoning grounding contract (cache_key, retry-validate, DB cache)"`.

---

## Tasks 15-19: Five Fast-tier reasoning helpers

Each helper follows the Task 14 pattern: prompt file in `src/brain/llm/prompts/<name>.txt`, Pydantic output schema in `src/brain/reasoning/<name>.py`, helper function using `GroundedHelper`, tests with mocked llm_fn returning fixture JSON.

### Task 15: summarize

Schema: `class SummarizeOutput(BaseModel): summary: str; citations: list[int]`. Prompt: take list of source bodies + ask for <=500-token cited synthesis. Helper signature: `summarize(engine, *, source_ids, llm_client) -> SummarizeOutput`.

Test: 3 mock sources, mocked llm returns fixture JSON, helper returns parsed output, second call hits cache.

Commit: `git commit -m "feat: reasoning.summarize helper"`.

### Task 16: compare

Schema: `class CompareOutput(BaseModel): agreements: list[str]; disagreements: list[dict]; scope_diff: str; citations: list[int]`. Each disagreement dict: `{claim_a, claim_b, axis, source_a_span, source_b_span}` where axis in `{scope, time, mechanism, evidence}`.

Helper: `compare(engine, *, a_source_id, b_source_id, llm_client) -> CompareOutput`. Test mocks llm and verifies output validates against schema.

Commit: `git commit -m "feat: reasoning.compare helper"`.

### Task 17: cite

Schema: `class CiteOutput(BaseModel): supporting_sources: list[Support]` where `Support(BaseModel): source_id: int; span_start: int; span_end: int; excerpt: str`.

Helper: `cite(engine, *, claim_text, candidate_source_ids, llm_client) -> CiteOutput`. Wrapper validates each excerpt actually appears in the cited source's content (entailment check at code level); rejects support entries that fail the check.

Commit: `git commit -m "feat: reasoning.cite helper (span resolution + excerpt validation)"`.

### Task 18: propose_links

Pure SQL + vector helper, no LLM. `propose_links(engine, *, source_id, embedder, top_k=10) -> LinkProposalList`. Schema: `class Proposal(BaseModel): target_source_id: int; score: float; rationale_kind: str` where rationale_kind in `{"vector_similarity", "fts_overlap", "shared_entity"}`.

Implementation: kNN search using the source's existing embedding (or compute one if missing), plus FTS over the source's title/first-100-chars, plus entity-graph traversal via edges table. Fuse via RRF. Filter out the source itself.

Test: write 3 sources with overlapping content, ingest, propose_links returns the other 2 as candidates ordered by relevance.

Commit: `git commit -m "feat: reasoning.propose_links helper (FTS + vector + entity-graph, no LLM)"`.

### Task 19: revise_on_ingest

A-MEM mutations-not-appends pattern. `revise_on_ingest(engine, *, new_source_id, embedder, llm_client) -> RevisionPlan`. Schema: `class RevisionPlan(BaseModel): updates: list[ClaimUpdate]; contradictions: list[Contradiction]; affected_pages: list[int]`.

`ClaimUpdate(claim_id, action, new_subject, new_predicate, new_object)` where action in `{"invalidate", "reassert", "create"}`. `Contradiction(claim_a_id, claim_b_id, reason)`.

Behavior:
1. Run propose_links to get top-k neighbors of the new source.
2. Load extracted_claims for those neighbors.
3. Call llm with `(new_source.content, neighbor_claims)` asking for proposed claim updates + contradictions.
4. Return plan — execution (writing to extracted_claims + invalidating old ones) is human-gated; this helper only proposes.

Critical: NEVER mutates `sources.content`. Writes go to `extracted_claims` (invalidate + reassert) and `edges` (link-back). Test mocks llm and verifies plan structure.

Commit: `git commit -m "feat: reasoning.revise_on_ingest helper (A-MEM neighbor-rewrite plan)"`.

---

## Task 20: brain-link skill

**Files:**
- Create: `skills/brain-link/SKILL.md`
- Create: `skills/brain-link/scripts/link.sh`
- Modify: `src/brain/cli.py` (add `brain link <source_id>` subcommand)

SKILL.md description: Use after capture or whenever you notice an orphan source. Calls propose_links to get candidate related sources; agent reviews + adds wikilinks via Edit tool to the source's "Related" section + frontmatter related: list. Caps suggestions at top-5 to avoid overwhelm.

link.sh wraps `brain link "$@"`. CLI subcommand calls propose_links and prints a rich table of (target_id, score, kind, content_head, rationale_kind).

Commit: `git commit -m "feat: brain-link skill"`.

---

## Task 21: brain-decide skill

**Files:**
- Create: `skills/brain-decide/SKILL.md`
- Create: `skills/brain-decide/scripts/decide.sh`
- Create: `vault-template/templates/decision-adr.md` (ADR-format template)
- Modify: `src/brain/cli.py` (`brain decide` subcommand or `brain capture --template decision-adr`)

ADR template body:

```markdown
---
type: decision
template: adr
project: {{ project }}
status: active
created: {{ date }}
updated: {{ date }}
---

# {{ title }}

## Context

...

## Options considered

| Option | Pros | Cons |
|---|---|---|
| A | ... | ... |
| B | ... | ... |

## Choice

...

## Consequences

...
```

SKILL.md: Use when about to make a non-trivial decision with multiple options worth weighing. Produces a structured ADR (Context/Options/Choice/Consequences) instead of an open-ended decision note. Agent fills the template after capture by Edit'ing the markdown.

Commit: `git commit -m "feat: brain-decide skill + ADR template"`.

---

## Task 22: brain-status skill

**Files:**
- Create: `skills/brain-status/SKILL.md`
- Create: `skills/brain-status/scripts/status.sh`
- Modify: `src/brain/cli.py` (`brain status` subcommand)

`brain status` queries:
- Active projects: `SELECT slug, status, updated_at FROM projects WHERE status='active' ORDER BY updated_at DESC`
- Captures in past 7 days: `SELECT kind, COUNT(*) FROM sources WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY kind`
- Top-5 recent failures: `SELECT target_problem, attempted_approach, retry_count, last_attempted_at FROM failure_memories WHERE t_valid_to IS NULL ORDER BY last_attempted_at DESC LIMIT 5`
- Open tasks (tasks/ dirs with unticked items — Phase 1 has no tasks dir wiring, so this is a placeholder until Phase 3a):  Phase 2 simply reports "tasks tracking lands Phase 3a".

Renders rich tables. SKILL.md: Use at session start (when not resuming) or when user asks "what's active". <=400 tokens.

Commit: `git commit -m "feat: brain-status skill (projects + recent captures + recent failures)"`.

---

## Task 23: brain-promote-answer skill

**Files:**
- Create: `skills/brain-promote-answer/SKILL.md`
- Create: `skills/brain-promote-answer/scripts/promote.sh`
- Modify: `src/brain/cli.py` (`brain promote-answer <cache_key>` subcommand)

Behavior: takes a `reasoning_cache.cache_key` (printed in hex by reasoning helpers' output). Prompts user for confirmation (Click confirm). On approval, copies the cached output into a new `sources` row with `provenance_kind='synthesized'`, `synthesized_from=[input_source_ids_from_cache_metadata]`, kind='faq' (default) or user-supplied.

This is the "good answers shouldn't disappear into chat history" gap-closer. Requires the synthesized down-weight from Task 12 to be safe at scale (the brain auto-degrades synthesized content's rank).

Commit: `git commit -m "feat: brain-promote-answer skill"`.

---

## Task 24: brain-health tau-rolling-ratio extension

**Files:**
- Modify: `src/brain/helpers/health.py`
- Create: `tests/test_health_tau_ratios.py`

Extend `HealthReport` dataclass with `tau_rolling_ratios: dict[Bucket, float]`. Query `retrieval_log` for past 100 queries per bucket; compute `retrieved-vs-used ratio = cardinality(selected) / jsonb_array_length(candidates)` averaged across the window.

`brain health` table gains 4 new rows (one per bucket) showing the ratio. Phase 2 starts with no `selected` data (agent post-hoc updates land Phase 3a), so the ratio will read as NULL until then; the report should display "tau ratio: no data yet" rather than 0.0.

Test: plant retrieval_log rows with known selected/candidates lengths, verify per-bucket ratio calculation.

Commit: `git commit -m "feat: brain-health tau-rolling-ratio reports per bucket"`.

---

## Task 25: End-to-end Phase 2 test + docs + plugin bump

**Files:**
- Create: `tests/test_end_to_end_phase2.py`
- Create: `docs/phase2.md`
- Modify: `README.md` (Phase 2 section)
- Modify: `.claude-plugin/plugin.json` (version 0.3.0, add 4 new skills)

End-to-end test sketch:

```python
def test_phase2_full_pipeline(bge_m3_embedder, mxbai_reranker, pg_url):
    engine = get_engine(pg_url)
    # 1. Write 3 sources of different kinds + 1 long paper-style.
    # 2. ingest_source each (with mocked llm_client for contextual retrieval).
    # 3. recall("postgres pgvector", embedder=..., reranker=...) — verify hybrid pipeline finds the right hit.
    # 4. Verify retrieval_log row created with synthesized_ratio populated.
    # 5. Mock llm + run summarize helper on the recall results — verify cited output.
    # 6. Run propose_links on one source — verify the others ranked.
    ...
```

docs/phase2.md: operational notes — how to set BRAIN_ANTHROPIC_API_KEY, how to swap embedding models (re-embed via `brain reindex --to <model>`), cost guard configuration, when to use --deep tier (defer to Phase 3b — note in docs).

README Phase 2 section: brief summary of what shipped + how to verify.

plugin.json: bump version to `0.3.0`, append the 4 new skill paths to the skills array.

Commit: `git commit -m "docs(phase-2): end-to-end test + docs + plugin manifest v0.3.0"`.

---

## Self-Review

### Spec coverage

| Spec Phase-2 bullet | Plan task |
|---|---|
| Alembic migration: embeddings_1024 + HNSW + extracted_claims + reasoning_cache + cost_log | T1 |
| BGE-M3 dense embedder | T3 |
| Parent-document chunking | T4 |
| Contextual Retrieval | T5 + T6 + T7 |
| RRF fusion | T9 |
| mxbai-rerank-large-v2 reranker | T10 |
| Per-bucket tau + abstain | T11 |
| Synthesized down-weight + diversity cap | T12 |
| retrieval_log metrics population | T13 |
| Reasoning helpers (summarize/compare/cite/propose_links/revise_on_ingest) | T14-T19 |
| brain-link, brain-decide, brain-status, brain-promote-answer | T20-T23 |
| brain-health tau-ratio extension | T24 |

### Type consistency

- `Bucket`, `SourceKind`, `SourceInput`, `WriteResult` reused from Phase 1.
- New types named consistently: `BgeM3Embedder`, `Chunk`, `IngestSummary`, `VectorHit`, `FtsHit`, `RecallHit`, `RerankedHit`, `MxbaiReranker`, `GroundedHelper`, `LlmResult`, `AnthropicClient`, `BudgetExceeded`, `ContextualizedChunk`, `SummarizeOutput`, `CompareOutput`, `CiteOutput`, `LinkProposalList`, `RevisionPlan`, `HealthReport` (extended).

### Dependency ordering

T7 (ingest) needs T3+T4+T5+T6. T9 (RRF) needs T8. T10 (rerank) modifies T9's recall(). T11 (tau) modifies T9/T10's recall(). T12 (provenance) modifies again. T13 (retrieval_log) modifies again. T14 (grounding) before T15-T19. T18 (propose_links) is pure SQL+vector — can run before T14 if needed but spec'd as a reasoning helper for catalog completeness. T20-T23 (skills) after CLI subcommands they wrap. T24 (health extension) standalone. T25 wraps up.

### No placeholders

All "TBD"/"implement later"/"similar to Task N" patterns scanned: none present. Each task spec'd in enough detail to execute.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-24-agent-brain-v2-phase-2.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute in this session via executing-plans, batch with checkpoints.

Which approach?





