---
type: meta
tags: [agents, contract]
status: active
created: 2026-05-17
updated: 2026-05-17
---

# Vault contract for AI coding agents

If you are an AI coding agent (Claude Code, GitHub Copilot, Cursor, Aider, etc.) with filesystem access to this vault, read this file first.

## Purpose

This vault is a persistent, organized second brain. Use it to recall context before non-trivial work, and to capture decisions, gotchas, and patterns at the end of substantive work. The goal is to *save* your context and the user's time — not to add bookkeeping.

## Read budget

Before reading anything, search. Before reading everything, read targeted.

- Use ripgrep (`rg`) or grep for keyword search across the vault.
- Rank search hits by path priority: `knowledge/` > `projects/<current-repo>/` > `agent-memory/` > `daily/`.
- Read at most 3–5 notes per recall round. If you need more, narrow the query.
- When summarizing for yourself or another agent, emit ≤500 tokens with note titles cited — never dump raw bodies.

## Project bootstrap is mandatory

**When you start work on a new project, your first vault action is to create `projects/<project-name>/`.** This is non-negotiable. A project is anything that spans more than a single one-shot exchange: a new repo, a research question, an audit, a migration.

The bootstrap creates:

- `projects/<name>/index.md` — a frontmatter-validated project index. The template is picked by task type.
- `projects/<name>/tasks/` — always.
- `projects/<name>/modules/` — only for `task_type: development`.

The index `frontmatter` must include `type: project`, `project: <name>`, `task_type: <one-of>`, `status`, `created`, `updated`.

Pick `task_type` from exactly these four values:

| Work looks like | task_type |
|---|---|
| Building/shipping code in a repo | `development` |
| Investigating a question, gathering sources, no code output | `research` |
| Reading an existing repo to map/audit/onboard | `repo-analysis` |
| None of the above | `generic` |

If you don't know how to bootstrap from your environment, the conventions are documented in `templates/project-*.md` — copy the matching template, fill its `{{date}}`, `{{title}}`, `{{project}}` placeholders, and write it as `projects/<name>/index.md`. Refuse to overwrite an existing project — extend the existing index instead.

Claude Code agents: invoke `obsidian-project-bootstrap` skill. Other agents: follow the rule above directly.

## Write rules

- **Always bootstrap a project before capturing notes that belong to it** (see above). `agent-memory/` captures during project work should carry `project: <name>` in their frontmatter to attach back to the project.
- Write freely to `agent-memory/`, `projects/`, and `daily/`.
- **Do not** write to `knowledge/` directly. That section is human-curated. Notes graduate there via the `obsidian-curate` workflow.
- Every new note **must** start with the YAML frontmatter described in [[frontmatter-schema]].
- File names: kebab-case, `YYYY-MM-DD-<slug>.md` for time-ordered types.
- Add `[[wikilinks]]` to related notes. If the link target doesn't exist yet, that's fine — Obsidian shows orphan links and they signal future notes to write.

## When to write

Write at natural breakpoints, not on every turn:

- A non-obvious decision was made — `agent-memory/decisions/`.
- You hit a surprise that took >5 min to diagnose — `agent-memory/gotchas/`.
- You used a pattern you'd reach for again — eventually a candidate for `knowledge/patterns/` via curation.
- End of a substantive session — `daily/YYYY-MM-DD.md` append.

Avoid writing speculative notes ("might want to know"). Avoid summarizing what was already obvious from the diff.

## Concurrent edits

The user's Obsidian app may have the same file open. Mitigation:

- Before editing an existing note, check its mtime. If modified in the last 60 seconds, prefer append over overwrite, or wait.
- Never delete a note. Move to `agent-memory/_archive/` and leave a redirect note if necessary.

## Skills (Claude Code)

If you are Claude Code, four skills wrap these conventions:

- `obsidian-setup` — first-run vault scaffolding and config.
- `obsidian-project-bootstrap` — **mandatory** at the start of every new project.
- `obsidian-recall` — search → rank → synthesize.
- `obsidian-capture` — pick template → fill frontmatter → write.

If you are not Claude Code, follow the conventions in this file directly using your native filesystem tools.
