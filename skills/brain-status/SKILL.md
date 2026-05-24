---
name: brain-status
description: Use at session start (when not resuming) or when user asks "what's active". Shows active projects, recent captures by kind (past 7 days), and recent unresolved failures. ≤400 tokens.
---

# brain-status

A 10-second snapshot of what the brain currently cares about.

## When to use

- Session start (when you're not resuming a specific task).
- User asks "what am I working on" / "what's active" / "anything blocking?".

## When NOT to use

- You already have a fresh resume bundle (Phase 3a).
- Mid-task — this is for orientation, not lookup.

## How

```bash
bash skills/brain-status/scripts/status.sh
```

Three tables: active projects, captures-by-kind in last 7 days, top-5 recent failures.

## Output budget

≤400 tokens. Summarize the tables in plain prose; don't paste them.
