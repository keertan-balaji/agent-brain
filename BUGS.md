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

## 2026-05-27 — [fixed-in-v0.8.3] `brain recall` CLI defaulted to FTS-only — full hybrid stack (BGE-M3 + RRF + rerank) was built but unwired

**Where:** `src/brain/cli.py` `recall` command + `src/brain/read.py` `recall()` signature defaults
**Severity:** **critical** — the brain's headline retrieval feature was effectively absent from the default user path
**Found via:** Path D "use the brain" evaluation — captured 3 things via `brain write`, then ran `brain recall` on rephrased questions. 3/4 queries returned empty despite the captures being clearly relevant. Investigation showed `recall(embedder=None)` skips the dense leg entirely (intentional FTS-only fallback for Phase 1), but the CLI never passed an embedder.

**Symptom:** Without embeddings, retrieval was exact-token FTS only. Queries phrased with different vocabulary than the stored content (synonyms, paraphrases) returned 0 results even when the topic was clearly captured.

**Root cause (three-layer):**
1. `brain.write()` does not auto-trigger `brain ingest source` to populate `embeddings_1024`. Captures land in `sources` + `sources_fts`; the dense index stays empty unless `brain ingest source <id>` is run manually.
2. `brain.read.recall()` defaults `embedder=None` (Phase 1 behavior), making the dense leg opt-in.
3. The CLI `recall` command never constructed an embedder or reranker, so the default user path was always FTS-only despite the spec advertising hybrid as the headline feature.

**Fix (this session, partial):** `src/brain/cli.py` `recall` command now defaults to full hybrid pipeline — loads `BgeM3Embedder` + `MxbaiReranker`, passes both into `_recall`. Flags `--fts-only` / `--no-rerank` / `--no-tau` trim the stack for speed. First invocation pays the ~3s embedder load + ~2s reranker load.

**Still open:**
- (a) Backfill embeddings for prior captures (this session: backfilled 8 sources via loop, but no general CLI for "ingest all sources missing embeddings").
- (b) Make `brain write` auto-trigger `ingest source` on success so new captures are immediately retrievable. This is the right architectural fix; today's session only fixed the read path.
- (c) Test that hybrid recall returns expected results from a populated brain (smoke test, not unit test — should sit in `tests/test_recall_hybrid_smoke.py`).

**Status:** read-path fixed in v0.8.3; write-path auto-embedding still deferred (new `brain ingest backfill` is the explicit close — agent runs it after substantive captures). A/B eval confirms the impact: hit@5 = 25% (FTS-only) vs 100% (hybrid) on 16 hand-curated questions. **Block Phase 3b on this being fixed → unblocked as of v0.8.3.**

---

## 2026-05-27 — [fixed-in-v0.8.3] Reranker MIN_FREE_GB heuristic + per-reranker tau calibration

**Where:** `src/brain/retrieval/rerank.py` + `src/brain/read.py`
**Severity:** medium — defaulted to mxbai-rerank-large-v2 on 4GB GPUs, which OOMs immediately
**Found via:** Path-D A/B eval, killed first run at 41 min wall (CPU reranker too slow); second run with bge-reranker-v2-m3 showed tau abstain killing 8/16 hits because the default tau (0.65) was calibrated for mxbai's score distribution, not bge-v2-m3's sigmoid output (confident ~0.95, weak ~0.001, noise ~0.0003).

**Symptom:** On a 4GB GPU, the only available reranker (mxbai-large) doesn't fit alongside the embedder — falls back to CPU, ~30s/query. Switching to bge-reranker-v2-m3 (canonical pair for BGE-M3, fits 4GB) fired tau abstain on every weak-but-correct match because default tau=0.65 vs actual top-score ~0.003.

**Fix:** 
1. `_CrossEncoderReranker` base class with per-model `DEFAULT_TAU` + `MIN_FREE_GB` class attrs.
2. `default_reranker()` factory picks mxbai on ≥6GB GPU, bge-reranker-v2-m3 otherwise.
3. `recall()` falls back to `reranker.DEFAULT_TAU` when `tau` is None and a reranker is in play; bucket-based tau only when no reranker.
4. `brain recall` CLI uses `default_reranker()` — no more hardcoded mxbai default.

**Eval results post-calibration (16 real Qs + 4 controls, 4GB GPU):**
- FTS only: hit@5=25%, FP=0/4, 4ms/q
- Hybrid (no rerank): hit@5=100%, FP=4/4, 50ms/q
- Hybrid + bge-rerank + tau=0.01: hit@5=75%, FP=**0/4**, 1170ms/q
- Hybrid + bge-rerank + no-tau: hit@5=100%, FP=4/4, 1170ms/q

**Known limit:** bge-v2-m3 doesn't strongly separate weak-match from noise. 4/16 paraphrased queries get abstained even though correct source is in candidates. Mitigation: agent-driven retrieval uses no-tau and reads top-5; "is this in the brain?" automated queries use tau. Documented operating modes in the captured decision (`brain recall "v0.8.3 retrieval decision option G"`).

**Status:** fixed-in-v0.8.3.

---

## 2026-05-27 — [open, deferred] Multi-chunk sources skip contextual retrieval — BUGS.md saturates top-5 results

**Where:** `brain ingest source` + `brain ingest backfill` (both pass `contexts=None`)
**Severity:** medium — degrades retrieval precision for any multi-chunk capture
**Found via:** A/B eval showing source 18 (BUGS.md, 19 chunks) appearing in top-5 on nearly every query, including controls (nginx, kubernetes).

**Symptom:** Each chunk of a multi-chunk document is embedded without surrounding context. A chunk about "Click ctx.exit Phase 3a-4" loses its "this is a BUGS.md entry" framing, so it pattern-matches against queries on unrelated topics. Anthropic's Contextual Retrieval paper documents 49% retrieval-failure reduction with contextual prepend on multi-chunk docs.

**Root cause:** `_insert_chunks_and_embeddings(contexts=None)` is the default path. The contextual flow (`prepare-contexts` + `finalize-contexts`) is built but requires an agent inline to generate per-chunk summaries.

**Fix path:** Extend `brain ingest backfill` to detect multi-chunk sources (chunk count > 1) and route them through the contextual flow. Single-chunk sources (decisions, gotchas, patterns) skip — no value when chunk == whole doc.

**Status:** open — deferred to Phase 3b retrieval hardening. Current workaround: agent reads top-5 and discards the BUGS.md-chunk false positives.

---

---

## 2026-05-27 — [fixed-in-v0.8.2] Test suite wipes the dev `brain` database — TRUNCATE + alembic-downgrade-base ran against production data

**Where:** `tests/conftest.py` `pg_url` default + `_apply_migrations` autouse fixture + `_truncate_tables`
**Severity:** **critical** — silent data loss, user captures vanish on every full-suite run
**Found via:** running pytest after capturing 3 sources (psql gotcha, slash-collision gotcha, strict_mode decision) — all 3 disappeared. `SELECT COUNT(*) FROM sources` dropped to 1 (residue from a test that didn't clean). `strict_mode` row also wiped by my new conftest cleanup.

**Symptom:** Real brain captures, projects, sessions, failure_memories, retrieval_log — everything except `brain_config`-not-on-the-delete-list — gets nuked when the test suite runs. Pytest's session-scoped autouse fixture issues `alembic downgrade base` then `alembic upgrade head` on whatever `BRAIN_TEST_DB_URL` points at, and per-test `TRUNCATE ... CASCADE` runs afterward.

**Root cause:** `pg_url` defaulted to `postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain` — the same connection string the brain CLI uses for production data. No separate test DB ever existed; the assumption was the dev DB and test DB share the container but should have been distinct names.

**Fix:** Default `BRAIN_TEST_DB_URL` is now `.../brain_test` (separate database on the same Postgres container). New `_ensure_test_db_exists` helper auto-creates `brain_test` via the `postgres` admin DB if missing, installs `vector` + `pg_trgm`, then migrations run against the isolated test DB. The dev `brain` DB is now untouched by the suite. Defensive runtime check refuses to run if the URL appears to still point at the dev DB.

**Status:** fixed-in-v0.8.2 — `tests/conftest.py` overhaul. Anyone with prior captures should verify `SELECT COUNT(*) FROM sources` is intact before running the suite on this version.

---

## 2026-05-27 — [fixed-in-v0.8.2] `psql -d brain` fails — DB runs in Docker on TCP-only, no local Unix socket

**Where:** any documentation or skill body that suggests `psql -d brain ...` for direct DB access
**Severity:** low (user-visible friction; brain CLI works fine)
**Found via:** the brain-compliance skill's strict_mode example: `psql -d brain -c "INSERT INTO brain_config..."` — failed with "connection to socket /run/postgresql/.s.PGSQL.5432 failed: No such file or directory".

**Symptom:** Bare `psql -d brain` tries the default Unix socket, which doesn't exist because `docker-compose.yml` exposes Postgres only on `127.0.0.1:5433` via TCP. No local Postgres install means no socket.

**Root cause:** Brain runs in a container, port-mapped to `127.0.0.1:5433` (not the default 5432). The host has no local postgres install, so the Unix socket at `/run/postgresql/.s.PGSQL.5432` doesn't exist.

**Fix / workaround:** Use one of:
- `PGPASSWORD=brain_dev_password psql -h 127.0.0.1 -p 5433 -U brain -d brain -c "..."`
- `docker exec -it brain-postgres psql -U brain -d brain -c "..."`
- `brain` CLI subcommands (already configured via `BRAIN_DB_URL` env or default)

**Status:** fixed-in-v0.8.2 — docs updated in `skills/brain-compliance/SKILL.md`, `docs/operations.md`, and `docs/phase3a_4.md` to use TCP form or `docker exec`.

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

**Fix / workaround:** v0.8.2 wraps the truncate in a 5-attempt retry loop with exponential backoff on `OperationalError` matching `deadlock|lock timeout|statement timeout`. Each attempt is bounded by a 3-second `statement_timeout` so a stuck lock can't hang the whole suite. Also added the missing `session_events` table to the TRUNCATE list (latent bug from 3a-1).

**Status:** fixed-in-v0.8.2.

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

**Fix:** Migration 011 added `under_captured`; migration 012 added `thin_session`. Migration 013 (v0.8.2) **drops the constraint entirely** — `event_kind` is now open-ended TEXT. Future event kinds require no migration. Trade-off: misspellings won't be caught at INSERT time, but the upside of no migration-per-kind outweighs the typo risk (which only producers can introduce, and we control all of them).

**Status:** fixed-in-v0.8.2 — constraint dropped via migration 013.

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
