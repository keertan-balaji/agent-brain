# Claude Code

Claude Code is the only platform with a real skill runtime. The five skills (`obsidian-setup`, `obsidian-project-bootstrap`, `obsidian-map-repo`, `obsidian-recall`, `obsidian-capture`) load as proper Claude Code skills with their own `/`-commands.

## Option A — one-shot installer (recommended)

From the repo root:

```bash
bash clients/install-claude-code.sh
```

What it does:
- Symlinks every `skills/<name>/` directory into `~/.claude/skills/<name>`.
- Skips entries that are already correctly linked.
- Replaces stale symlinks (warns first).
- Refuses to touch non-symlink files at the target paths.

Idempotent. Re-run any time after you pull updates to the repo.

Override the target with `CLAUDE_SKILLS_DIR=/some/other/path bash clients/install-claude-code.sh`.

## Option B — marketplace plugin

If you'd rather manage the pack like other plugins:

1. Either clone the repo somewhere stable (`~/projects/brain`, `/opt/brain`, etc.) or treat your existing `$(pwd)` as the install location.
2. Add this repo to your Claude Code marketplace. In `~/.claude/settings.json` under `extraKnownMarketplaces`, add a `directory` source:
   ```json
   "extraKnownMarketplaces": {
     "obsidian-second-brain": {
       "source": { "source": "directory", "path": "/home/keertan/codes/brain" }
     }
   }
   ```
3. Then `/plugin install obsidian-second-brain@obsidian-second-brain`.

(`plugin.json` at the repo root declares the five skills.)

## After install

1. Open Claude Code in any project.
2. Run `/obsidian-setup`. It asks where your Obsidian vault is and persists the choice.
3. Add the vault path to `~/.claude/settings.json` so native file tools (Read/Edit/Write/Grep) can reach it:
   ```json
   "permissions": {
     "additionalDirectories": ["/home/keertan/Documents/ObsidianVault"]
   }
   ```
   (Auto-mode correctly blocks the agent from doing this for you — apply it manually.)
4. Run `/obsidian-map-repo` to onboard the current repo as a project.
5. From here on, use `/obsidian-recall <topic>` before non-trivial work and `/obsidian-capture <type>` after decisions/gotchas.

## Uninstall

```bash
for name in obsidian-setup obsidian-project-bootstrap obsidian-map-repo \
            obsidian-recall obsidian-capture; do
  rm -f "$HOME/.claude/skills/$name"
done
```

The vault itself is untouched. To remove the vault, delete `~/Documents/ObsidianVault/` manually.
