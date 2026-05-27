# BUGS.md

Running log of bugs / errors / rough edges encountered while using agent-brain in real workflows. New entries at the top.

Format per entry:

```
## YYYY-MM-DD — [STATUS] short title

**Where:** file:line or surface (CLI / hook / skill)
**Severity:** low | medium | high
**Found via:** (brief context — what was being done)

**Symptom:** what went wrong

**Root cause:** (if known)

**Fix / workaround:** (if applied, link to commit; else: tracking)

**Status:** open | fixed-in-<commit> | wontfix | duplicate-of-#N
```

---

## 2026-05-27 — [open] `psql -d brain` fails — DB runs in Docker on TCP-only, no local Unix socket

**Where:** any documentation or skill body that suggests `psql -d brain ...` for direct DB access
**Severity:** low (user-visible friction; brain CLI works fine)
**Found via:** the brain-compliance skill's strict_mode example: `psql -d brain -c "INSERT INTO brain_config..."` — failed with "connection to socket /run/postgresql/.s.PGSQL.5432 failed: No such file or directory".

**Symptom:** Bare `psql -d brain` tries the default Unix socket, which doesn't exist because `docker-compose.yml` exposes Postgres only on `127.0.0.1:5433` via TCP. No local Postgres install means no socket.

**Root cause:** Brain runs in a container, port-mapped to `127.0.0.1:5433` (not the default 5432). The host has no local postgres install, so the Unix socket at `/run/postgresql/.s.PGSQL.5432` doesn't exist.

**Fix / workaround:** Use one of:
- `PGPASSWORD=brain_dev_password psql -h 127.0.0.1 -p 5433 -U brain -d brain -c "..."`
- `docker exec -it brain-postgres psql -U brain -d brain -c "..."`
- `brain` CLI subcommands (already configured via `BRAIN_DB_URL` env or default)

**Status:** open — fix docs in `skills/brain-compliance/SKILL.md`, `docs/operations.md`, and any other place suggesting bare `psql -d brain`.

---

## 2026-05-27 — [fixed-in-440a10a] Skill/command name collision = bare slash command unresolvable

**Where:** Claude Code plugin resolver — `skills/<name>/SKILL.md` and `commands/<name>.md` with the same name
**Severity:** medium (user-visible — slash command appears in autocomplete but errors on invocation)
**Found via:** `/using-agent-brain` returned "Unknown command" while `/agent-brain:using-agent-brain` worked.

**Symptom:** When a plugin ships both `skills/<NAME>` (auto-aliased to `/<plugin>:<NAME>` AND optionally `/<NAME>` bare) AND `commands/<NAME>.md` (registers `/<NAME>` bare), Claude Code's autocomplete shows BOTH entries but the bare-form resolver fails with "Unknown command".

**Root cause:** Bare slash-command namespace collision between a skill alias and an explicit command file. Resolver can't disambiguate.

**Fix:** Rename the command file (or the skill) so the bare paths don't collide. v0.8.1 renames `commands/using-agent-brain.md` → `commands/brain.md`; skill keeps the longer name.

**Status:** fixed in 440a10a (v0.8.1). When designing future slash commands, never reuse a skill's bare name.

---

## 2026-05-27 — [open] Test deadlock race: `_truncate_tables` fixture vs subprocess hook tests

**Where:** `tests/conftest.py` `_truncate_tables` fixture interacting with subprocess-based hook e2e tests
**Severity:** low (flaky; passes on retry)
**Found via:** Phase 3a-4 final-review full-suite run (16 fails + 3 errors first run, 243 passing second run — same suite, no code change).

**Symptom:** Random tests fail with `sqlalchemy.exc.OperationalError: DeadlockDetected` mid-truncate. Always involves a subprocess hook test (`brain hook stop` / `brain hook session-end`) running concurrently with `_truncate_tables`.

**Root cause:** The `_truncate_tables` fixture issues a session-scope `TRUNCATE ... CASCADE` after each test. If a hook subprocess from a prior test still holds row-level locks (e.g. a SELECT or INSERT inside a transaction that didn't commit before the test exited), the TRUNCATE blocks waiting for locks, then deadlocks against the next test's TRUNCATE.

**Fix / workaround:** Re-run flakes. Real fix would be either (a) make `_truncate_tables` retry on deadlock with a small backoff, or (b) explicitly `wait` on subprocess pids before tearing down. Pre-existing — not introduced by 3a-4.

**Status:** open — pre-existing test-infra issue. Not blocking merge.

---

## 2026-05-27 — [fixed-in-e49f704] `ctx.exit()` raises `click.exceptions.Exit`, not `SystemExit`

**Where:** Click 8.x context exit semantics; affects any hook handler using `ctx.exit(n)` for non-zero exits
**Severity:** medium
**Found via:** Phase 3a-4 Task 3 — strict-mode SessionEnd was supposed to exit non-zero, but `except SystemExit: raise` was the wrong guard.

**Symptom:** A `try/except Exception` block around `ctx.exit(2)` swallows the intended exit (because `click.exceptions.Exit` inherits from `RuntimeError → Exception`), then logs the swallowed exit as a `hook_error` and exits 0 instead of 2.

**Root cause:** Click 8.x changed `ctx.exit()` to raise `click.exceptions.Exit`, not stdlib `SystemExit`. The two are unrelated in the exception hierarchy — `SystemExit` inherits from `BaseException` (and was never caught by `Exception`); `click.exceptions.Exit` inherits from `RuntimeError` (so a bare `Exception` clause DOES catch it).

**Fix:** Catch `(SystemExit, click.exceptions.Exit)` explicitly BEFORE the bare-Exception non-fatal guard, and re-raise.

**Status:** fixed in e49f704 (Phase 3a-4 SessionEnd). Apply same pattern to any future hook that uses `ctx.exit()`.

---

## 2026-05-27 — [fixed-in-e49f704] `session_events.event_kind` CHECK constraint blocks new kinds

**Where:** `session_events_kind_check` constraint from migration 010
**Severity:** high — silent insert failure if not migrated
**Found via:** Phase 3a-4 Task 3 — attempting to write `event_kind='under_captured'` failed with `CheckViolation`.

**Symptom:** Any new `event_kind` value not in the original 6-item allowlist (`session_start`, `session_end`, `user_prompt_submit`, `stop`, `pre_compact`, `hook_error`) raises a CheckViolation at INSERT time. The Stop hook's existing `event_kind='hook_error'` wrap swallows the error and logs it as ANOTHER hook_error event — infinite reentrancy risk.

**Root cause:** Migration 010 hard-coded the kind allowlist as a CHECK constraint. Future phases adding new kinds must migrate.

**Fix:** Migration 011 drops + recreates the constraint with `under_captured` added. Task 4 needs another migration (012) to add `thin_session`.

**Status:** partial — `under_captured` added in 011. `thin_session` lands in Task 4 / migration 012. Any future event kind requires a migration; consider relaxing the CHECK or moving the allowlist into a lookup table in Phase 4.

---

## 2026-05-27 — [fixed-via-cleanup] `brain_config` not in conftest TRUNCATE list — strict_mode leaks across tests

**Where:** `tests/conftest.py` `_truncate_tables` fixture
**Severity:** low — only affects tests that mutate brain_config; deliberately preserved so seeded config rows survive
**Found via:** Phase 3a-4 Task 3 — strict_mode set to 'true' in one test leaked into a later test that expected `is_strict_mode() == False`.

**Symptom:** Test order-dependent failures when one test sets `brain_config('strict_mode', 'true')` and the next reads `is_strict_mode()`.

**Root cause:** `brain_config` is intentionally excluded from `_truncate_tables` to preserve seeded constants. Tests that mutate it must self-clean.

**Fix:** Tests that toggle `strict_mode` explicitly reset to 'false' at the end, OR use a per-test fixture that records and restores prior state.

**Status:** worked around in `test_hook_session_end_compliance.py`. Phase 3a-4 Task 9 docs note this as a testing convention.

---

## 2026-05-27 — [open] Stop-hook false-positive rate ~66% on smoke-test session

**Where:** Stop hook → `transcript_scan.py` → `failures.record`
**Severity:** medium
**Found via:** Phase 3a-2 live verification. Single test session produced 3 auto-flagged failures; 1 legit (a `git push` 403), 2 spurious (`brain --version` — option doesn't exist but the command otherwise succeeds; chained `git status; git log; git tag | head` where the head pipe likely returned non-zero on EOF).

**Symptom:** Every Bash that returns is_error=true OR emits "Error:" / "Traceback" / "FAILED" anywhere gets flagged. Trivial CLI usage errors (unknown flag, no-match grep, head-on-tiny-output) fire alongside real failures.

**Root cause:** Heuristic is intentionally broad per spec § "Sanitization at ingest" Phase-2 minimum. Refinement is deferred to Phase 4. Documented in `docs/phase3a_2.md` Known Limitations.

**Fix / workaround:** Manual `brain failure invalidate <id> --reason ...`. Phase 3a-4 adds compliance counters that surface noise volume; Phase 4 owns heuristic refinement.

**Status:** open — wontfix until Phase 4

---

## 2026-05-27 — [fixed-in-d0472fc] SQLAlchemy `:param` clashes with Postgres `::` cast in NULL inference

**Where:** `src/brain/compliance.py` `under_captured_sessions` query
**Severity:** low
**Found via:** Phase 3a-4 Task 1 implementation. Adding an optional `since` filter via `CAST(:since AS timestamptz)` or `(:since IS NULL OR ended_at >= :since)` tripped Postgres' type inference on the NULL literal — also exposed risk of `:colon` collisions if a future query needs Postgres `::` casts.

**Symptom:** Type-inference errors on NULL parameters; potential confusion between SQLAlchemy bind params (`:name`) and Postgres double-colon casts (`expr::type`).

**Root cause:** SQLAlchemy `text(...)` lexes `:name` as a bind site; Postgres uses `expr::type` for casts. Adjacent `::` sequences in a `text(...)` literal can confuse the lexer.

**Fix:** Conditionally concatenate the `since` clause at Python level (only when `since is not None`); separately use `CAST(:x AS jsonb)` rather than `:x::jsonb` when a cast is needed.

**Status:** fixed in d0472fc; documented here as a recurring gotcha for future SQL.

---

## 2026-05-27 — [fixed-in-e97292a] Stop / SessionEnd hookSpecificOutput envelope rejected by harness

**Where:** `src/brain/hooks/cli.py` `_emit_empty_output` → harness Stop schema
**Severity:** high (blocks Stop hook silently — emits a schema-validation error in transcript)
**Found via:** session startup error message: `Hook JSON output validation failed — (root): Invalid input`.

**Symptom:** Stop / SessionEnd hooks emitted `{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":""}}`, but harness schema for those events does not accept `additionalContext` (only PreToolUse / UserPromptSubmit / PostToolUse / PostToolBatch do).

**Root cause:** `_emit_empty_output` used the same JSON shell for all events. SessionStart legitimately needs `additionalContext` (that's how the resume bundle reaches the new session); Stop and SessionEnd do not.

**Fix:** Added `_emit_noop()` that emits bare `{}` for Stop / SessionEnd. UserPromptSubmit retained the `additionalContext=""` form (required by its schema). Shell fallback in `hooks/run-hook.sh` branches by event name.

**Status:** fixed in e97292a (carried into v0.6.0).

---

## 2026-05-27 — [tracked-by-p3a-4] `health.audit` undercapture query counts the wrong table

**Where:** `src/brain/helpers/health.py:58-77`
**Severity:** medium (renders the audit blind to under-captured sessions)
**Found via:** Phase 3a-4 plan investigation.

**Symptom:** `brain health` reports zero under-captured sessions even when sessions captured nothing.

**Root cause:** The audit LEFT JOINs `sessions` to the `events` table (canonical subtask-scoped episodic stream). Claude Code sessions never write to `events` — they write to `session_events` (hooks) and `sources` (substantive captures via `brain.write`). The HAVING clause's `COUNT(ev.id) > 0` then filters out every real Claude Code session.

**Fix / workaround:** Phase 3a-4 Task 2 rewrites the query to delegate to `compliance.under_captured_sessions`, which counts `session_events.user_prompt_submit` for turn count and `sources WHERE kind IN capture-worthy AND created_at within session window` for capture count.

**Status:** tracked — fix lands in Phase 3a-4 Task 2.
