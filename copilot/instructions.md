# Repository AI agent instructions

This repository participates in a shared second-brain system at `~/Documents/ObsidianVault/`.

## At the start of every new project (mandatory)

Before any other vault writes, create `~/Documents/ObsidianVault/projects/<project-name>/` with a populated `index.md`. Pick `<project-name>` from the repo basename (`basename "$(pwd)"`) unless told otherwise. Pick a `task_type`: `research`, `development`, `repo-analysis`, or `generic`. Copy the matching template from `~/Documents/ObsidianVault/templates/project-<task_type>.md`, fill `{{date}}`, `{{title}}`, `{{project}}` placeholders, write to `projects/<name>/index.md`. Create `tasks/` (always) and `modules/` (development only). Never overwrite an existing project — extend the index.

This step is non-negotiable. Every capture during this project carries `project: <project-name>` in its frontmatter.

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
