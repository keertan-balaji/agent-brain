---
name: obsidian-recall
description: Use BEFORE starting non-trivial work, when the user mentions a feature/module/concept that may be documented, or before brainstorming/implementation. Searches the Obsidian vault and returns a synthesized brief (≤500 tokens) — never dumps raw note bodies. Replaces ad-hoc grep + Read sprees that burn context.
---

# obsidian-recall

Pull just-enough context from the vault before working.

## When to use

- Start of any non-trivial task — *before* you read code.
- User says: "what do we know about X", "is there a doc for Y", "have we decided about Z".
- Before invoking `superpowers:brainstorming` or `superpowers:writing-plans` on a topic the vault might cover.
- A concept appears in the conversation that you don't have full context for.

## When NOT to use

- The query is about the *current* file or current diff — read those directly.
- The vault is brand new and obviously empty — run `obsidian-setup` instead.
- You already pulled vault context for the same topic this session.

## What it does

1. Resolves vault path from `$OBSIDIAN_VAULT` or defaults to `$HOME/Documents/ObsidianVault`.
2. Calls `recall-search.sh <vault> <query>` to get up to 5 paths ranked by section priority (knowledge > projects > agent-memory > daily).
3. Reads each hit (using the Read tool).
4. Emits a synthesis with this shape, in ≤500 tokens:

   ```
   Vault recall — "<query>"
   - **[note title]** (`<path>`): one-sentence claim or finding.
   - …
   No-hits sections (so the user knows): <list>
   ```

5. If zero hits: emit `No vault notes for "<query>"` and proceed; suggest `obsidian-capture` once a finding emerges.

## How

### Step 1 — resolve vault

```bash
VAULT=$(bash skills/obsidian-setup/scripts/resolve-vault.sh)
```

Honors env > persisted `.vault-path` > default. Set once via `obsidian-setup`.

### Step 2 — search

From the brain repo root:

```bash
bash skills/obsidian-recall/scripts/recall-search.sh "$VAULT" "<query>"
```

Use `<query>` as a fixed string. For multi-word queries, quote them. If you need broader matching, run multiple queries with the key terms separately and merge.

### Step 3 — read selectively

Use the Read tool on each returned path. Cap at 5 files. If a file is large, read with `limit` to stay tight.

### Step 4 — synthesize

Produce a single brief, ≤500 tokens, formatted as above. Cite source paths. Do not paste raw bodies. If a note is critical and the user will want the full body, say "Read `<path>` for full content" — don't pre-emptively dump it.

## Anti-patterns

- Dumping every matched note body inline.
- Running `rg` against the vault directly when this script exists — you lose priority ranking.
- Recalling on every turn — recall once per topic per session.
- Falling back to web search before checking the vault.

## Related skills

- `obsidian-capture` — write findings back so the next recall pays off.
- `obsidian-setup` — fix "vault not found".
