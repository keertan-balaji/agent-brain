# Agent Brain v2 — Phase 2.5 Operations

Phase 2.5 pivots all reasoning helpers + ingest-time summarization from embedded-Haiku to **agent-driven**. The brain prepares prompts + JSON schemas + cache keys; the calling agent (Claude Code, Cursor, etc.) synthesizes inline using its own context; the brain validates against the schema and persists. **No Anthropic API key required**.

## What changed (vs. Phase 2)

- Removed: `AnthropicClient`, `BudgetExceeded`, `LlmResult`, `cost_log` table, `anthropic` + `pyyaml` deps, `--api` pytest flag.
- Reshaped: every reasoning helper (`summarize`, `compare`, `cite`, `revise`) now has a `prepare(...)` and `finalize(...)` Python pair, plus a `brain <helper> prepare/finalize` CLI sub-group.
- Reshaped: `brain.ingest_source()` drops `llm_client`; new `ingest_prepare_contexts` + `ingest_finalize_contexts` flow for agent-driven Contextual Retrieval.
- Cache key formula: `sha256(helper_name + input_hash + prompt_ver)` (model fields dropped).
- Unchanged: hybrid retrieval (FTS + BGE-M3 + RRF + mxbai cross-encoder), provenance defenses (down-weight + diversity cap + tau abstain), Phase 1/2 schema (minus `cost_log`).

## Setup

No API key needed. Standard Python install:

```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
bash skills/brain-setup/scripts/setup.sh
brain --help
```

First use of a reasoning helper or `brain recall` will lazy-download BGE-M3 (~2GB) and (if reranker is used) mxbai-rerank-large-v2 (~1GB). Models cache under `~/.cache/huggingface/hub/`.

## Using reasoning helpers (worked example: summarize)

```bash
# 1. Brain renders the prompt + schema + cache key, returns cached output if present
$ brain summarize prepare --source-ids 1,2,5
{
  "cache_key": "5f3a7c8b...",
  "schema": {"type": "object", "required": ["summary", "citations"], ...},
  "prompt": "You are summarizing the following sources for a coding agent...\n\n[id=1]\n...",
  "cached": null
}

# 2. (Agent synthesizes inline, emits JSON matching the schema)

# 3. Brain validates against the schema and persists
$ brain summarize finalize --cache-key 5f3a7c8b... --output '{"summary":"...","citations":[1,2,5]}'
{"summary": "...", "citations": [1, 2, 5]}
```

If `cached` is non-null on `prepare`, the agent uses it directly and skips `finalize`. Cache key drops the LLM model id, so the same prompt yields the same cache row regardless of which agent runs it (cross-agent shareable).

The same `prepare`/`finalize` shape applies to `compare`, `cite`, and `revise`. See each skill's `SKILL.md` for the exact CLI flags.

## When to use brain-ingest-contextual

Default ingest is `brain ingest source <source_id>` — plain chunk + embed. Skip Contextual Retrieval unless the source is long (>2000 tokens) AND will be retrieved frequently. For those, use the 3-step flow:

```bash
brain ingest prepare-contexts <source_id>     # returns per-chunk prompts
# agent synthesizes 1-3 sentence context summaries inline, one per chunk
brain ingest finalize-contexts <source_id> --contexts-json '<json>'
```

This gives the published 35–50% recall lift on long docs without an embedded LLM call.

## Migration from Phase 2

Existing Phase 2 installs:

```bash
source .venv/bin/activate
alembic upgrade head    # runs migration 009: drops cost_log + 3 reasoning_cache columns; truncates cache
```

Existing `reasoning_cache` rows are unreachable under the new 3-field cache key formula anyway, so the truncate is harmless.

Then `uv pip install -e ".[dev]"` to pick up dropped deps (anthropic, pyyaml).

## Known limitations

- **Headless batch ingest (no agent in loop)** cannot use Contextual Retrieval — there's no embedded LLM to generate per-chunk contexts. Either run inside an agent session or skip context summaries (default ingest path).
- **`retrieval_log.selected` still unpopulated** until Phase 3a wires post-hoc updates from hooks. `brain health` tau-rolling ratios will read "no data yet" until then.
- **Hooks (SessionStart/End/UserPromptSubmit/PreCompact) + compaction-survival** remain on Phase 3a.
- **Multi-query fusion + CRAG** remain on Phase 3b.
- **Sparse + ColBERT retrieval legs** remain on Phase 3c.

## Verifying Phase 2.5 locally

```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
bash skills/brain-setup/scripts/setup.sh
pytest -q
# Expected: ~131 passed
```
