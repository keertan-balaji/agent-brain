# Aider

Aider reads `CONVENTIONS.md` files passed via `--read` flag or referenced from the project root. Drop the universal instructions file there.

## Install per repo

```bash
cp /home/keertan/codes/brain/clients/agent-instructions.md ./CONVENTIONS.md
```

Then run aider as:

```bash
aider --read CONVENTIONS.md
```

Or add to your `~/.aider.conf.yml`:

```yaml
read:
  - CONVENTIONS.md
  - ~/Documents/ObsidianVault/_meta/AGENTS.md
```

That makes the conventions and the full vault contract part of every aider session in this repo.

## Make the vault accessible

Aider operates on whatever files you `--read` or add to the chat. To let aider write to the vault:

```bash
aider ~/Documents/ObsidianVault/agent-memory/decisions/2026-05-17-some-decision.md
```

For "recall before coding" workflows, prefer reading specific vault notes into the session rather than the whole vault — aider doesn't have a generic ripgrep-then-read affordance.
