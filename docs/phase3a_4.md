# Agent Brain v2 — Phase 3a-4 Operations

Phase 3a-4 ships the compliance subsystem: observability + nudges to make non-capture visible. The brain cannot compel an LLM to capture, but it can flag sessions that talked a lot and wrote down little, surface bundles that survive compaction with nothing substantive, and optionally fail the SessionEnd hook hard so the next session sees a system reminder.

## What changed

- **New module:** `src/brain/compliance.py` (pure SQL aggregation + dataclass predicates)
  - `session_capture_stats(session_id) -> CaptureStats` — turn count, capture count, kind breakdown, failure count.
  - `is_under_captured(stats, *, turn_threshold=5, capture_threshold=3) -> bool` — strict `<` on captures.
  - `is_thin_bundle(BundleSelection) -> bool` — true when no decisions, gotchas, failures, or open subtasks.
  - `under_captured_sessions(engine, *, limit=50) -> list[CaptureStats]` — audit query for the report.
  - `is_strict_mode(engine) -> bool` — reads `brain_config('strict_mode', 'true')`.
- **Migrations 011 + 012:** extend `session_events_kind_check` to allow `under_captured` and `thin_session` event kinds.
- **Hook wiring:**
  - `session_end_cmd` (`src/brain/hooks/cli.py`) — after recording `event_kind='session_end'`, computes stats. If under-captured, records `event_kind='under_captured'` with the count payload. If strict_mode is on, exits 2 (non-zero — surfaces a system reminder to the next session via the harness).
  - `pre_compact_cmd` — between `gather_bundle_selection` and `render_bundle`, records `event_kind='thin_session'` when the selection has no substance.
- **`brain.helpers.health.audit`** — undercapture query rewritten to use `compliance.under_captured_sessions`. The old query LEFT JOIN against `events` (subtask-scoped) was structurally wrong for Claude Code sessions (which write to `session_events` + `sources`). Field `UndercapturedSession.event_count` kept by name but its meaning shifts to "substantive capture count" — column header in the render is unchanged.
- **CLI:** `brain compliance check/list/list-thin` mirrors the `brain failure` shape from 3a-2.
- **`brain status` extension** — appends a one-line compliance summary (under-captured + thin counts past 30 days).
- **Skill:** `brain-compliance` (record/inspect surface, mirrors the brain-failure pattern).

## The compliance loop

1. Every `UserPromptSubmit` hook records `session_events(event_kind='user_prompt_submit')` — turn counter.
2. Substantive captures during the session write to `sources` (kind ∈ {decision, gotcha, pattern, note, subtask_summary, session_summary}).
3. `SessionEnd` hook fires.
4. `session_capture_stats` aggregates: turn count from `session_events`, capture count from `sources` within `[sessions.started_at, sessions.ended_at)`.
5. `is_under_captured(stats)` returns true when `turn_count >= 5 AND capture_count < 3`.
6. If true → record `session_events(event_kind='under_captured', payload=<counts>)`.
7. If `brain_config.strict_mode = 'true'` → exit 2 from the SessionEnd hook. Claude Code surfaces a system reminder in the next session.

The next session's SessionStart bundle render includes recent `session_events`, so the `under_captured` row is visible in the resume context.

## Thin sessions

`PreCompact` runs `is_thin_bundle(selection)` on the gathered selection. True when:
- no `decisions`
- no `gotchas`
- no `failures`
- no `subtasks_open`

(Patterns and recent_events alone don't qualify a bundle as non-thin — they're support material, not durable handoff.)

A thin bundle still gets persisted (no behavior change to the existing render path), but a `session_events(event_kind='thin_session', payload={'cwd': ..., 'trigger': 'pre_compact'})` row marks it. `brain compliance list-thin` and `brain status` surface these.

## Thresholds

Hardcoded constants in `src/brain/compliance.py`:
- `turn_threshold = 5` — below this, the session is exploratory / one-shot, not under-captured.
- `capture_threshold = 3` — strictly less than this counts as under-captured.

To tune, edit the helper signature; no DB config exists for these (yet — Phase 4 may move them into `brain_config`).

## Strict mode

Opt-in. Default off. Brain runs in Docker on `127.0.0.1:5433` — use TCP or `docker exec`, not bare `psql -d brain`.

```bash
# Enable
PGPASSWORD=brain_dev_password psql -h 127.0.0.1 -p 5433 -U brain -d brain -c \
  "INSERT INTO brain_config(key, value, updated_at) VALUES ('strict_mode', 'true', NOW()) \
   ON CONFLICT (key) DO UPDATE SET value = 'true';"

# Disable
PGPASSWORD=brain_dev_password psql -h 127.0.0.1 -p 5433 -U brain -d brain -c \
  "UPDATE brain_config SET value = 'false', updated_at = NOW() WHERE key = 'strict_mode';"
```

With strict mode on, the SessionEnd hook exits with code 2 when the session is under-captured. The harness surfaces non-zero exits as a system reminder in the next session.

Strict mode is intentionally NOT on by default — exploratory sessions (asking a few questions, no captures expected) would otherwise be punished.

## Migration

```bash
git pull
source .venv/bin/activate
alembic upgrade head    # applies 011 + 012 (event_kind allowlist extensions)
/reload-plugins         # in Claude Code, to pick up brain-compliance + manifest 0.7.0
```

## CLI surface

```bash
# Inspect one session's stats by id.
brain compliance check --session-id <N>
# → session_id=N turn_count=6 capture_count=0 decision_count=0 gotcha_count=0 failure_count=0 under_captured=True

# Recent under-captured sessions (default limit 20).
brain compliance list [--limit N]

# Sessions that triggered a thin_session event (most-recent per session).
brain compliance list-thin [--limit N]
```

## Known limitations

- **Turn count is a proxy.** We count `user_prompt_submit` events as turns. Assistant-only thinking turns are invisible. Real "Claude turn" count from transcript metadata is richer but not used in 3a-4.
- **No per-project threshold.** Thresholds are global constants. A project with intentionally exploratory work (research notes, scratch) will always trip the audit; the user can lower `--capture-threshold` per-call but it's not stored.
- **Thin signal fires only on PreCompact.** Phase 3a-1 generates resume bundles only at PreCompact (not SessionEnd). If a future phase adds SessionEnd bundle generation, mirror the thin-check there.
- **No auto-remediation.** Compliance is observability + nudges. The brain does not synthesize captures the agent failed to make.
- **`UndercapturedSession.event_count` field name is a back-compat artifact.** The field now holds a substantive capture count, not events.id rows. Renaming would break `brain health` callers; tracked for a future cleanup.

## Skills

| Skill | When to use |
|---|---|
| `brain-compliance` | Inspect / audit / strict-mode toggle for under-captured + thin sessions |
