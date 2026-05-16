# Repository AI agent instructions

This repository participates in a shared second-brain system. The user's Obsidian vault lives at `~/Documents/ObsidianVault/` (override via `OBSIDIAN_VAULT` env var or the path persisted in `<brain-repo>/.vault-path`).

**All agent activity is namespaced to `<vault>/Agent-Brain/`** — the user's own notes (anywhere else in the vault) are off-limits. Override the subdir name with `BRAIN_SUBDIR=<name>` if needed; the default is `Agent-Brain`.

## At the start of every new project (mandatory)

Before any other agent writes, create `<vault>/Agent-Brain/projects/<project-name>/` with a populated `index.md`. Pick `<project-name>` from the repo basename (`basename "$(pwd)"`) unless told otherwise. Pick a `task_type` from:

- `development` — building/shipping code
- `research` — investigation, sources, no code output
- `repo-analysis` — reading an existing repo to map/audit/onboard
- `generic` — none of the above

Copy `<vault>/Agent-Brain/templates/project-<task_type>.md`, fill `{{date}}` `{{title}}` `{{project}}` placeholders, write to `Agent-Brain/projects/<name>/index.md`. Create `tasks/` (always) and `modules/` (development only). Never overwrite an existing project — extend the index instead.

This step is non-negotiable. Every capture during this project carries `project: <project-name>` in its frontmatter.

## Before non-trivial work

Read `<vault>/Agent-Brain/_meta/AGENTS.md` for full conventions. Search the brain for relevant context with ripgrep before reading code:

```bash
rg --type md --files-with-matches --ignore-case --fixed-strings "<topic>" ~/Documents/ObsidianVault/Agent-Brain
```

**Limit your search to `Agent-Brain/`.** Do not grep the rest of the user's vault — those are their notes, not yours.

Rank hits by section priority:
1. `Agent-Brain/knowledge/` — durable curated docs
2. `Agent-Brain/projects/<this-repo>/` — repo-specific notes
3. `Agent-Brain/agent-memory/` — prior decisions and gotchas
4. `Agent-Brain/daily/` — recent session logs

Read at most 3–5 notes. Summarize briefly; do not dump raw bodies.

## When to write

Capture inside `Agent-Brain/` at natural breakpoints:

- Non-obvious decision → `Agent-Brain/agent-memory/decisions/YYYY-MM-DD-<slug>.md`
- Surprise that took real time → `Agent-Brain/agent-memory/gotchas/YYYY-MM-DD-<slug>.md`
- Reusable pattern → propose to user before writing to `Agent-Brain/knowledge/patterns/`
- End of substantive session → append to `Agent-Brain/daily/YYYY-MM-DD.md`

Every note must have frontmatter as defined in `Agent-Brain/_meta/frontmatter-schema.md`. Required keys: `type`, `status`, `created`, `updated`. Filenames are kebab-case, time-ordered types prefixed `YYYY-MM-DD-`.

## Do not

- **Write anywhere outside `<vault>/Agent-Brain/`.** The rest of the vault is the user's own notes.
- Write to `Agent-Brain/knowledge/` without explicit user approval — that section is human-curated.
- Delete vault notes (yours or theirs).
- Capture trivial summaries or speculative "might be useful later" notes.
- Maintain a separate per-repo doc that duplicates Agent-Brain content — link to it.

## Sync

Obsidian Sync mirrors this vault across the user's devices. Treat `Agent-Brain/` as authoritative for agent state; treat everything outside it as read-only.
