---
name: brain-decide
description: Use when about to make a non-trivial decision with multiple options worth weighing. Produces a structured ADR (Context / Options / Choice / Consequences) instead of an open-ended decision note. After capture, fill the template via Edit tool.
---

# brain-decide

Force decisions into a comparable structure so you can review them later.

## When to use

- Picking between 2+ options where the trade-offs matter.
- Architectural choices (library, schema shape, deployment target).
- Process changes (CI policy, release cadence).

## When NOT to use

- The "decision" is mechanical (rename, formatting).
- You've already captured a decision note for this issue.

## How

```bash
bash skills/brain-decide/scripts/decide.sh "<title>" [--project <slug>]
```

Captures an ADR-formatted source. The returned `source_id` is what you'll then Edit to fill Context / Options / Choice / Consequences.

## Output budget

≤200 tokens. Just confirm the capture and report the source_id.
