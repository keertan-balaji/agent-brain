# Agent Brain v2 — Phase 3a-2 Operations

Phase 3a-2 turns the dormant `failure_memories` table into a live capture surface and ships the spec's Phase-2 sanitization minimum. The Stop hook (wired in 3a-1, doing nothing useful) now scans the session transcript for failure signatures and upserts `failure_memories` rows. The `brain.write()` ingest path strips ANSI escapes from high-risk kinds and flags suspicious instruction-density content. The `brain recall` retrieval path wraps high-risk content in origin-aware delimiters so consumer LLMs treat it as data, not instructions.

## What changed

- **No new migration.** `failure_memories` (typed columns + `UNIQUE (target_problem, attempted_approach)`) and `sources.flags JSONB` already shipped in earlier phases.
- **New modules:**
  - `src/brain/sanitize.py` — `strip_ansi`, `instruction_density`, `sanitize_for_ingest` (pure).
  - `src/brain/failures.py` — `record`, `list_active`, `invalidate`, `FailureRow`.
  - `src/brain/hooks/transcript_scan.py` — `scan_for_failures`, `FailureCandidate` (pure, single-file read).
  - `src/brain/retrieval/render.py` — `quote_origin` (pure helper).
- **Wired into existing paths:**
  - `brain.write()` calls `sanitize_for_ingest` before INSERT for kinds `tool_call_output`, `command`, `web_page`, `code_file`.
  - `stop_cmd` in `src/brain/hooks/cli.py` scans the transcript and upserts failure rows after recording the `stop` event. Non-fatal — any exception is logged as `event_kind='hook_error'`.
  - `brain recall` table wraps each row's `content[:80]` via `quote_origin(kind, ...)`.
  - Bundle render's per-item bullet lines for decisions/gotchas/patterns also call `quote_origin` defensively (no-op for current selections, future-proof if high-risk kinds are ever included).
- **New CLI:** `brain failure record/list/invalidate`.
- **New skill:** `brain-failure` (record/refine/invalidate surface).

## The failure-capture loop

1. Agent runs a tool (Bash, etc.) that returns an error — `is_error: true` in the tool_result, or text matching `^(Traceback|Error|FATAL|FAILED)` / mid-line `command not found` / `Exit code [1-9]`.
2. User `/exit`s or session ends. `Stop` hook fires.
3. `brain hook stop` records the `stop` event, then:
   - Reads up to the last 200 lines of `transcript_path` (silent on missing/malformed).
   - Walks oldest → newest, tracking the most recent user prompt + most recent assistant tool_use as rolling state.
   - For each failure-signature tool_result, extracts a `(target_problem, attempted_approach, outcome_evidence)` triple, in-memory de-duped on `attempted_approach`.
   - Looks up `project_id` from `projects WHERE repo_root = cwd` (may be NULL).
   - Calls `failures.record(...)` with `auto_flagged_by="stop_hook"` — the dedup `ON CONFLICT (target_problem, attempted_approach)` bumps `retry_count` and clears any prior invalidation. Every record creates a backing `sources` row (kind='gotcha') so the narrative participates in FTS.
4. Next session, the agent can run `brain failure list` to see what's accumulated, or `brain failure invalidate <id>` to retire false positives.

## Sanitization at ingest

Applied only to high-risk source kinds: `tool_call_output`, `command`, `web_page`, `code_file`.

- **ANSI strip**: removes CSI escape sequences (e.g. `\x1b[31m`) plus non-printable control chars (CR is stripped along with the rest; only `\t` and `\n` are preserved).
- **Instruction-density flag**: counts suspicious phrase matches per 1000 chars (`ignore previous instructions`, `disregard previous|above|prior`, `you are now`, `new instructions:`, `system:`, `<system>`, `override your|the instructions|directives|rules`). Density > 1.0 sets `sources.flags.suspicious=true` + `suspicion_reason='instruction_density'` + `suspicion_score`. **Flag only — never reject.**

Auditing suspicious rows:

```sql
SELECT id, kind, flags
FROM sources
WHERE flags ? 'suspicious'
ORDER BY id DESC
LIMIT 50;
```

## Origin-aware quoting at recall

When `brain recall` prints results, content from `kind IN ('tool_call_output', 'command')` is wrapped in `<tool-output>…</tool-output>`. Content from `kind = 'web_page'` is wrapped in `<web-content>…</web-content>`. Other kinds pass through unchanged. This is the render-time half of the defense: even if instruction-shaped text slips past the ingest flag, the consuming LLM sees it tagged as data.

## CLI

```bash
# Record a failure explicitly (dedup on target+approach).
brain failure record \
  --target-problem "install Postgres pgvector on Arch" \
  --attempted-approach "docker-compose with pgvector image" \
  --outcome-evidence "image pulled; psql connection refused on 5432"

# Recent active failures.
brain failure list [--limit N] [--project-id ID]

# Mark a failure as no longer applying.
brain failure invalidate <id> --reason "fixed in commit abc123"
```

## Migration from Phase 3a-1

No schema migration. Just pull and reload:

```bash
git pull
source .venv/bin/activate
# alembic upgrade head — no-op; nothing changed
/reload-plugins   # in Claude Code, to pick up the brain-failure skill + manifest 0.6.0
```

## Known limitations

- **Heuristic false-positives.** The Stop scanner will fire on harmless Bash exits — `grep` no-match returns exit 1, some commands legitimately emit "Error: …" without failing. These get captured as failures and the user can invalidate them via `brain failure invalidate`. Refining the heuristic is intentionally deferred to Phase 4.
- **`root_cause` and `lesson` stay NULL** on auto-flagged rows. Filling them is a future workflow (Phase 4 `distill_pattern` or manual refinement via the skill).
- **No backfill** of `flags.suspicious` on existing sources rows. Only new ingests get sanitized.
- **OSC escape sequences** (e.g. terminal hyperlinks `\x1b]8;;url\x07text\x1b]8;;\x07`) are not yet stripped — the CSI-only regex leaves payload garbage after the control-char pass. Phase 4 sanitization hardening covers this.
- **Failure-memory recall surface is read-only.** Spec §Retrieval calls for `failure_memories WHERE target_problem ~ P AND attempted_approach ~ A` lookup before the agent attempts an approach; this lookup ships in Phase 3b. Until then, the bundle render includes unresolved failures and the agent can read them via `brain failure list`.

## Skills

| Skill | When to use |
|---|---|
| `brain-failure` | Record a failure explicitly, list active failures, or invalidate a stale one |
