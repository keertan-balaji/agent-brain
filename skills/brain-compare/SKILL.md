---
name: brain-compare
description: Use when you need a structured pairwise comparison of two sources (decisions, conflicting docs, before/after notes). Brain renders the prompt + schema + cache key; you synthesize the agreements/disagreements/scope_diff/citations inline; brain validates + persists.
---

# brain-compare

Typed pairwise comparison without burning a second LLM call.

## When to use

- Two competing decisions or designs you want to weigh against each other.
- Conflicting documentation (e.g., README vs ARCHITECTURE.md).
- Before/after comparison after a refactor or rewrite.

## When NOT to use

- More than two sources — use `brain-summarize` then synthesize differences yourself.
- The diff is mechanical (just diff the files).

## How

### Step 1 — prepare

```bash
bash skills/brain-compare/scripts/compare.sh prepare --a-id <int> --b-id <int>
```

Returns `{cache_key, schema, prompt, cached}`. If `cached` is non-null, use it directly. Done.

### Step 2 — synthesize inline

Read `prompt`. Emit JSON matching `schema`: `agreements` (string list), `disagreements` (list of objects with `claim_a`/`claim_b`/`axis`/`source_a_span`/`source_b_span`), `scope_diff` (string), `citations` (int list). Axis is one of `{scope, time, mechanism, evidence}` (loose — other strings accepted).

### Step 3 — finalize

```bash
bash skills/brain-compare/scripts/compare.sh finalize --cache-key <hex> --output '<your json>'
```

If finalize errors, fix the JSON per stderr and retry.

## Output budget

≤300 tokens to the user. Lead with the headline disagreement; defer detail to the cached output.
