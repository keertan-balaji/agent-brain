---
name: brain-session-log
description: Use when you want to see what's been captured this session (or any prior session) — user prompts, turn boundaries, session starts/ends, pre-compact triggers. Helps debug under-capture or replay decision history.
---

# brain-session-log

Inspect what hooks have captured.

## When to use

- "What did I work on this session?" — see the chronological user-prompt + stop event trail.
- Debugging: hook didn't fire as expected; check what made it into session_events.
- Reviewing a prior session by its Claude Code UUID.

## How

```bash
bash skills/brain-session-log/scripts/session-log.sh [--limit 20] [--cc-session-id <uuid>]
```

Prints a rich table of (when, cc_session, kind, payload head).

## Output budget

≤200 tokens. Summarize the table, don't paste the full thing.
