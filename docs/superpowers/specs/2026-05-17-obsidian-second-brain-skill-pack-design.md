# Obsidian Second Brain — Skill Pack Design

**Date:** 2026-05-17
**Status:** Draft, awaiting user review
**Author:** keertan + Claude

## Goal

Build a Claude Code skill pack (also usable by other agents with filesystem access) that turns an Obsidian vault into a persistent, organized second brain for coding agents. Reduces time-and-context that agents spend rediscovering enterprise knowledge — architecture docs, API specs, process rules, prior decisions, recurring gotchas — by giving them a structured, searchable, write-back-capable knowledge store that survives across sessions and devices.

## Problem

In enterprise codebases agents start cold every session:
- Architecture/process/API docs are scattered, large, or remote.
- Agents burn turns and context grepping repos and re-reading the same files.
- Hard-won learnings (gotchas, decisions, "don't touch X because Y") vanish at session end.
- No shared substrate across agents (Claude Code, GitHub Copilot, others) — each rediscovers everything independently.

## Non-goals (v1)

- No semantic / embedding search. Grep + structure first; embeddings later only if proven necessary.
- No MCP server. Filesystem-direct access only.
- No multi-user concurrency model. Single-user vault, Obsidian Sync handles cross-device.
- No automated curation. `agent-memory/` → `knowledge/` promotion is human-gated.
- No replacement for code search tools. Vault holds *about* the code, not the code.

## Architecture

Three layers:

```
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Skills (this repo)                              │
│   obsidian-setup, recall, capture, curate, graph-walk,   │
│   project-bootstrap, daily-log                           │
│   → tell agent WHEN to act and HOW to format             │
└──────────────────────┬───────────────────────────────────┘
                       │ uses
                       ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Native agent tools (no custom infra)            │
│   Read, Write, Edit, Grep, Bash(rg/find/ls)              │
└──────────────────────┬───────────────────────────────────┘
                       │ operates on
                       ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Vault — plain markdown directory                │
│   ~/Documents/ObsidianVault/                             │
│   knowledge/  agent-memory/  projects/  _meta/  templates/ │
│   ← Obsidian Sync mirrors across devices                 │
│   ← Obsidian app reads/edits same files                  │
└─────────────────────────────────────────────────────────┘
```

Vault is the source of truth. Skills are workflows. Native tools are the transport. Obsidian Sync is the cross-device layer (out of scope for this pack — user already has it).

## Vault structure

```
~/Documents/ObsidianVault/
├── knowledge/                  # curated, durable. Agents read; rarely write directly.
│   ├── architecture/           # system diagrams, component boundaries, data flow
│   ├── api/                    # external + internal API references
│   ├── process/                # team rules, release flow, compliance checks
│   ├── glossary/               # domain terms, project-specific vocabulary
│   └── patterns/               # validated solutions, idioms, templates
├── agent-memory/               # agent scratch + working memory. Agents write freely.
│   ├── decisions/              # YYYY-MM-DD-<slug>.md — non-obvious choices + reasons
│   ├── sessions/               # daily session logs
│   ├── gotchas/                # surprises, footguns, "looked simple but…"
│   └── prompts/                # reusable prompt fragments + interaction patterns
├── projects/                   # per-repo workspace
│   └── <repo-name>/
│       ├── index.md            # entry point: links to relevant knowledge/ + memory
│       ├── modules/            # per-module notes
│       └── tasks/              # current/recent task notes
├── daily/                      # YYYY-MM-DD.md — chronological session journal
├── _meta/                      # vault conventions
│   ├── MOC.md                  # Map of Content — top-level index
│   ├── AGENTS.md               # how agents should use this vault
│   ├── frontmatter-schema.md   # required fields per note type
│   └── linking-conventions.md  # wikilink style, tag taxonomy
└── templates/                  # frontmatter-prefilled stubs
    ├── decision.md
    ├── session.md
    ├── gotcha.md
    ├── api-note.md
    └── architecture.md
```

### Frontmatter schema (required on every note)

```yaml
---
type: decision | session | gotcha | api | architecture | process | glossary | pattern | project | task
tags: [list, of, tags]
project: <repo-name or null>
status: draft | active | archived | promoted
created: YYYY-MM-DD
updated: YYYY-MM-DD
related: ["[[other-note]]", "[[another-note]]"]
---
```

Skills enforce this on write. Notes without it surface in `obsidian-curate` for cleanup.

### Linking conventions

- Use `[[wikilinks]]` for cross-note references — Obsidian and grep both handle these.
- Use `#tag` for cross-cutting categories (`#performance`, `#auth`, `#legacy`).
- Note filenames: kebab-case, prefixed with date for time-ordered types (`decisions/`, `sessions/`, `gotchas/`).
- Aliases via frontmatter `aliases: [...]` when a concept has multiple names.

## Skills

Each skill is `skills/<name>/SKILL.md` with superpowers-compatible frontmatter:

```yaml
---
name: obsidian-<verb>
description: When ...; use to ...
---
```

### Phase 1 (MVP) — minimum end-to-end loop

| Skill | Trigger | Behavior |
|---|---|---|
| **obsidian-setup** | First run, user says "set up brain", config drift detected | Ensure vault dir exists; copy `vault-template/*` if empty; append vault path to `~/.claude/settings.json` `additionalDirectories`; write `_meta/AGENTS.md`; verify with a round-trip read/write test. Idempotent. |
| **obsidian-recall** | Start of non-trivial task; user mentions a feature/module/concept; before brainstorming or implementation | `rg <topic>` across vault. Rank: `knowledge/` > `projects/<current-repo>/` > `agent-memory/` > `daily/`. Read top 3–5. Return ≤500-token synthesis citing source notes. **Never dump raw file contents.** |
| **obsidian-capture** | Decision made; gotcha hit; pattern emerged; end of substantive task | Choose template by event type. Fill frontmatter. Write to `agent-memory/<type>/YYYY-MM-DD-<slug>.md`. Add `[[wikilinks]]` to related notes (found via grep). Append entry to today's `daily/YYYY-MM-DD.md`. |

### Phase 2 — durability + navigation

| Skill | Trigger | Behavior |
|---|---|---|
| **obsidian-daily-log** | Session start, session end | Create or append `daily/YYYY-MM-DD.md`. Sections: tasks worked, files touched, decisions captured (links), notes written (links), open threads. |
| **obsidian-graph-walk** | Need expanded context on a concept; ambiguous reference; user says "what do we know about X" | Start at named note → grep its `[[refs]]` → recurse up to 2 hops. Return graph slice (note titles + first lines), not full bodies. Lets agent decide which to Read. |
| **obsidian-curate** | Periodic; user says "promote" or "curate"; or `agent-memory/` note has ≥3 inbound links | Surface promotion candidates: `agent-memory/` notes with high link-in count or `status: active` >30 days. Present list to user. On approval: move to appropriate `knowledge/` subdir, rewrite frontmatter (`status: promoted`), update inbound links. Always human-gated. |

### Phase 3 — multi-project + cross-agent polish

| Skill | Trigger | Behavior |
|---|---|---|
| **obsidian-project-bootstrap** | First Claude Code session in a new repo; user says "bootstrap this repo's brain" | Create `projects/<repo-name>/index.md`. Detect repo language/framework. Grep vault for tags matching detected stack. Pre-populate index with `[[links]]` to relevant `knowledge/` entries. Create `tasks/`, `modules/` subdirs. |
| (no new skill — config) | Copilot enablement | Drop `.github/copilot-instructions.md` template at repo level pointing at vault path + AGENTS.md. Skill pack ships this template under `copilot/instructions.md`. |

## Write discipline

- Skills write to `agent-memory/`, `projects/`, `daily/` freely.
- Skills write to `knowledge/` **only via `obsidian-curate`** with explicit user approval.
- Skills never delete. Curate may move + rewrite, never destroy.
- Concurrent edit risk (Obsidian app + agent on same file): mitigated by file-level operations being atomic on Linux. Agent's Edit is read→modify→write; if Obsidian saves between, Obsidian's version may overwrite. Mitigation: skills do not edit notes that have been touched in the last 60 seconds (check mtime); if conflict, append-only.

## Context budget

The whole point of this system is to *save* agent context, so skills must obey budgets:

- `obsidian-recall`: returns ≤500 tokens synthesized brief; never dumps raw file content.
- `obsidian-graph-walk`: returns titles + first-line previews only; agent decides what to Read.
- `obsidian-capture`: emits short confirmation (path written), not the note body back.
- `obsidian-curate`: paginated candidate list, 10 per page.

Agents that ignore budgets and Read everything defeat the system. Skills make the budgeted path the path of least resistance by returning summaries by default.

## Repo layout

```
brain/
├── README.md                              # install, philosophy, quick start
├── plugin.json                            # Claude Code marketplace manifest
├── skills/
│   ├── obsidian-setup/SKILL.md
│   ├── obsidian-recall/SKILL.md
│   ├── obsidian-capture/SKILL.md
│   ├── obsidian-daily-log/SKILL.md        # phase 2
│   ├── obsidian-graph-walk/SKILL.md       # phase 2
│   ├── obsidian-curate/SKILL.md           # phase 2
│   └── obsidian-project-bootstrap/SKILL.md # phase 3
├── vault-template/                        # scaffold copied by obsidian-setup
│   ├── knowledge/{architecture,api,process,glossary,patterns}/.gitkeep
│   ├── agent-memory/{decisions,sessions,gotchas,prompts}/.gitkeep
│   ├── projects/.gitkeep
│   ├── daily/.gitkeep
│   ├── _meta/
│   │   ├── MOC.md
│   │   ├── AGENTS.md
│   │   ├── frontmatter-schema.md
│   │   └── linking-conventions.md
│   └── templates/
│       ├── decision.md
│       ├── session.md
│       ├── gotcha.md
│       ├── api-note.md
│       └── architecture.md
├── copilot/
│   ├── instructions.md                    # .github/copilot-instructions.md template
│   └── README.md                          # how to wire Copilot to read the vault
└── docs/superpowers/specs/
    └── 2026-05-17-obsidian-second-brain-skill-pack-design.md
```

## Setup flow (first run)

1. User installs skill pack (clone repo, add to Claude Code marketplace OR symlink `skills/*` into `~/.claude/skills/`).
2. User runs `/obsidian-setup` (or agent triggers it on detecting absence of vault).
3. Skill checks: does `~/Documents/ObsidianVault/` exist? If empty → copy `vault-template/*`. If non-empty → verify required dirs exist, create missing.
4. Skill ensures vault path is in `~/.claude/settings.json` `additionalDirectories`.
5. Skill writes `~/Documents/ObsidianVault/_meta/AGENTS.md` — the vault's own readme telling any agent how it's organized.
6. Skill drops `.github/copilot-instructions.md` template in current repo if applicable.
7. Round-trip test: write a sentinel note, read it back, delete it. Confirm permissions.
8. Surface vault path + next-step suggestions (run `obsidian-project-bootstrap` for current repo).

## Cross-agent strategy

| Agent | How it consumes the vault |
|---|---|
| Claude Code | Skill pack — full workflows via Skill tool |
| GitHub Copilot (VS Code agent mode) | `.github/copilot-instructions.md` points at vault + `_meta/AGENTS.md`. Copilot reads files via its own file tools. No skill runtime, but markdown SKILL.md files double as documentation Copilot can read and follow. |
| Other (Cursor, Aider, Cline, etc.) | Same as Copilot — vault is plain markdown, `_meta/AGENTS.md` is the contract. |

`_meta/AGENTS.md` is the **interoperability layer** — every agent reads it on bootstrap, learns conventions, behaves consistently regardless of skill-runtime support.

## Risks and open items

- **Vault permissions**: agent must have read+write on vault path. Setup skill handles via `additionalDirectories`; fallback is symlink into project. Documented.
- **Obsidian Sync conflicts**: if two devices edit same note offline, Sync produces conflict files. Out of scope for skills — user resolves in Obsidian.
- **Frontmatter drift**: agents may forget required fields. Mitigation: templates pre-fill frontmatter; `obsidian-curate` lints.
- **Vault sprawl**: `agent-memory/` grows unbounded. Mitigation: `obsidian-curate` archives notes with `status: active` + no link activity in 90 days to `agent-memory/_archive/`.
- **Bootstrap chicken-and-egg**: `obsidian-recall` needs content; new vault has none. Mitigation: setup ships seed notes in `_meta/` so first recall has something to return; encourages user/agent to capture early.
- **Slop**: agents writing noise into `agent-memory/`. Mitigation: capture skill requires explicit trigger (decision made, gotcha hit) — not "after every turn." Curate skill prunes.

## Success criteria

1. Fresh-install user runs `/obsidian-setup` once. Vault scaffolds. No manual file editing.
2. In a new task, `/obsidian-recall <topic>` returns relevant prior notes in ≤500 tokens within 5 seconds.
3. After a non-trivial decision, `/obsidian-capture` writes a properly-frontmattered note linked to related concepts in <2 seconds.
4. The same vault is usable from Claude Code on laptop and (via Obsidian Sync) browsed/edited from phone Obsidian app.
5. A second agent (Copilot in VS Code) follows `_meta/AGENTS.md` and writes notes that pass the same frontmatter schema.

## Phasing summary

- **Phase 1 (MVP, 1 implementation plan)**: vault template + `obsidian-setup` + `obsidian-recall` + `obsidian-capture`. Validates end-to-end loop on the user's own daily coding.
- **Phase 2**: `obsidian-daily-log` + `obsidian-graph-walk` + `obsidian-curate`. Adds durability and navigation.
- **Phase 3**: `obsidian-project-bootstrap` + Copilot polish + measurement.

Each phase ships as its own implementation plan after this spec is approved.
