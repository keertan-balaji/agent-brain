# Other agents

For any AI coding agent not covered by the platform-specific subdirs (Cline, Continue.dev, Zed AI, Windsurf, custom CLI agents, etc.), the install pattern is the same: point the agent at the universal instructions file and the vault contract.

## Step 1 — figure out the right path

Find whichever per-repo or per-user config file your agent honors. Common ones:

| Agent | Path |
|---|---|
| Cline (VS Code) | `.clinerules` at repo root |
| Continue.dev | `~/.continue/config.json` under `customCommands` / `contextProviders` |
| Zed AI | Project-level prompt config |
| Windsurf | `.windsurfrules` |
| Generic CLI agent | Whatever file the agent reads on startup (often `AGENTS.md`) |

When in doubt, check the agent's docs for "system prompt", "custom instructions", "rules file", or "context file."

## Step 2 — drop the instructions

Copy or symlink `clients/agent-instructions.md` to the path above:

```bash
cp /home/keertan/codes/brain/clients/agent-instructions.md <agent-path>
```

Or, if you want one source of truth:

```bash
ln -s /home/keertan/codes/brain/clients/agent-instructions.md <agent-path>
```

## Step 3 — make the vault reachable

The agent needs filesystem access to `~/Documents/ObsidianVault/`. Most editor-integrated agents only see the workspace; either add the vault as a workspace folder, or run the agent from a parent directory that includes both your code and the vault.

For shell-based agents, no special wiring is needed — the filesystem is already accessible.

## Step 4 — verify

Ask the agent:

> Read `~/Documents/ObsidianVault/_meta/AGENTS.md` and tell me what to do at the start of a new project.

If it reports "create projects/&lt;name&gt;/ with a task-typed index.md," wiring is good.
