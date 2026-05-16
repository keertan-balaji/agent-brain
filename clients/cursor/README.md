# Cursor

Cursor reads project-level rule files. Drop a rule pointing at the vault and Cursor will honor the same conventions as Claude Code does via the skills.

## Install per repo (modern: Project Rules)

From any repo you want connected:

```bash
mkdir -p .cursor/rules
cp /home/keertan/codes/brain/clients/agent-instructions.md \
   .cursor/rules/obsidian-brain.mdc
```

Cursor's Project Rules system loads every `.mdc` file under `.cursor/rules/` automatically.

## Install per repo (legacy: .cursorrules)

If your Cursor version doesn't yet support Project Rules:

```bash
cp /home/keertan/codes/brain/clients/agent-instructions.md ./.cursorrules
```

## Make the vault visible to Cursor

Cursor's file index only sees files inside the open workspace. Two options:

1. **Add vault as a workspace folder.** In Cursor: `File → Add Folder to Workspace → ~/Documents/ObsidianVault/`. Cursor will then index the vault and let you @-mention notes directly.
2. **Use bash through Cursor's agent.** The agent can run `rg --type md ... ~/Documents/ObsidianVault` directly even without indexing — slower for autocomplete but works fine for chat.

Option 1 is the better experience for "recall before coding."

## Verify

In a Cursor chat:

> @file ~/Documents/ObsidianVault/_meta/AGENTS.md — summarize the four required frontmatter keys.

If Cursor reads it, wiring works.
