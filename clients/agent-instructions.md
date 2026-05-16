# Repository AI agent instructions

This repository participates in a shared second-brain system at `~/Documents/ObsidianVault/` (override via `OBSIDIAN_VAULT` env var or the path persisted in `<brain-repo>/.vault-path`).

## At the start of every new project (mandatory)

Before any other vault writes, create `<vault>/projects/<project-name>/` with a populated `index.md`. Pick `<project-name>` from the repo basename (`basename "$(pwd)"`) unless told otherwise. Pick a `task_type` from:

- `development` — building/shipping code
- `research` — investigation, sources, no code output
- `repo-analysis` — reading an existing repo to map/audit/onboard
- `generic` — none of the above

Copy `<vault>/templates/project-<task_type>.md`, fill `{{date}}` `{{title}}` `{{project}}` placeholders, write to `projects/<name>/index.md`. Create `tasks/` (always) and `modules/` (development only). Never overwrite an existing project — extend the index instead.

This step is non-negotiable. Every capture during this project carries `project: <project-name>` in its frontmatter.

## Before non-trivial work

Read `<vault>/_meta/AGENTS.md` for full vault conventions. Search the vault for relevant context with ripgrep before reading code:

```bash
rg --type md --files-with-matches --ignore-case --fixed-strings "<topic>" ~/Documents/ObsidianVault
```

Rank hits by section priority:
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
- End of substantive session → append to `daily/YYYY-MM-DD.md`

Every note must have frontmatter as defined in `<vault>/_meta/frontmatter-schema.md`. Required keys: `type`, `status`, `created`, `updated`. Filenames are kebab-case, time-ordered types prefixed `YYYY-MM-DD-`.

## Do not

- Write to `<vault>/knowledge/` without explicit user approval — that section is human-curated.
- Delete vault notes.
- Capture trivial summaries or speculative "might be useful later" notes.
- Maintain a separate per-repo doc that duplicates vault content — link to it.

## Sync

Obsidian Sync mirrors this vault across the user's devices. Treat the vault as authoritative.
