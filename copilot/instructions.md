# Repository AI agent instructions

This repository participates in a shared second-brain system at `~/Documents/ObsidianVault/`.

## Before non-trivial work

Read `~/Documents/ObsidianVault/_meta/AGENTS.md` for vault conventions. Search the vault for relevant context with ripgrep before reading code:

```bash
rg --type md --files-with-matches --ignore-case --fixed-strings "<topic>" ~/Documents/ObsidianVault
```

Prioritize hits from:
1. `knowledge/` — durable curated docs
2. `projects/<this-repo>/` — repo-specific notes
3. `agent-memory/` — prior decisions and gotchas
4. `daily/` — recent session logs

Read at most 3–5 notes. Summarize briefly; do not dump raw bodies.

## When to write

Capture to the vault at natural breakpoints:

- Non-obvious decision → `agent-memory/decisions/YYYY-MM-DD-<slug>.md`
- Surprise that took real time → `agent-memory/gotchas/YYYY-MM-DD-<slug>.md`
- Reusable pattern → propose to user before writing to `knowledge/patterns/`

Every note must have frontmatter as defined in `~/Documents/ObsidianVault/_meta/frontmatter-schema.md`.

## Do not

- Write to `~/Documents/ObsidianVault/knowledge/` without explicit user approval.
- Delete vault notes.
- Capture trivial summaries or speculative "might be useful later" notes.

## Sync

Obsidian Sync mirrors this vault across the user's devices. Treat the vault as authoritative; do not maintain a separate per-repo doc that duplicates it.
