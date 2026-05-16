# Using this skill pack with GitHub Copilot

Copilot (especially VS Code agent mode) doesn't load Claude Code skills, but the Obsidian vault is plain markdown and works the same. The contract is `~/Documents/ObsidianVault/_meta/AGENTS.md`.

## Install per repo

```bash
mkdir -p .github
cp /path/to/brain/copilot/instructions.md .github/copilot-instructions.md
```

GitHub Copilot reads `.github/copilot-instructions.md` automatically and applies it to chat and agent mode sessions in that repo.

## Verify

In a Copilot chat, ask:

> Read `~/Documents/ObsidianVault/_meta/AGENTS.md` and tell me the three sections of the vault.

If Copilot reads it and reports `knowledge/`, `agent-memory/`, `projects/` — wiring is good.

## Cursor / Aider / Cline

Same approach. Drop `instructions.md` content into whatever per-repo agent-config file the editor honors (`.cursorrules`, `AGENTS.md`, etc.). The vault conventions in `_meta/AGENTS.md` are the same regardless of agent.
