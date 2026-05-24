# Agent Brain v2 — Phase 2 Operations

Phase 2 adds hybrid retrieval (FTS + dense + RRF + cross-encoder rerank), parent-document chunking, Contextual Retrieval at ingest time, provenance-aware ranking, abstain semantics, and a Fast-tier reasoning layer (summarize / compare / cite / propose_links / revise_on_ingest).

## What shipped

- **Schema:** `embeddings_1024` (halfvec(1024) + HNSW cosine), `extracted_claims`, `reasoning_cache`, `cost_log` — alembic migration 008.
- **Pipeline:** `brain.ingest_source()` chunks the source, optionally runs Contextual Retrieval (Haiku), embeds via BGE-M3, persists into `embeddings_1024`.
- **Retrieval:** `brain.recall()` now accepts `embedder=` to enable hybrid (FTS + pgvector kNN, RRF-fused), `reranker=` to add a cross-encoder pass, and `tau=` for abstain semantics.
- **Reasoning helpers:** five Pydantic-validated, prompt-versioned, DB-cached wrappers around Haiku. All obey the grounding contract: cited spans where applicable, strict JSON, retry-and-validate, cache_key sha256.
- **Skills:** `brain-link`, `brain-decide`, `brain-status`, `brain-promote-answer`.
- **Health:** `brain health` gains per-bucket tau-rolling ratio reports (NULL until Phase 3a hooks fill in `selected`).

## Setup

### 1. Anthropic API key

Reasoning helpers + Contextual Retrieval call Claude Haiku. Provide the key via env or config file (precedence order):

```bash
export BRAIN_ANTHROPIC_API_KEY=sk-ant-...
# or
export ANTHROPIC_API_KEY=sk-ant-...
# or write to ~/.config/brain/anthropic_key (one line, no trailing newline)
```

Without a key, ingest still works (skips contextual retrieval) but reasoning helpers will fail.

### 2. Embedding model

BGE-M3 weights (~2GB ONNX) download to `~/.cache/huggingface/hub/` on first use via the `aapot/bge-m3-onnx` HF repo (community-maintained tri-output export — dense vec is the only head used).

Override via:

```python
embedder = BgeM3Embedder()  # default
# To swap models in a future release: change BgeM3Embedder.MODEL_ID + .DIM
```

### 3. Reranker model

mxbai-rerank-large-v2 (~1GB) downloads via sentence-transformers on first use of `MxbaiReranker()`.

## Cost guard

`AnthropicClient(api_key=..., session_budget_usd=0.50)` caps total cost. Helpers raise `BudgetExceeded` on the call that would push over. Set per-session per-helper or per-process; no global state.

## Storage estimates

- `halfvec(1024)` row = ~2KB persisted (2 bytes × 1024 + overhead). 100k chunks ≈ 200MB.
- HNSW index build = `m=16, ef_construction=64`. Plan ~30 minutes for first 100k chunks on RTX 3050 Ti.

## Re-embedding

When swapping embedding models, write a one-off `brain reindex --to <new_model_id>` (not yet shipped; manual loop over `sources` + new INSERT into `embeddings_<dim>` table). Phase 3a will ship the helper.

## Known limitations (deferred to later phases)

- **No hooks yet.** Phase 3a wires SessionStart, SessionEnd, UserPromptSubmit, PreCompact (and compaction-survival resume bundles).
- **No multi-query fusion / CRAG.** Phase 3b.
- **No sparse / ColBERT legs.** Phase 3c (sparse via fastembed `SparseTextEmbedding`, ColBERT via `LateInteractionTextEmbedding`).
- **`selected` column on retrieval_log isn't populated yet** — agent post-hoc updates land Phase 3a. tau-rolling-ratio displays "no data yet" until then.
- **No tree-sitter symbol index** for code search. Phase 4.

## Verifying Phase 2 locally

```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
bash skills/brain-setup/scripts/setup.sh
pytest -q
# Expected: 134 passed
```
