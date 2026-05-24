---
name: brain-ingest-contextual
description: Use when ingesting a long source where retrieval quality matters (long technical docs, multi-section ADRs). Three-step: prepare-contexts emits per-chunk prompts; you generate 1-3 sentence context summaries inline; finalize-contexts embeds them. Skip for short notes — default `brain ingest source` is fine.
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

### Step 1 — prepare

```bash
bash skills/brain-ingest-contextual/scripts/ingest-contextual.sh prepare-contexts <source_id>
```

Returns `{source_id, doc_body, chunks: [{chunk_idx, child_text, prompt}]}`.

### Step 2 — synthesize inline

For each chunk in `chunks`, read its `prompt` and emit a 1-3 sentence context summary that situates the chunk within `doc_body`. Keep it short and search-friendly.

### Step 3 — finalize

Assemble `[{chunk_idx, context}, ...]` JSON. Then:

```bash
bash skills/brain-ingest-contextual/scripts/ingest-contextual.sh finalize-contexts <source_id> --contexts-json '<json>'
```

Brain embeds the (context + chunk) text into `embeddings_1024` and persists each context as a `chunk_context` source row with `provenance_kind='synthesized'`.

## Output budget

Don't echo doc_body or chunk texts back to the user. Confirm with `chunks_created` count.
