# Agent Brain v2 — Phase 3a-1 Operations

Phase 3a-1 ships the compaction-survival core: Claude Code hooks (5 events), session_resume_bundles auto-generation on PreCompact, automatic injection at SessionStart, and 3 manual-control skills.

## What changed

- **Schema:** migration 010 — `sessions.cc_session_id`, `sessions.cwd`, `session_resume_bundles.consumed_at`, `session_resume_bundles.cwd`, new `session_events` table.
- **Hooks:** `<plugin>/hooks/hooks.json` registers SessionStart, SessionEnd, UserPromptSubmit, Stop, PreCompact. All dispatch to `brain hook <event>`.
- **CLI:** new `brain hook` sub-group (called by hooks; not for direct user invocation) and three user-facing commands: `brain session-log`, `brain session-resume`, `brain handoff`.
- **Skills:** `brain-session-log`, `brain-session-resume`, `brain-handoff`.

## The compaction-survival loop

1. User runs `/compact` (or context fills naturally).
2. `PreCompact` hook fires. `brain hook pre-compact` runs:
   - Queries decisions, gotchas, patterns, failures, open subtasks, recent events.
   - Renders a manifest JSON + markdown body (≤4000 tokens).
   - INSERTs into `session_resume_bundles`, supersedes any prior unconsumed bundle for the same cwd.
   - Emits compact instructions to stdout (becomes the compactor's "custom compact instructions").
3. Claude Code compacts the session.
4. New session starts with `source=compact`.
5. `SessionStart` hook fires. `brain hook session-start` runs:
   - Looks up the latest unconsumed, non-superseded bundle for this cwd.
   - Emits the markdown body as `additionalContext` JSON.
   - Marks the bundle `consumed_at = now()`.
6. The new session sees the bundle as a system reminder in its initial context.

## Migration from Phase 2.5

```bash
source .venv/bin/activate
alembic upgrade head    # runs migration 010
```

Then enable the plugin if not already (it carries the hooks):

```
/plugin install agent-brain@agent-brain
/reload-plugins
```

## Setup verification

Verify hooks are registered:

```
/hooks
```

You should see `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `Stop`, `PreCompact` entries pointing at `${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh`.

Verify the loop end-to-end:

```bash
brain write --kind decision --content "test decision"
# Then trigger /compact in this Claude Code session.
# After compaction, new session should show:
#   "Decisions: [id=N] test decision"
# in its initial context.
```

## Known limitations

- **No transcript replay** in bundles yet. The `transcript_path` from SessionStart stdin is captured in `session_events.payload` but not used for richer bundle content. Phase 3b will add transcript-aware bundle generation.
- **No failure capture flow yet.** `failure_memories` are read into bundles, but auto-population from Stop hooks lands in Phase 3a-2.
- **No file watcher.** Obsidian-side edits don't sync back. Phase 3a-3.
- **No compliance audit yet.** Under-captured session detection lands in Phase 3a-4.
- **Bundle token budget is a heuristic** (4 chars/token). Tighter accounting (tiktoken) is a future tuning.

## Skills

| Skill | When to use |
|---|---|
| `brain-session-log` | "What was captured this session?" — list session_events |
| `brain-session-resume` | View or regenerate the latest bundle |
| `brain-handoff` | Export the bundle for transfer to another agent/machine |
