---
name: brain-cite
description: Use when you need to ground a claim in verbatim source spans before answering. Brain renders the prompt + schema + cache key; you identify supporting spans inline (one verbatim quote per source); brain validates that each excerpt actually appears in the cited source and strips hallucinations.
---

# brain-cite

Source-span grounding with built-in hallucination defense.

## When to use

- Before asserting a non-trivial claim to the user — confirm the brain actually contains the evidence.
- When the user asks "where did you read that?" and you need to point at specific source spans.
- After `brain recall` returns ambiguous hits and you need to verify which sources actually support a specific point.

## When NOT to use

- The claim is the user's input verbatim (no grounding needed).
- The claim is trivially derivable from one source you just read.

## How

### Step 1 — prepare

```bash
bash skills/brain-cite/scripts/cite.sh prepare --claim "<claim text>" --source-ids 1,2,5
```

Returns `{cache_key, schema, prompt, cached}`. If `cached` is non-null, use it directly. Done.

### Step 2 — synthesize inline

Read `prompt`. For each candidate source, decide if any contiguous span supports the claim. Output JSON with a `supporting_sources` array. Each entry needs `source_id`, `span_start`, `span_end`, and `excerpt` — copied **verbatim** from the source body. Omit sources that don't support the claim.

### Step 3 — finalize

```bash
bash skills/brain-cite/scripts/cite.sh finalize --source-ids 1,2,5 --cache-key <hex> --output '<your json>'
```

`finalize` will silently drop any `Support` whose `excerpt` is not a substring of the cited source — those are treated as hallucinations. If everything you cited gets dropped, your excerpts were wrong; re-read the sources and try again.

## Output budget

≤200 tokens to the user. Quote the excerpts; cite by source id.
