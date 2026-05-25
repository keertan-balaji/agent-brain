---
name: brain-session-resume
description: Use to view the latest compaction-survival bundle for the current project, or regenerate it on demand. Default behavior: show the bundle that will be injected at the next SessionStart.
---

# brain-session-resume

Inspect or refresh the resume bundle.

## When to use

- "What will the next session see when it resumes?" — show mode.
- Just finished an important chunk; force a fresh bundle without waiting for `/compact` — regenerate mode.
- Debugging: bundle injection wasn't useful → check what's in it, then improve capture.

## How

```bash
bash skills/brain-session-resume/scripts/session-resume.sh [--cwd /path] [--mode show|regenerate]
```

Defaults to `--cwd $PWD` and `--mode show`.

## Output budget

The bundle itself is ≤4000 tokens. Don't echo it back to the user verbatim — describe what's there.
