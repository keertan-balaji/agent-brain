---
name: brain-revise
description: Use after ingesting a new source that may supersede or contradict existing notes. Brain prepares a prompt + schema that lists neighboring claims; you propose which to invalidate/reassert/create + flag contradictions; brain validates the plan. The helper PROPOSES only — execution is human-gated.
---

# brain-revise

A-MEM neighbor-rewrite planning without burning a second LLM call. Never mutates anything.

## When to use

- Just ingested a source that updates or replaces older notes (changed defaults, deprecated approach, corrected gotcha).
- Reviewing a contentious topic and want to see which existing claims the new source agrees/disagrees with.

## When NOT to use

- The new source is purely additive (no existing claims to revise).
- You haven't ingested the source yet — `revise_prepare` needs the embedding to find neighbors.

## How

### Step 1 — prepare

```bash
bash skills/brain-revise/scripts/revise.sh prepare --source-id <int>
```

Returns `{cache_key, schema, prompt, cached}`. The prompt lists the new source's content + neighbor claims (drawn from `propose_links` over the same source).

### Step 2 — synthesize inline

Read `prompt`. Emit a JSON `RevisionPlan` with:
- `updates`: list of `{claim_id, action, new_subject, new_predicate, new_object}`. `action` is one of `invalidate`/`reassert`/`create`. For `create`, set `claim_id` to `null`.
- `contradictions`: list of `{claim_a_id, claim_b_id, reason}` for direct conflicts.
- `affected_pages`: list of source ids the plan touches (informational).

### Step 3 — finalize

```bash
bash skills/brain-revise/scripts/revise.sh finalize --cache-key <hex> --output '<your json>'
```

Validates against the `RevisionPlan` schema. The plan is **never executed automatically** — surface it to the user; they approve or discard.

## Output budget

≤300 tokens. List the headline `invalidate`s and any contradictions; defer detail to the cached output.
