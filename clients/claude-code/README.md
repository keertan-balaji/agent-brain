# Claude Code

The repo ships a Claude Code plugin manifest at `.claude-plugin/plugin.json` and a single-plugin marketplace at `.claude-plugin/marketplace.json`. Skills under `skills/` are auto-discovered. Three install paths, in order of preference.

## Option A — marketplace (recommended)

Register this repo as a marketplace, then install the plugin. From inside Claude Code:

```text
/plugin marketplace add keertan/obsidian-second-brain
/plugin install obsidian-second-brain@obsidian-second-brain
```

If you've cloned the repo locally and don't want to round-trip through GitHub:

```text
/plugin marketplace add /home/keertan/codes/brain
/plugin install obsidian-second-brain@obsidian-second-brain
```

The local-directory form reads `.claude-plugin/marketplace.json` directly. Updates propagate as you pull the repo.

## Option B — manual marketplace registration via settings.json

Add an entry to `~/.claude/settings.json`:

```json
"extraKnownMarketplaces": {
  "obsidian-second-brain": {
    "source": { "source": "directory", "path": "/home/keertan/codes/brain" }
  }
}
```

Then in Claude Code: `/plugin install obsidian-second-brain@obsidian-second-brain`.

## Option C — symlink installer (no plugin runtime)

If you want skills loaded but don't want them managed as a plugin:

```bash
bash clients/install-claude-code.sh
```

What it does:
- Symlinks every `skills/<name>/` into `~/.claude/skills/<name>`.
- Skips entries already correctly linked.
- Replaces stale symlinks (warns first).
- Refuses to touch non-symlink files at target paths.

Idempotent. Override target with `CLAUDE_SKILLS_DIR=/path bash clients/install-claude-code.sh`.

## After install

1. Open Claude Code in any project.
2. Run `/obsidian-setup`. It asks where your vault is (Obsidian Sync path, custom location, or default `~/Documents/ObsidianVault`) and persists the choice.
3. Add the vault path to `~/.claude/settings.json` so native file tools reach it:
   ```json
   "permissions": {
     "additionalDirectories": ["/home/keertan/Documents/ObsidianVault"]
   }
   ```
   (Auto-mode correctly blocks the agent from doing this for you — apply it manually.)
4. Run `/obsidian-map-repo` to onboard the current repo as a project.
5. Use `/obsidian-recall <topic>` before non-trivial work and `/obsidian-capture <type>` after decisions/gotchas.

## Uninstall

Marketplace install: `/plugin uninstall obsidian-second-brain@obsidian-second-brain`.

Symlink install:

```bash
for name in obsidian-setup obsidian-project-bootstrap obsidian-map-repo \
            obsidian-recall obsidian-capture; do
  rm -f "$HOME/.claude/skills/$name"
done
```

The vault itself is untouched.
