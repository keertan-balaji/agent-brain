# Obsidian Second Brain

A Claude Code skill pack that turns an Obsidian vault into a persistent, organized second brain for coding agents. Filesystem-direct (no MCP server), agent-agnostic (Claude Code, GitHub Copilot, Cursor, etc.).

## What it does

Coding agents waste time and context every session rediscovering enterprise knowledge — architecture, APIs, process docs, prior decisions, recurring gotchas. This pack gives agents:

- A **structured vault** scaffolded at `~/Documents/ObsidianVault/` with sections for durable knowledge, agent working memory, per-project notes, and daily logs.
- **Skills** that tell agents *when* to recall context (before non-trivial work) and *how* to capture learnings (decisions, gotchas, patterns).
- **Cross-agent interop** via `_meta/AGENTS.md` — any agent with filesystem access can use the same vault.
- **Cross-device sync** by riding Obsidian Sync (you bring your own).

## Install

1. Clone this repo (any path is fine).
2. Symlink skills into Claude Code:
   ```bash
   ln -s "$(pwd)/skills/obsidian-setup" ~/.claude/skills/obsidian-setup
   ln -s "$(pwd)/skills/obsidian-recall" ~/.claude/skills/obsidian-recall
   ln -s "$(pwd)/skills/obsidian-capture" ~/.claude/skills/obsidian-capture
   ```
   Or add this repo to your Claude Code marketplace.
3. In Claude Code, run: `/obsidian-setup`
4. Done. Try `/obsidian-recall <topic>` and `/obsidian-capture <decision|gotcha|pattern>`.

## Skills

| Skill | When to use |
|---|---|
| `obsidian-setup` | First run; reconfigure vault path; verify install |
| `obsidian-recall` | Before non-trivial work; when topic mentioned; before brainstorming |
| `obsidian-capture` | After non-trivial decision; gotcha hit; pattern emerged |

## For other agents

Point GitHub Copilot, Cursor, Aider, etc. at `~/Documents/ObsidianVault/_meta/AGENTS.md`. That file is the cross-agent contract describing vault conventions. A copy of `copilot/instructions.md` can be dropped into any repo as `.github/copilot-instructions.md`.

## Design docs

- Spec: `docs/superpowers/specs/2026-05-17-obsidian-second-brain-skill-pack-design.md`
- Plan: `docs/superpowers/plans/2026-05-17-obsidian-second-brain-phase-1.md`

## Tests

```bash
bash tests/run-all.sh
```
