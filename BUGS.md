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
