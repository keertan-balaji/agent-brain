---
name: brain-failure
description: Use when an attempt to solve a problem fails in a way worth remembering, when reviewing past failures before retrying an approach, or when invalidating a stale failure that no longer applies. Auto-captures from the Stop hook are best-effort; this skill is the precise record/refine/invalidate surface.
---

# brain-failure

## When to use

- You tried an approach, it didn't work, and the failure isn't obvious from a tool error (e.g. a conceptual misstep, a wrong assumption, a misread spec).
- You're about to retry an approach and want to check whether it's already been tried.
- A previously-captured failure was resolved by external means — invalidate it so it stops surfacing in future retrieval.

## How

```bash
# Record a failure explicitly. Dedup on (target-problem, attempted-approach).
bash skills/brain-failure/scripts/failure.sh record \
  --target-problem "<concise problem statement>" \
  --attempted-approach "<what was tried>" \
  --outcome-evidence "<what went wrong, ≤600 chars>"

# List active failures (last 20 by default).
bash skills/brain-failure/scripts/failure.sh list [--limit N] [--project-id ID]

# Invalidate a failure that no longer applies.
bash skills/brain-failure/scripts/failure.sh invalidate <id> --reason "<one line>"
```

## Output budget

≤200 tokens per call. List output is a compact table — do not paste full
outcome_evidence in your response; cite by id and summarize.
