# Obsidian Second Brain

A Claude Code skill pack that turns an Obsidian vault into a persistent, organized second brain for coding agents. Filesystem-direct (no MCP server), agent-agnostic (Claude Code, GitHub Copilot, Cursor, Aider, Codex, and anything else that reads markdown).

## What it does

Coding agents waste time and context every session rediscovering enterprise knowledge — architecture, APIs, process docs, prior decisions, recurring gotchas. This pack gives agents:

- A **structured vault** at `~/Documents/ObsidianVault/` with sections for durable knowledge, agent working memory, per-project notes, and daily logs.
- **Skills** that tell agents *when* to recall context (before non-trivial work) and *how* to capture learnings (decisions, gotchas, patterns).
- **A mandatory project-bootstrap rule** — every new project starts with `projects/<name>/` and a task-typed index. Non-negotiable. Cross-agent.
- **Cross-agent interop** via `_meta/AGENTS.md` — any agent with filesystem access uses the same vault.
- **Cross-device sync** by riding Obsidian Sync (you bring your own).

## Install

The skill runtime is Claude Code. Every other agent gets the same behavior via a one-file instructions drop. See `clients/README.md` for the full matrix; quick paths below.

### Claude Code (skills run natively)

```bash
git clone <this-repo> ~/codes/brain   # or anywhere stable
cd ~/codes/brain
bash clients/install-claude-code.sh   # symlinks all 5 skills into ~/.claude/skills/
```

Then in Claude Code: `/obsidian-setup` (asks for vault path), then `/obsidian-map-repo` to onboard the current repo.

Also add the vault path to `~/.claude/settings.json` so native file tools reach it:

```json
"permissions": { "additionalDirectories": ["/home/keertan/Documents/ObsidianVault"] }
```

(Auto-mode correctly blocks the agent from doing this for you — apply it manually.)

### Other agents (one file, different paths)

| Agent | Drop this file at | One-liner |
|---|---|---|
| GitHub Copilot | `.github/copilot-instructions.md` | `cp ~/codes/brain/clients/agent-instructions.md .github/copilot-instructions.md` |
| Cursor (modern) | `.cursor/rules/obsidian-brain.mdc` | `cp ~/codes/brain/clients/agent-instructions.md .cursor/rules/obsidian-brain.mdc` |
| Cursor (legacy) | `.cursorrules` | `cp ~/codes/brain/clients/agent-instructions.md .cursorrules` |
| Aider | `CONVENTIONS.md` + `--read` | `cp ~/codes/brain/clients/agent-instructions.md CONVENTIONS.md` |
| Codex / AGENTS.md spec | `AGENTS.md` | `cp ~/codes/brain/clients/agent-instructions.md AGENTS.md` |
| Cline / Continue / Zed / Windsurf | varies | see `clients/generic/README.md` |

Per-platform install notes and verification steps live in `clients/<platform>/README.md`. Symlink instead of copy if you want one source of truth across many repos.

## Skills

| Skill | When to use |
|---|---|
| `obsidian-setup` | First run; asks where your vault is (Obsidian Sync path or default), scaffolds gaps, persists choice |
| `obsidian-project-bootstrap` | **Mandatory** — first action on any new project |
| `obsidian-map-repo` | Onboard a coding repo: scan stack/tree/README/git into `projects/<repo>/repo-map.md` |
| `obsidian-recall` | Before non-trivial work; when topic mentioned; before brainstorming |
| `obsidian-capture` | After non-trivial decision; gotcha hit; pattern emerged |

## Why this design

- **No MCP server.** The vault is plain markdown; agents use their native file tools. One fewer moving part, fewer failure modes, and the same vault works for every agent on day one.
- **Vault conventions are runtime-loaded.** Agents read `<vault>/_meta/AGENTS.md` at session start. Update conventions there once and every agent picks them up — no re-install across N repos.
- **Bootstrap is mandatory.** Every new project gets a folder + task-typed index before any other vault writes. Encoded in both the Claude Code skill and the cross-agent contract.
- **Write isolation.** Agents write freely to `agent-memory/` and `projects/`. `knowledge/` is human-curated, never agent-clobbered.

## Design docs

- Spec: `docs/superpowers/specs/2026-05-17-obsidian-second-brain-skill-pack-design.md`
- Plan: `docs/superpowers/plans/2026-05-17-obsidian-second-brain-phase-1.md`

## Tests

```bash
bash tests/run-all.sh
```

9 test files covering scaffold, frontmatter validation, recall priority ranking, capture, project bootstrap, repo mapping, vault connect/resolve, end-to-end loop, and the Claude Code installer.
