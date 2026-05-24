---
name: brain-summarize
description: Use after recalling 2+ sources to produce a cited, structured synthesis. Brain prepares the prompt + JSON schema + cache key; you synthesize inline (no extra API call); brain validates + persists. Pure JSON output, ≤500 tokens summary.
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
