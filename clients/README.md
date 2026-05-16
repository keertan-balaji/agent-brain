# Client install matrix

This skill pack runs natively on Claude Code (skill runtime). For every other agent, you install by dropping the same universal instructions file (`clients/agent-instructions.md`) at whatever path that agent reads.

The vault contract at `<vault>/_meta/AGENTS.md` is the shared source of truth — the per-platform file is just a pointer.

## At a glance

| Platform | Install file | Path | Method |
|---|---|---|---|
| Claude Code | `skills/*` | `~/.claude/skills/` | `bash clients/install-claude-code.sh` |
| GitHub Copilot | `github-copilot/copilot-instructions.md` | `.github/copilot-instructions.md` (per repo) | copy or symlink |
| Cursor (Project Rules) | `agent-instructions.md` | `.cursor/rules/obsidian-brain.mdc` (per repo) | copy or symlink |
| Cursor (legacy) | `agent-instructions.md` | `.cursorrules` (per repo) | copy or symlink |
| Aider | `agent-instructions.md` | `CONVENTIONS.md` (per repo) + `--read` | copy or `~/.aider.conf.yml` |
| OpenAI Codex / AGENTS.md spec | `agent-instructions.md` | `AGENTS.md` (per repo) | copy or symlink |
| Cline / Continue / Zed / Windsurf | `agent-instructions.md` | varies — see `generic/` | copy or symlink |

See the platform-specific subdir for full instructions and verification steps.

## Why one universal instructions file

`agent-instructions.md` is short and self-contained. It tells any agent:

1. The vault lives at `~/Documents/ObsidianVault/` (overridable).
2. Read `<vault>/_meta/AGENTS.md` for full conventions.
3. The "create `projects/<name>/` first" rule is mandatory.
4. Search before reading; rank by section priority; cap at 3–5 notes.
5. Write to `agent-memory/` freely; never to `knowledge/` without approval.

Every other detail (frontmatter schema, linking, templates) is read from the vault itself at runtime — not embedded in the install file — so updates to conventions don't require re-installing across N repos.

## Updating

When this repo's conventions change:

- **Claude Code**: skills are symlinked, so the change is live next session. No reinstall.
- **Other platforms**: if you symlinked, same — change is live. If you copied, re-run the copy step.
- **Vault contract** (`_meta/AGENTS.md`): updated in the vault by re-running `/obsidian-setup` (it fills gaps; user edits are preserved). Or manually copy `vault-template/_meta/AGENTS.md` over the live vault's copy when you want the new version.
