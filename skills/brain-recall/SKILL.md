---
name: brain-recall
description: Use BEFORE non-trivial work, when a topic comes up that may be in the brain, or before brainstorming. Searches the agent brain with FTS (Phase 1 — hybrid retrieval with embeddings comes in Phase 2). Returns top-k structured hits with provenance. Cap output at ≤500 tokens; never dump raw content.
---

# brain-recall

Pull just-enough structured context from the brain before working.

## When to use

- Start of any non-trivial task — *before* you read code.
- User mentions a concept the brain might have notes on.
- Before invoking `superpowers:brainstorming` or `superpowers:writing-plans` on a topic the brain might cover.

## When NOT to use

- The query is about the current diff — read the diff directly.
- The brain is empty (`brain health` shows zero sources). Run `brain-setup` and capture something first.
- You already pulled context for this exact query this session.

## What it does

1. Resolves brain DB connection from `BRAIN_DB_URL` or default docker-compose URL.
2. Calls `brain recall <query> -k 5` (or higher k if needed).
3. Optionally filters: `--project-id`, `--bucket`, `--kind-filter`.
4. Prints a rich-table of `(id, kind, score, content head)`.
5. **The agent must synthesize the table into a ≤500-token brief**. Do not paste the raw table at the user; cite source IDs.

## How

### Step 1 — recall

```bash
bash skills/brain-recall/scripts/recall.sh "<query>" [-k 5] [--project-id N] [--bucket semantic]
```

The script is a passthrough to `brain recall`.

### Step 2 — pick

Choose the 3–5 most relevant hits. If top-1 has low score (`< 0.05`), say "no high-confidence match" and don't fabricate one.

### Step 3 — synthesize

Emit ≤500 tokens with `[brain:<id>]` cites. Phase 2 adds reranker + abstain threshold; Phase 1 is honest about score-only ranking.

## Don't

- Dump raw rows — synthesize.
- Recall the same query twice in one session.
- Skip the score check — a score of 0.0001 is noise.
