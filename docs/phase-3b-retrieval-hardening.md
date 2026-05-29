# Agent Brain v0.12.0 — Phase 3b: Deep-Tier Retrieval Hardening

## Overview

Phase 3b adds a second retrieval tier — the **Deep tier** — on top of the Phase 2 Fast-tier stack (FTS + BGE-M3 dense + RRF + mxbai cross-encoder reranker + tau abstain). Where the Fast tier optimises for latency (~500 ms p99), the Deep tier trades ~3 s p99 for substantially higher recall on paraphrase and synonym queries.

Three new GroundedHelper layers compose around the existing `recall()` pipeline:

| Layer | Helper | What it does |
|---|---|---|
| Self-Query | `QueryFilterExtractor` | Extracts structured filters (kind, project, since/until) from the query string |
| Multi-query | `MultiQueryExpander` | Generates 3–5 lexically diverse variants of the residual query |
| CRAG | `CragVerifier` | Issues a three-way keep/merge/discard verdict per candidate |

The entry point is `recall_deep()` in `src/brain/retrieval/deep.py`. The `brain recall --deep` CLI flag delegates to it.

## The three new layers

### Composition flow

```
User query
    │
    ▼
┌───────────────────────────────────┐
│  Self-Query (QueryFilterExtractor)│
│  Input: raw query string          │
│  Output: {kinds, since, until,    │
│           residual_query}         │
└───────────────────────────────────┘
    │  residual_query
    ▼
┌───────────────────────────────────┐
│  Multi-query (MultiQueryExpander) │
│  Input: residual_query            │
│  Output: [v1, v2, v3, ...]        │
└───────────────────────────────────┘
    │  variants list
    ▼
┌───────────────────────────────────┐
│  Fast-tier recall() × N variants  │
│  (FTS + BGE-M3 + RRF + reranker)  │
│  Pool: k×3 per variant            │
└───────────────────────────────────┘
    │  per-variant ID lists
    ▼
┌───────────────────────────────────┐
│  RRF fusion across variants       │
│  Temporal post-filter (since/until│
│  from Self-Query if set)          │
└───────────────────────────────────┘
    │  fused ranked pool
    ▼
┌───────────────────────────────────┐
│  CRAG (CragVerifier)              │
│  Three-way verdict per candidate: │
│  KEEP | MERGE | DISCARD           │
│  (always-on at deep tier)         │
└───────────────────────────────────┘
    │  keeps (then merges), top-k
    ▼
 RecallHit list
```

### Self-Query

`QueryFilterExtractor` receives the raw query and produces a structured `QueryFilters` payload: `kinds`, `project_hint`, `buckets`, `since_iso`, `until_iso`, `residual_query`. Temporal filters (`since_iso` / `until_iso`) are applied **post-hoc** after RRF fusion — they are not pushed down into the per-variant FTS/vector queries. This is a known limit (see §Known limits).

Cache miss (cold `reasoning_cache`): the original query is used as the residual; no kind or temporal filter is applied.

### Multi-query expansion

`MultiQueryExpander` receives the residual query and returns a list of 3–5 lexically diverse variants. Each variant runs through the full Fast-tier `recall()` independently (with a widened pool of `k×3` to give RRF more material to fuse). The variants are then fused via reciprocal rank fusion.

Cache miss: single-variant mode — effectively identical to calling `recall()` directly.

### CRAG verification

`CragVerifier` receives the original query and the hydrated top pool (up to `max(k×3, 20)` candidates). It issues a three-way verdict per candidate: `KEEP`, `MERGE` (plausibly relevant — surface after all KEEPs), or `DISCARD`. The final result set is `keeps_ordered + merges_ordered`, truncated to `k`.

Cache miss: CRAG is skipped; the fused pool is returned as-is (Fast-tier quality).

## CLI: `brain recall --deep`

```bash
brain recall "how does trunk-based dev work with ephemeral envs" --deep
brain recall "decision about test isolation" --deep --kind decision
brain recall "GPU reranker selection" --deep --limit 5
```

**When to use:**
- Paraphrase and synonym queries where the exact vocabulary is unknown.
- High-stakes recall where a Fast-tier miss would be costly (e.g., before a risky edit).
- During eval runs with `eval/run_ab.py --with-deep`.

**Latency budget:** ~3 s p99 on a warm `reasoning_cache` vs ~500 ms for the Fast tier. On a cold cache the Deep tier degrades to Fast-tier quality at Fast-tier latency — no LLM round-trips are made synchronously.

**Cache warming:** each unique query must have been through a `brain.prepare()` + agent JSON synthesis + `brain.finalize()` round-trip before the cache is warm for that query. Run `brain recall --deep` on representative queries in your project's warm-up script, or use the eval harness with `--with-deep` after seeding the cache manually.

## GroundedHelper agent flow

All three helpers inherit from `GroundedHelper` (Phase 2.5). No embedded LLM client exists in the brain codebase. The flow per helper:

```
1. brain.prepare(input)
   └─ look up reasoning_cache by (helper_name, cache_key)
   └─ if HIT: return PrepareBundle(cached=<parsed output>, prompt=None)
   └─ if MISS: build prompt + JSON schema, return PrepareBundle(cached=None, prompt=<str>)

2. Agent reads bundle.prompt + bundle.schema  [LLM synthesis happens here, outside brain]

3. brain.finalize(cache_key, raw_json_output)
   └─ validate output against Pydantic model
   └─ persist to reasoning_cache(helper_name, cache_key, output_json, prompt_ver)
   └─ return parsed typed output
```

| Helper | `helper_name` | Input | Output model |
|---|---|---|---|
| `QueryFilterExtractor` | `query_filter_extractor` | query string | `QueryFilters` |
| `MultiQueryExpander` | `multi_query_expander` | residual query | `QueryExpansion` |
| `CragVerifier` | `crag_verifier` | query + candidates JSON | `CragResult` |

Cache keys are `SHA-256(helper_name + ":" + prompt_ver + ":" + prompt_text)`.

## Eval methodology

### questions.yaml schema

```yaml
questions:
  - id: q01
    query: "paraphrase of what's in the source"
    expected_source_ids: [6]          # parent source IDs; children count too
    tags: [paraphrase]                # vocab_match | paraphrase | synonym | control

  - id: c01
    query: "nginx reverse proxy config"
    expected_source_ids: []
    tags: [control]
    control: true                     # no relevant content in brain; measures FP rate
```

A hit counts if any `expected_source_ids` entry **or any of its children** appears in the top-k result list.

### Adding new questions

1. Find a substantive source: `brain recall <topic>` or query the DB directly.
2. Write one `vocab_match` query (same words), one `paraphrase` (different words, same intent), optionally one `synonym` (heavy reword).
3. Add `control` questions for topics entirely absent from the brain.
4. Append to `eval/questions.yaml`; keep IDs sequential (`q<N>` for non-controls, `c<N>` for controls).

Current counts: **46 non-control questions + 8 controls = 54 total**.

### Running the eval

```bash
# Standard A/B (FTS vs hybrid):
.venv/bin/python eval/run_ab.py

# Full hybrid with cross-encoder reranker:
.venv/bin/python eval/run_ab.py --reranker auto

# Add deep-tier arm (warm cache recommended):
.venv/bin/python eval/run_ab.py --with-deep

# All arms:
.venv/bin/python eval/run_ab.py --reranker auto --with-deep
```

## Known limits

- **Temporal pushdown is post-hoc.** `since_iso` / `until_iso` from Self-Query are applied to the fused pool *after* recall — the FTS and vector queries still scan all time ranges. A native `WHERE created_at >=` pushdown is Phase 4.
- **CRAG cache miss falls back to skip-verification.** If `crag_verifier` has no cached output for a query+candidates combination, the step is skipped and the fused pool is returned as-is. The eval's cold-cache warning covers this case.
- **No HyDE / query decomposition.** Hypothetical Document Embeddings and multi-hop decomposition are Phase 3c/4.
- **Deep tier writes one `retrieval_log` row per query variant.** On a 5-variant expansion, 5 rows are written. This is analytics-friendly (each variant's latency and hit-rate are independently observable) but means `retrieval_log` row counts are higher under `--deep`.
- **Cache warming is manual.** There is no automated warm-up workflow. Eval with `--with-deep` on a cold cache reports degraded-mode results (equivalent to Fast tier).

## Roadmap

### v0.12.0 (this release)

- `brain recall --deep` CLI integration.
- Three GroundedHelper layers: `MultiQueryExpander`, `QueryFilterExtractor`, `CragVerifier`.
- Eval set extended from 20 to 54 questions; `--with-deep` arm in `eval/run_ab.py`.

### Phase 3c — Multi-vector retrieval

- BGE-M3 sparse leg + ColBERT late interaction (triple-leg RRF via VectorChord).
- Late chunking for long agent-memory notes.
- `--with-deep` warm-up workflow integrated into `brain serve` background task.

### Phase 4 — Power features

- HyDE (hypothetical document embeddings) for keyword-poor queries.
- Query decomposition for multi-hop questions.
- Temporal pushdown into FTS/vector queries (native `WHERE created_at` filter).
- MCP server exposing `brain_recall` and `brain_write` as tools to any MCP client.
