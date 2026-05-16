---
name: obsidian-setup
description: Use when the user wants to install or repair the Obsidian second-brain vault, when no vault exists at the configured path, or when other obsidian-* skills fail with "vault not found". Idempotent — safe to run repeatedly.
---

# obsidian-setup

Set up or repair the Obsidian vault used by the second-brain skill pack.

## When to use

- User runs `/obsidian-setup`, says "set up brain", or first-runs the pack.
- Another `obsidian-*` skill fails because the vault directory doesn't exist or is incomplete.
- The user changed vault location and wants to re-bootstrap.

## What it does

1. Determine vault path. Default: `$HOME/Documents/ObsidianVault/`. Honors `OBSIDIAN_VAULT` env var or a path the user supplies.
2. Run `scaffold-vault.sh <path>`. Creates required directory tree. Copies template files (AGENTS.md, MOC.md, schema, linking conventions, note templates) only where missing — never overwrites existing files.
3. Ensure the vault path is in Claude Code's `additionalDirectories` so Read/Edit/Write/Grep can reach it.
4. Verify by running the frontmatter validator on `_meta/AGENTS.md`.
5. Report path, files copied vs skipped, and next-step suggestions.

## How

### Step 1 — pick the path

```bash
VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/ObsidianVault}"
```

If the user named a different path, use that. Otherwise the default.

### Step 2 — scaffold

Run from this repo root:

```bash
bash skills/obsidian-setup/scripts/scaffold-vault.sh "$VAULT"
```

Expect output of the form `vault scaffolded at <path> (copied=N skipped=M)`.

### Step 3 — wire Claude Code permissions

Read `~/.claude/settings.json`. If the `additionalDirectories` array does not include the vault path, add it. Preserve existing keys and array entries. If the file does not exist, create it with the minimal shape:

```json
{
  "additionalDirectories": ["<vault-path>"]
}
```

Always re-read before write and merge — never blindly overwrite. If `permissions` or other top-level keys exist, leave them untouched.

### Step 4 — verify

```bash
bash skills/obsidian-capture/scripts/validate-frontmatter.sh "$VAULT/_meta/AGENTS.md"
```

Exit 0 = vault is healthy.

### Step 5 — report

Tell the user:
- vault path
- copied / skipped counts
- next suggested skills: `obsidian-recall <topic>` and `obsidian-capture <type>`

## Don't

- Don't overwrite user-edited files. The scaffold script handles this; trust it.
- Don't write into `knowledge/` — that's human-curated.
- Don't pre-populate seed notes beyond what `vault-template/` ships. Vault sprawl starts here.
- Don't add the vault path to `additionalDirectories` more than once — check before append.
