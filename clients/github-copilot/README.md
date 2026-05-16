# GitHub Copilot

Copilot — including agent mode in VS Code 1.95+ — doesn't load Claude Code skills, but the vault is plain markdown and works the same. You wire Copilot to the vault by dropping an instructions file at the path Copilot reads automatically.

## Install per repo

From any repo you want connected to the brain:

```bash
mkdir -p .github
cp /home/keertan/codes/brain/clients/github-copilot/copilot-instructions.md \
   .github/copilot-instructions.md
```

GitHub Copilot reads `.github/copilot-instructions.md` automatically for chat and agent-mode sessions in that repo.

If you have many repos and want one source of truth, symlink instead of copying:

```bash
ln -s /home/keertan/codes/brain/clients/github-copilot/copilot-instructions.md \
  .github/copilot-instructions.md
```

## Verify

Open a Copilot chat in the repo and ask:

> Read `~/Documents/ObsidianVault/_meta/AGENTS.md` and tell me the four required frontmatter keys for vault notes.

If Copilot reads the file and reports `type`, `status`, `created`, `updated` — wiring works.

## VS Code agent mode — MCP

VS Code Copilot agent mode (1.95+) supports MCP servers. This skill pack deliberately avoids MCP (the vault is plain filesystem; one fewer moving part). If you want MCP later, drop in any community `mcp-obsidian` server pointed at the same vault — it will coexist with the instructions-file approach.
