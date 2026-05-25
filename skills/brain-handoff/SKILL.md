---
name: brain-handoff
description: Use when transferring context to another agent, another machine, or saving a checkpoint outside the brain. Exports the current resume bundle as markdown (default) or JSON. Pipe-able.
---

# brain-handoff

Export the current bundle.

## When to use

- Switching agents (Claude Code → Cursor or vice versa).
- Sharing context with a collaborator.
- Archiving a session's state before destructive work.

## How

```bash
bash skills/brain-handoff/scripts/handoff.sh [--cwd /path] [--format markdown|json] [--out file]
```

Defaults: markdown, stdout.

## Output budget

Don't paste the bundle back to the user. Confirm export.
