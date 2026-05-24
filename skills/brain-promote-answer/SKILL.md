---
name: brain-promote-answer
description: Use after a reasoning helper produced a good answer you want preserved as a durable source. Takes a reasoning_cache.cache_key (hex), shows the cached output, confirms, then captures it as a new source row with provenance_kind='synthesized'.
---

# brain-promote-answer

Stop losing well-formed agent answers to chat history.

## When to use

- A reasoning helper (`summarize`, `compare`, `cite`, `revise_on_ingest`) produced an answer worth keeping as a referencable note.
- A "good answer" emerged from a multi-turn chat and you want it findable later.

## When NOT to use

- The answer is trivially derivable from existing sources (just rerun the helper).
- You're unsure of accuracy — promote only after vetting.

## How

```bash
bash skills/brain-promote-answer/scripts/promote.sh <cache_key_hex> [--kind faq] [--yes]
```

Shows the cached output, asks for confirmation, captures with `provenance_kind='synthesized'`. The synthesized down-weight (Task 12) keeps promoted answers from dominating future retrievals.

## Output budget

≤200 tokens. Confirm capture; report new source_id.
