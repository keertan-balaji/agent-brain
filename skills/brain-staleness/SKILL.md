---
name: brain-staleness
description: Use after editing files in this repo to find captured knowledge that may have gone stale, or before relying on a recall result to confirm the source file hasn't changed since capture. The brain detects file changes; you decide whether the captured claim still holds.
---

# brain-staleness

## When to use

- **After substantive edits to source files.** Run `brain staleness diff` to see which captured sources reference files you just touched.
- **Before relying on a recall result.** If `brain recall` returns a source about `src/foo.py`, optionally check whether `foo.py` has changed since the capture was created.
- **At session end (automatic).** The SessionEnd hook records a `staleness_detected` event into `session_events` and surfaces the count in the next session's resume bundle. You don't have to invoke this skill explicitly for that — but the skill provides the manual triage surface.

## When NOT to use

- The captures don't reference files (no `provenance_meta` — older captures pre-v0.9.0 or non-file captures).
- You haven't edited anything substantive yet (will return empty).

## How

```bash
# Diff-based scan — only the files changed since a git ref.
bash skills/brain-staleness/scripts/staleness.sh diff [--since HEAD~1]

# Whole-DB scan — every source with provenance_meta, hash-compared.
bash skills/brain-staleness/scripts/staleness.sh check
```

## Triage workflow

For each `[source_id]` returned:

1. Read the current file (or its diff vs the capture-time hash).
2. Decide: is the captured claim still true?
   - **Still true:** ignore. Optionally re-capture to refresh the hash (capture-time sha256 will update).
   - **Stale:** invalidate via `brain.write.invalidate(<source_id>, reason='...')`, OR re-capture the new claim and let dedup handle the rest, OR invoke `agent-brain:brain-revise` to propose structured invalidation.
3. If status is `missing`: the file no longer exists. Almost always invalidate.

## Output budget

≤200 tokens per call. The CLI prints one line per stale source — cite by ID in your response, don't paste full paths into prose.
