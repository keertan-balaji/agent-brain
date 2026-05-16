---
name: obsidian-setup
description: Use FIRST when wiring up this skill pack — whether the user has an existing Obsidian vault (Obsidian Sync, custom location) or wants a fresh one at the default path. Asks the user where the vault is, validates the path, fills any missing structural pieces without overwriting user content, and persists the choice so every other obsidian-* skill resolves to the same vault. Idempotent — safe to re-run.
---

# obsidian-setup

Connect this skill pack to a vault and remember which one.

## When to use

- First run after install.
- User says: "set up obsidian", "connect to my vault", "/obsidian-setup", "use my Obsidian Sync vault".
- User mentions Obsidian Sync, iCloud-/Dropbox-/Syncthing-backed vaults, or any non-default vault location.
- Another `obsidian-*` skill failed because the vault wasn't found or pointed at the wrong place.
- User changed vault location and wants to re-point.

## What it does

1. **Resolve current state.** Read whichever path is already in effect (env > persisted choice > default).
2. **Ask the user** to confirm or change the vault path.
3. **Validate** the chosen path: exists, is a directory, readable+writable.
4. **Classify**: existing Obsidian vault (has `.obsidian/`), empty directory (will be scaffolded), or non-empty plain directory (warn but proceed).
5. **Fill structural gaps** via `scaffold-vault.sh`. Only adds missing `_meta/`, `templates/`, section dirs — never overwrites user content.
6. **Persist** the absolute path to `<brain-repo>/.vault-path` (or `$BRAIN_VAULT_CONFIG` if set). All other skills read this via `resolve-vault.sh`.
7. **Surface permissions reminder.** If the path isn't already in Claude Code's `additionalDirectories`, tell the user; don't edit `~/.claude/settings.json` autonomously.

## How

### Step 1 — show the current state

```bash
BRAIN=/home/keertan/codes/brain
current=$(bash "$BRAIN/skills/obsidian-setup/scripts/resolve-vault.sh")
```

This prints whichever path would be used right now: `$OBSIDIAN_VAULT` env > persisted `.vault-path` > default `$HOME/Documents/ObsidianVault`.

### Step 2 — ask the user

Invoke `AskUserQuestion`:

- **Question**: `Where is your Obsidian vault?`
- **Header**: `Vault path`
- **Options**:
  1. label: `Use current: <current>` — description: `Keep the path already in effect.`
  2. label: `Other` — description: `Type a different path. Use this if you have an Obsidian Sync vault or a custom location.`

If the user picks "Other", they type the path. Treat `~` and shell variables literally — if they paste `~/notes`, expand it before passing it on (`path="${typed/#\~/$HOME}"`).

### Step 3 — connect

```bash
chosen=$(bash "$BRAIN/skills/obsidian-setup/scripts/connect-vault.sh" "<path>")
```

The script:
- validates the path,
- runs the scaffold to fill gaps (existing files preserved),
- writes the absolute path to `.vault-path`,
- echoes the resolved absolute path.

If it errors, surface the message and re-ask.

### Step 4 — verify

```bash
bash "$BRAIN/skills/obsidian-capture/scripts/validate-frontmatter.sh" "$chosen/_meta/AGENTS.md"
```

Exit 0 = the vault is wired up.

### Step 5 — permissions reminder (do not edit settings yourself)

Check whether `$chosen` is listed in `~/.claude/settings.json` under `permissions.additionalDirectories`. If not, tell the user:

> Vault connected: `<path>`. To let Claude Code's native Read/Edit/Write/Grep tools reach the vault, add it to `~/.claude/settings.json`:
>
> ```json
> "permissions": { "additionalDirectories": ["<path>"] }
> ```
>
> The skills work via Bash without this, but the native file tools will be blocked from the vault until you add it.

Don't edit the settings file yourself — auto-mode rightly blocks agents from granting themselves filesystem access.

### Step 6 — confirm

Report: `Vault connected: <path>` plus the next-step suggestion (`/obsidian-project-bootstrap` if a project is in flight, `/obsidian-recall <topic>` to test reading).

## Resolution contract for other skills

Every other `obsidian-*` skill (and their helper scripts) resolves the vault by calling:

```bash
VAULT=$(bash "$BRAIN/skills/obsidian-setup/scripts/resolve-vault.sh")
```

Order: `$OBSIDIAN_VAULT` env → `.vault-path` file → `$HOME/Documents/ObsidianVault` fallback. Once `obsidian-setup` runs, every subsequent skill follows.

## Don't

- Don't ask the user for the path more than once per session.
- Don't run this skill unprompted when a vault is already connected and working.
- Don't trust the path without validating — the helper does this; respect its errors.
- Don't move or copy user content from one vault into another. Vault consolidation is a manual operation.
- Don't edit `~/.claude/settings.json` yourself. Surface the snippet, let the user apply it.
- Don't write into `knowledge/` — that section is human-curated.

## Related skills

- `obsidian-project-bootstrap` — mandatory after setup, on every new project.
- `obsidian-recall` / `obsidian-capture` — both honor the connected vault automatically via the resolver.
