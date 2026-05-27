# Operations

## Backup

Nightly `pg_dump` is the canonical disaster-recovery path. Add to cron:

```bash
0 2 * * * /usr/bin/pg_dump -U brain brain | gzip > "$HOME/Documents/ObsidianVault/Agent-Brain/_backups/brain-$(date +\%F).sql.gz"
```

The markdown view under `<vault>/Agent-Brain/` is a **partial fallback only** — see spec §Obsidian markdown view. Episodic stream, embeddings, retrieval logs, and procedure counters are NOT recoverable from markdown alone.

## Restore

```bash
gunzip -c brain-2026-05-24.sql.gz | psql -U brain brain
```

## Conflict resolution (markdown ↔ DB)

If the file-watcher (Phase 3) detects a markdown edit that conflicts with a recent DB write, both versions are kept (older invalidated with `invalidation_reason='conflict: see <id>'`). The user resolves via `brain reingest` after editing.

## Cost guards

Phase 1 has no LLM dependencies — no API costs. Phase 2+ introduces per-session cost caps configurable in `brain_config`.

## Sanitization minimum (Phase 3a-2)

`brain.write()` strips ANSI escape sequences and non-printable control chars from high-risk source kinds (`tool_call_output`, `command`, `web_page`, `code_file`) before INSERT. Suspicious instruction-density content is not rejected — it carries `sources.flags.suspicious = true` with a `suspicion_reason` + `suspicion_score`. Retrieval consumers see the flag and decide whether to trust the content.

Audit suspicious rows:

```sql
SELECT id, kind, uri, flags
FROM sources
WHERE flags ? 'suspicious'
ORDER BY id DESC
LIMIT 50;
```

`brain recall` wraps results from `tool_call_output` / `command` / `web_page` in `<tool-output>` / `<web-content>` delimiters at print time — a render-layer defense in depth.

Known gap: OSC sequences (terminal hyperlinks, window-title sets) are not yet stripped. Phase 4 hardening covers this.

## Failure-memory triage (Phase 3a-2)

The Stop hook auto-flags failures it sees in the session transcript. To inspect what's been captured:

```bash
brain failure list --limit 20
```

The output is a compact one-line-per-failure table; cite by `[id]` rather than pasting full evidence.

Invalidate false positives or fixed-in-the-meantime failures:

```bash
brain failure invalidate <id> --reason "fixed in commit abc123 / not actually a failure"
```

Re-occurrences (same `target_problem` + `attempted_approach`) bump `retry_count` and clear any prior invalidation — the lesson didn't stick. Auto-flagged rows have `root_cause` and `lesson` NULL; refine manually with a fresh `brain failure record` if you have insight to add (the dedup will update the same row).

## Compliance triage (Phase 3a-4)

The SessionEnd hook now flags under-captured sessions (≥5 user prompts + <3 substantive captures). The PreCompact hook flags thin bundles (no decisions/gotchas/failures/open subtasks). Both signals live in `session_events`.

```bash
# Audit recent under-captured sessions.
brain compliance list --limit 20

# Inspect one session's stats by id.
brain compliance check --session-id <N>

# Sessions that produced thin resume bundles.
brain compliance list-thin --limit 20
```

`brain status` shows a one-line summary of both counts (last 30 days).

### Strict mode (opt-in)

```sql
-- Enable: SessionEnd hook exits 2 on under-captured sessions.
INSERT INTO brain_config(key, value, updated_at) VALUES ('strict_mode', 'true', NOW())
ON CONFLICT (key) DO UPDATE SET value = 'true';

-- Disable.
UPDATE brain_config SET value = 'false', updated_at = NOW() WHERE key = 'strict_mode';
```

Off by default because exploratory sessions (no captures expected) would otherwise be punished.

### Capture thresholds

Hardcoded constants in `src/brain/compliance.py`:
- `turn_threshold = 5` — below this, no audit (exploratory work).
- `capture_threshold = 3` — strictly less than this counts as under-captured.

To change for one CLI invocation: `brain health --threshold 5` overrides the capture threshold. The turn threshold is not yet CLI-tunable.
