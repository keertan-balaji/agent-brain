# Agent Brain v2 — Design

**Date:** 2026-05-23
**Status:** Draft, awaiting user review
**Author:** keertan + Claude
**Predecessors:**
- `2026-05-17-obsidian-second-brain-skill-pack-design.md` (v1, shipped)
- `2026-05-17-obsidian-second-brain-skill-expansion-design.md` (v1.5 expansion spec)

## Goal

Build the agent brain: a persistent cognition store that preserves *what the agent did, what worked, what didn't, and what it learned* across sessions and through context compaction. Then layer higher-order operations on top — query, summarize, compare, contrast — that turn raw stored cognition into usable working memory for the next session.

Obsidian remains a read view for humans, not the primary store.

## Problem (the real one)

Coding agents lose 90% of their working state when conversations compact. Tool calls, command outputs, error traces, working hypotheses, "the second approach we tried and abandoned because of X" — all of it disappears or degrades into a few lossy summary sentences. The agent restarts cold every time, re-derives state, re-makes the same mistakes, re-discovers the same dead ends.

Secondary problem: even within a single session, the agent has no higher-order operations over what it just saw. It can read 50 files but cannot answer "summarize the data flow through these 12 modules" without doing all the reasoning from scratch every time.

The current markdown pack (`v1.0`) addresses durable knowledge (`knowledge/`), structured project notes (`projects/`), and free-form captures (`agent-memory/`). It doesn't address: tool-call-level fidelity, failure memory as a first-class type, compaction-survival bundles, semantic+structural+temporal hybrid retrieval, embedding-versioned indexes.

## Non-goals

- Replacing Obsidian. Obsidian is the human reading interface; we render markdown views for humans, the brain is queried by agents.
- A general-purpose AGI memory system. Scope: coding-agent cognition + research-intensive work, single user (initially), local-first.
- Real-time multi-agent concurrency. One agent writes at a time. Future-compatible with multi-agent via Postgres locking but not a v1 requirement.
- Cloud hosting. Local Postgres, local embedding model option, local everything by default. Cloud embedders supported as a config swap.
- Reinventing what 2026 SOTA already settled. We adopt RRF, halfvec, HNSW, bi-temporal validity, embedding-model-versioning, cross-encoder reranking, progressive disclosure (Anthropic Skills format), LangMem taxonomy.

## SOTA positioning

This design is informed by a survey of the 2026 agent-memory field. Closest analog is **LangMem** (primitives over pgvector). Our differentiators against the field:

| Capability | Status in the field | What we ship |
|---|---|---|
| Tool-call / command-output preservation | Conversational only (Mem0, Letta, Zep) | First-class `tool_call_event` table |
| Failure memory as typed entity | Missing in popular frameworks | First-class `failure_memories` table with typed columns (target_problem, attempted_approach, root_cause, lesson, retry_count) — see §Failure memory |
| Provenance typing (captured vs synthesized) | Missing — most systems re-ingest LLM outputs without distinction | First-class `provenance_kind` + `generation_depth` + RRF down-weight; brain-rot defense from day one |
| Procedural lifecycle (Build/Retrieve/Update/Deprecate) | Loose tags / unmaintained skill files | First-class `procedures` table per Memp (arxiv 2508.06433) with success/failure counters + auto-deprecate trigger |
| Compounding self-test | Anecdotal at best | Weekly replay-vs-current regression against `retrieval_log`; 4-week trend gate; brain-rot ratio alarm |
| Generative lint with user-facing questions | Silent flags or absent | `brain-health --lint` runs nightly NLI, surfaces contradictions as ARIA-pattern questions, FP-target-tuned per ClueBot NG framing |
| Compaction-survival bundle | Letta paging is closest, heavy | Pre-computed `session_resume_bundle` per active project |
| Cross-tool portability | Documented gap (MemPalace etc. partial) | Postgres + Anthropic Skills format ⇒ portable to Claude/Codex/Cursor/Gemini |
| Provenance per claim | Best-in-class systems do span-level | Same: every retrieval returns source URI + char span |
| Bi-temporal validity | Graphiti only | Adopted: `t_valid`, `t_invalid` on every row that can become stale |
| Embedding versioning | Most systems silently break | `embedding(row_id, model_id, version, vec)` from day one |

## Architecture

Five layers. Each owns one concern, communicates over well-defined interfaces.

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. CAPTURE (3 paths, all converging into the same write API)          │
│     • Agent-proactive  (mandatory discipline rule, AGENTS.md)          │
│     • Claude Code hooks  (PostToolUse / PreCompact / Stop / Session…)  │
│     • User-explicit  (/brain remember "…" or via Obsidian editor)      │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼ Python ingestion pipeline
┌────────────────────────────────────────────────────────────────────────┐
│  2. STORAGE (Postgres + pgvector, single local instance)               │
│     Memory taxonomy (LangMem canonical):                               │
│       • semantic   — facts about the world / repo / domain            │
│       • episodic   — sessions, subtasks, events, tool calls           │
│       • procedural — skills, recipes, heuristics                      │
│       • failure    — what was tried, why it didn't work               │
│     Each row: content TEXT (canonical) + metadata + bi-temporal       │
│     validity. Derived: tsvector (FTS), embeddings (pgvector halfvec)   │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  3. RETRIEVAL (hybrid, FP/FN-hardened)                                 │
│     Postgres FTS + pgvector kNN  →  RRF  →  cross-encoder rerank       │
│     Metadata pre-filter: project, validity, type, status, recency      │
│     [Specific stack details refined in §Retrieval below post-research] │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  4. REASONING (Python helpers, LLM-mediated where needed)              │
│     summarize / compare / contrast / cite / extract-claims /           │
│     trace-data-flow / propose-links / generate-resume-bundle           │
└──────────────────────────────┬─────────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  5. INTERFACES                                                         │
│     • Skills (Anthropic Skills format, cross-platform)                │
│     • Obsidian markdown export (derived, one-way, human reading)       │
│     • CLI (`brain ...` for humans and scripts)                        │
│     • MCP server (later, exports brain as MCP tools)                  │
└────────────────────────────────────────────────────────────────────────┘
```

## Schema

Postgres 16+ with `vector`, `pg_trgm`, and `btree_gist` extensions. Single database `brain`. All timestamps `TIMESTAMPTZ`. Bi-temporal columns on every "fact-bearing" row.

### Core tables

```sql
-- The canonical content. Lossless. Source of truth.
CREATE TABLE sources (
  id              BIGSERIAL PRIMARY KEY,
  kind            TEXT NOT NULL,        -- 'tool_call' | 'command' | 'edit' | 'decision' |
                                        -- 'note' | 'paper' | 'code_file' | 'web_page' | …
  uri             TEXT,                 -- e.g. file://… or https://… or tool://Bash/123
  content         TEXT NOT NULL,        -- the actual text. Lossless contract differs by kind — see §Content fidelity rule below.
  content_hash    BYTEA NOT NULL,       -- sha256 of content for scoped dedup (NOT a global identity — see scope rule)
  mime            TEXT,                 -- 'text/plain', 'text/markdown', 'application/x-python', …
  tokens          INT,                  -- approximate token count
  lang            TEXT,                 -- language code if applicable
  fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Bi-temporal validity (Graphiti pattern)
  t_valid_from    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  t_valid_to      TIMESTAMPTZ,          -- NULL = currently valid
  invalidation_reason TEXT,             -- nullable, why invalidated
  -- Provenance
  parent_id       BIGINT REFERENCES sources(id), -- for chunks of a larger document
  span_start      INT,                  -- char offset in parent
  span_end        INT,
  -- Primary project this source belongs to. NULL = global/cross-project knowledge.
  -- For cross-project sources (a paper relevant to N projects), use source_projects M2M (below).
  project_id      BIGINT REFERENCES projects(id),
  -- Source-level status, distinct from bi-temporal validity. 'active' is the default;
  -- 'archived' soft-hides from default retrieval without invalidating the row.
  -- Bi-temporal validity (t_valid_*) is for fact-revision; status is for visibility.
  status          TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','archived','draft')),
  -- Provenance discipline: distinguish observed/captured content from synthesized content.
  -- This is load-bearing for brain-rot prevention — synthesized content is down-weighted at
  -- retrieval to prevent the recursive-training drift documented in Oct-2025 LLM brain rot work.
  provenance_kind TEXT NOT NULL DEFAULT 'captured'
                  CHECK (provenance_kind IN ('captured','ingested','synthesized','user_authored')),
  synthesized_from BIGINT[],            -- if provenance_kind='synthesized', source_ids that produced this
  -- Generation depth for brain-rot down-weight. Computed at write time by brain.write() as
  --   0  when provenance_kind != 'synthesized'
  --   1 + MAX(generation_depth) over the rows referenced by synthesized_from, otherwise.
  -- Hard-capped at 3; brain.write() rejects writes that would produce depth > 3 (caller must
  -- consolidate input sources first). This eliminates runaway recursive synthesis.
  generation_depth SMALLINT NOT NULL DEFAULT 0
                   CHECK (generation_depth BETWEEN 0 AND 3),
  -- Free-form flags JSONB for sanitizer, suspicious-content markers, stale-provenance, etc.
  flags           JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX sources_kind_idx ON sources(kind);
CREATE INDEX sources_project_idx ON sources(project_id) WHERE project_id IS NOT NULL;
CREATE INDEX sources_status_idx ON sources(status);

-- Many-to-many for sources that legitimately belong to multiple projects (a shared paper,
-- a cross-cutting decision). Most sources don't need this; sources.project_id covers the
-- primary association. source_projects is queried by the retrieval pre-filter via UNION.
CREATE TABLE source_projects (
  source_id   BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  project_id  BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  PRIMARY KEY (source_id, project_id)
);
CREATE INDEX sources_validity_idx ON sources(t_valid_from, t_valid_to);
CREATE INDEX sources_provenance_idx ON sources(provenance_kind);
-- Scoped dedup: only one CURRENTLY-VALID row per (kind, uri, content_hash) — preserves
-- distinct observations that happen to share text (two commands with identical output in
-- different sessions; same note body in two projects). NULL uri tied per-kind.
CREATE UNIQUE INDEX sources_scoped_active_idx
  ON sources (kind, COALESCE(uri,''), content_hash) WHERE t_valid_to IS NULL;
-- Non-unique hash index for cross-history lookups.
CREATE INDEX sources_hash_lookup_idx ON sources(content_hash);

-- Auto-update updated_at on row mutation.
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER sources_touch BEFORE UPDATE ON sources
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
```

**Content fidelity rule** (per-kind, resolves the lossless-vs-truncation ambiguity):

| Kind | Fidelity | Storage |
|---|---|---|
| `decision`, `note`, `gotcha`, `pattern`, `paper`, `web_page`, `code_file`, `chunk_context`, `faq`, `session_summary`, `subtask_summary` | **Lossless** — `content` is byte-identical to the source | inline `sources.content` |
| `command` (the invoked command string itself) | Lossless | inline |
| `tool_call_output` (Bash stdout/stderr, Read file contents at-time-of-read) | **Lossy by policy** — head + tail + error-span only (per §Capture Path 2). Full output is NOT stored, by design. | inline `sources.content` holds the truncated representation; `sources.flags = {'truncation': {'head_bytes': X, 'tail_bytes': Y, 'middle_elided': Z}}` records what was dropped |
| `image`, `binary_artifact` (Phase 4+) | Reference-only | `sources.content` holds a textual descriptor; the artifact lives in `artifacts.blob_path` (filesystem path) |

The "lossless source of truth" claim earlier in the spec applies to every kind **except `tool_call_output` and large `web_page` ingests** (which may be size-capped). Tool-output truncation is policy, not accident: full stdout for a long-running test run is unbounded and would dominate DB growth. The error-span preservation policy (§Capture Path 2) is the explicit fidelity bound.

**Re-assertion semantics** (the bi-temporal pattern in plain English):

- Inserting content whose `content_hash` already exists in a currently-valid row is a no-op (return the existing `id`).
- Editing existing content: the old row is invalidated (`t_valid_to = NOW()`, `invalidation_reason` set), a new row inserted with the new content. Downstream pointers (events, classifications) continue to reference the old `id` — historical correctness preserved.
- Re-asserting previously-invalidated content (same hash, now valid again): a new row is inserted; old invalidated row stays as history. The partial unique index permits this because only the new row has `t_valid_to IS NULL`.
- This is enforced by the application-layer `brain.write()` API; the spec commits to a `find_active_by_hash_and_kind_and_uri → return_id_or_insert` flow rather than relying on database constraints alone (see scope rule below).

```sql
-- Full-text index, generated from content.
CREATE TABLE sources_fts (
  source_id  BIGINT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
  tsv        TSVECTOR NOT NULL
);
CREATE INDEX sources_fts_idx ON sources_fts USING GIN(tsv);

-- Embeddings. Multiple per source allowed (different models, different versions).
-- pgvector requires a fixed dimension per HNSW-indexed column, so we partition the
-- embedding store by dimension: one table per dim. v2.0 ships embeddings_1024
-- (BGE-M3 dense, mxbai-embed-large-v1, voyage-3 at 1024d). Adding a new dim is a
-- new migration that creates embeddings_<dim>.
CREATE TABLE embeddings_1024 (
  source_id  BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  model_id   TEXT NOT NULL,             -- 'bge-m3' | 'mxbai-embed-large-v1' | 'voyage-3-large' …
  model_ver  TEXT NOT NULL,             -- specific version tag (e.g. '2024-06', 'v1.5')
  vec        HALFVEC(1024) NOT NULL,    -- float16; fixed dim required for HNSW
  embedded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (source_id, model_id, model_ver)
);
CREATE INDEX embeddings_1024_hnsw_idx ON embeddings_1024
  USING hnsw (vec halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);
-- Partial index per active model speeds the common-case query.
CREATE INDEX embeddings_1024_active_idx ON embeddings_1024(model_id, model_ver);

-- Active embedding configuration. The retrieval layer reads `active_embedding` to
-- pick which (model_id, model_ver) to filter on. Changing this is a deliberate act —
-- re-embedding the corpus is a separate migration.
CREATE TABLE brain_config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Seeded at install:
--   ('active_embedding_model_id', 'bge-m3')
--   ('active_embedding_model_ver', '2024-06')
--   ('active_embedding_dim', '1024')

-- Memory taxonomy: a source can belong to multiple buckets (e.g., a failure is
-- both `failure` AND `episodic`; a curated decision becomes `semantic` while
-- remaining `episodic` for the originating session).
CREATE TABLE memory_classifications (
  source_id  BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  bucket     TEXT NOT NULL CHECK (bucket IN ('semantic', 'episodic', 'procedural', 'failure')),
  classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  classifier TEXT NOT NULL,                -- 'agent' | 'hook' | 'user' | 'auto-router'
  PRIMARY KEY (source_id, bucket)
);
CREATE INDEX memory_classifications_bucket_idx ON memory_classifications(bucket);
```

**Bucket-assignment rules** (pre-resolves ambiguous cases the reviewer flagged):

| Source kind | Buckets assigned |
|---|---|
| `decision` (during work) | `episodic` (in the session) + `semantic` (the reasoning) |
| `decision` (curated, promoted) | `semantic` only (the originating event row remains episodic) |
| `gotcha` / `blocker` / failed attempt | `failure` + `episodic` |
| `pattern` / recipe / heuristic | `procedural` |
| `pattern` derived from repeated failures | `procedural` + `failure` |
| `tool_call` / `command` / `observation` | `episodic` only |
| `architecture` / `api` / `glossary` / `process` | `semantic` only |
| `paper` / `code_file` / `web_page` (external ingest) | `semantic` only |
| `session_summary` / `subtask_summary` | `episodic` only |

The classifier (extending the existing `agent-store-decide` skill) applies these rules at capture time.

### Episodic stream (sessions → subtasks → events)

```sql
CREATE TABLE projects (
  id           BIGSERIAL PRIMARY KEY,
  slug         TEXT NOT NULL UNIQUE,
  task_type    TEXT NOT NULL CHECK (task_type IN ('development','research','repo-analysis','generic')),
  status       TEXT NOT NULL DEFAULT 'active',
  repo_root    TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sessions (
  id           BIGSERIAL PRIMARY KEY,
  project_id   BIGINT REFERENCES projects(id),
  agent        TEXT NOT NULL,            -- 'claude-code' | 'codex' | 'cursor' | …
  started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at     TIMESTAMPTZ,
  summary_id   BIGINT REFERENCES sources(id) -- pointer to a session summary source
);

CREATE TABLE subtasks (
  id           BIGSERIAL PRIMARY KEY,
  session_id   BIGINT NOT NULL REFERENCES sessions(id),
  title        TEXT NOT NULL,
  goal         TEXT,
  started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at     TIMESTAMPTZ,
  outcome      TEXT CHECK (outcome IN ('success','failure','abandoned','in_progress'))
);

CREATE TABLE events (
  id           BIGSERIAL PRIMARY KEY,
  subtask_id   BIGINT REFERENCES subtasks(id),
  session_id   BIGINT NOT NULL REFERENCES sessions(id),
  ordinal      INT NOT NULL,
  kind         TEXT NOT NULL,            -- 'tool_call' | 'observation' | 'reflection' |
                                         -- 'decision' | 'plan' | 'blocker' | 'resolution' |
                                         -- 'user_correction' (user rejected an agent action;
                                         --   `source_id` points to the rejection note;
                                         --   consumed by brain-schema-evolve)
  tool         TEXT,                     -- for tool_call: 'Bash' | 'Edit' | 'Read' | …
  input_id     BIGINT REFERENCES sources(id),  -- tool input (cmd, file path, …)
  output_id    BIGINT REFERENCES sources(id),  -- tool output (stdout, file contents, …)
  source_id    BIGINT REFERENCES sources(id),  -- semantic note attached to event
  status       TEXT,                     -- 'ok' | 'error' | 'timeout' | 'denied'
  duration_ms  INT,
  procedure_id BIGINT,                   -- if this event applied a procedures row; FK added in
                                         -- the same migration that creates procedures (Phase 1)
  occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (session_id, ordinal)
);
CREATE INDEX events_subtask_idx ON events(subtask_id);
CREATE INDEX events_procedure_idx ON events(procedure_id) WHERE procedure_id IS NOT NULL;
-- FK added after procedures table is created (same migration):
-- ALTER TABLE events ADD CONSTRAINT events_procedure_fk FOREIGN KEY (procedure_id)
--   REFERENCES procedures(id) ON DELETE SET NULL;
```

### Knowledge graph (lightweight, layered on top)

```sql
CREATE TABLE entities (
  id            BIGSERIAL PRIMARY KEY,
  kind          TEXT NOT NULL,           -- 'person'|'concept'|'repo'|'module'|'paper'|'symbol'|…
  canonical_name TEXT NOT NULL,
  aliases       TEXT[],
  source_id     BIGINT REFERENCES sources(id),
  t_valid_from  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  t_valid_to    TIMESTAMPTZ
);
CREATE INDEX entities_kind_idx ON entities(kind);

CREATE TABLE edges (
  src_id        BIGINT NOT NULL REFERENCES entities(id),
  dst_id        BIGINT NOT NULL REFERENCES entities(id),
  relation      TEXT NOT NULL,           -- 'cites'|'refutes'|'extends'|'implements'|'calls'|…
  weight        REAL,
  source_id     BIGINT REFERENCES sources(id), -- which source asserts this edge
  t_valid_from  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  t_valid_to    TIMESTAMPTZ,
  PRIMARY KEY (src_id, dst_id, relation)
);
```

### Failure memory (typed entity, not just a tag)

Failure memory is a load-bearing differentiator — promoted from a string-tag to a real table joined to `sources`. The `sources` row holds the narrative; the typed columns are what makes "you tried this 2 weeks ago" a structured lookup, not a hopeful vector hit.

```sql
CREATE TABLE failure_memories (
  id                 BIGSERIAL PRIMARY KEY,
  source_id          BIGINT NOT NULL REFERENCES sources(id),   -- narrative body lives here
  target_problem     TEXT NOT NULL,            -- "install Postgres + pgvector on Arch"
  attempted_approach TEXT NOT NULL,            -- "docker-compose with pgvector image"
  outcome_evidence   TEXT,                     -- pointer or quote demonstrating the failure
  root_cause         TEXT,                     -- once identified
  lesson             TEXT,                     -- the rule-of-thumb to remember
  retry_count        INT NOT NULL DEFAULT 1,
  last_attempted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  first_attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  project_id         BIGINT REFERENCES projects(id),
  t_valid_from       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  t_valid_to         TIMESTAMPTZ,
  invalidation_reason TEXT,                    -- e.g. 'superseded by success at event N'
  -- Deduplication key: a re-attempt of the same approach for the same problem
  -- finds the existing row and bumps retry_count rather than creating a new row.
  UNIQUE (target_problem, attempted_approach)
);
CREATE INDEX failure_memories_problem_idx ON failure_memories USING GIN(to_tsvector('english', target_problem));
CREATE INDEX failure_memories_approach_idx ON failure_memories USING GIN(to_tsvector('english', attempted_approach));
```

Recall flow: when an agent is about to attempt approach A for problem P, the brain runs `failure_memories WHERE target_problem ~ P AND attempted_approach ~ A AND t_valid_to IS NULL` (with fuzzy match via tsvector or vector similarity on the two columns). A hit → surface "you tried this before, retry_count=N, lesson: …" before the agent commits the attempt.

Invalidation: if the same approach later succeeds (root cause was environmental, since fixed), the failure row is invalidated with `invalidation_reason='superseded by success at <event_id>'`. The history is preserved.

### Procedural memory (Memp lifecycle)

Procedures (recipes, heuristics, learned skills) need explicit Build / Retrieve / Update / Deprecate state — otherwise the procedural store rots: deprecated recipes get re-applied, succession isn't tracked, and there's no signal of which procedures actually work in practice. The Memp paper (arxiv 2508.06433, v2 Apr 2026) formalizes this; we adopt the lifecycle.

**Storage-of-record rule** (resolves the three-way ambiguity between `sources`, `procedures`, and `skills_index`):

| Layer | Role | Populated by |
|---|---|---|
| `sources` (kind='pattern') + `memory_classifications.bucket='procedural'` | Narrative body + bucket membership. Required for every procedure. | App-layer write trigger when `procedures` row inserted — bucket row is **derived**, not authored separately. |
| `procedures` table | **Canonical lifecycle state** — counters, granularity, deprecation. The source of truth for "is this procedure usable, has it worked, when last applied." | `propose_skill`, `distill_pattern`, user-authored imports, file-watcher (Obsidian-side procedure notes). |
| `skills_index` (on-disk SKILL.md mirror) | Cross-tool portability. Only written when a procedure is promoted to a SKILL.md for agents that don't speak SQL. | Explicit user/agent action: `brain procedure promote-to-skill <id>`. Not automatic. |

Invariant: every `procedures.id` has exactly one `sources.id` (FK), and that `sources` row has exactly one `memory_classifications(bucket='procedural')` row. `skills_index` rows are optional and explicit. Querying "all active procedures" goes through `procedures WHERE deprecated_at IS NULL` — never through `memory_classifications.bucket='procedural'` alone (which would miss the lifecycle state).

```sql
CREATE TABLE procedures (
  id                 BIGSERIAL PRIMARY KEY,
  source_id          BIGINT NOT NULL REFERENCES sources(id),  -- narrative body
  title              TEXT NOT NULL,
  target_situation   TEXT NOT NULL,            -- "Postgres install on Arch", "FastAPI dep injection cycle"
  granularity        TEXT NOT NULL CHECK (granularity IN ('step','script')),
                                                -- step = human-readable step list
                                                -- script = executable / structured automation
  build_method       TEXT NOT NULL CHECK (build_method IN
                       ('distilled_from_episodes','user_authored','imported','llm_proposed')),
  built_from         BIGINT[],                  -- episode/subtask ids if distilled
  success_count      INT NOT NULL DEFAULT 0,
  failure_count      INT NOT NULL DEFAULT 0,
  last_applied_at    TIMESTAMPTZ,
  last_outcome       TEXT CHECK (last_outcome IN ('success','failure','partial','unknown')),
  deprecated_at      TIMESTAMPTZ,               -- NULL = active. Set when superseded.
  superseded_by      BIGINT REFERENCES procedures(id),
  project_id         BIGINT REFERENCES projects(id),
  t_valid_from       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  t_valid_to         TIMESTAMPTZ,
  -- One active step + one active script per situation. NULL deprecated_at means active;
  -- Postgres treats NULLs as distinct in a normal UNIQUE, so we use a partial index instead.
  -- (The historical (target_situation, granularity) tuple may recur over time as deprecated rows accumulate.)
  CONSTRAINT procedures_no_self_supersede CHECK (superseded_by IS NULL OR superseded_by != id)
);
CREATE UNIQUE INDEX procedures_active_unique_idx
  ON procedures (target_situation, granularity) WHERE deprecated_at IS NULL;
CREATE INDEX procedures_active_idx ON procedures(target_situation) WHERE deprecated_at IS NULL;
CREATE INDEX procedures_outcome_idx ON procedures(last_outcome, last_applied_at DESC);
```

**Dual-granularity rule (Memp result that transfers across models):** for each `target_situation`, the brain may store one `granularity='step'` (human/agent-readable steps) AND one `granularity='script'` (executable abstraction). Stronger models build procedures; weaker models apply them. Both forms cohabit; retrieval picks based on the caller's capability.

**Procedure update workflow** (run by the agent after each application):
1. Apply procedure → record outcome via `events.kind='reflection'` linking to `procedure_id`.
2. Increment `success_count` or `failure_count`.
3. Update `last_applied_at`, `last_outcome`.
4. If `failure_count > 0.5 * (success_count + failure_count)` AND total applications ≥ 5 → flag for review (deprecation candidate).
5. If a newer procedure proposed for the same `target_situation` accumulates better outcome stats → manual or human-gated `deprecated_at = NOW()`, `superseded_by = new_id`.

**Retrieval rule:** procedures with `deprecated_at IS NOT NULL` are never returned to the agent for application. They remain queryable for history/audit (`brain-health` shows deprecation rate per project).

### Compaction-survival bundles (the headline feature)

The single most important mechanism in the brain. When Claude Code is about to compact a conversation, or when a session ends, the brain produces a deterministic bundle that captures everything an agent would need to resume — and stores it for the next session to read.

```sql
CREATE TABLE session_resume_bundles (
  id            BIGSERIAL PRIMARY KEY,
  project_id    BIGINT NOT NULL REFERENCES projects(id),
  session_id    BIGINT REFERENCES sessions(id),    -- the session this bundle summarizes
  trigger       TEXT NOT NULL CHECK (trigger IN ('pre_compact','session_end','manual')),
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  superseded_at TIMESTAMPTZ,                       -- when a newer bundle replaced this
  token_budget  INT NOT NULL,                      -- target size at generation time
  manifest      JSONB NOT NULL,                    -- structured: see below
  rendered      TEXT NOT NULL                      -- ready-to-paste markdown brief
);
-- Partial UNIQUE enforces "one active bundle per project" (the spec's stated invariant).
-- The trigger that creates a new bundle sets superseded_at on any prior active row in the
-- same transaction.
CREATE UNIQUE INDEX bundles_project_active_unique_idx ON session_resume_bundles(project_id)
  WHERE superseded_at IS NULL;
CREATE INDEX bundles_project_idx ON session_resume_bundles(project_id, generated_at DESC);
```

**Manifest schema:**

```json
{
  "active_subtask": { "id": 123, "title": "...", "goal": "...", "open_threads": [...] },
  "recent_decisions": [{ "source_id": 456, "summary": "...", "rationale": "...", "weight": 0.9 }],
  "recent_failures": [{ "failure_id": 78, "target": "...", "lesson": "...", "weight": 0.7 }],
  "recent_files_touched": ["path/a.py", "path/b.sh"],
  "recent_commands_succeeded": ["bash tests/run-all.sh", "psql -c '\\dt'"],
  "recent_commands_failed": [{ "cmd": "docker compose up", "exit": 1, "tail": "..." }],
  "relevant_knowledge": [{ "source_id": 901, "title": "...", "weight": 0.5 }],
  "open_questions": ["should we install pgvector via apt or build from source?"]
}
```

**Selection algorithm (deterministic, in order):**

1. **Active subtask** — the `subtasks` row for this session with `ended_at IS NULL`, plus its goal and any events with `kind='blocker'` whose resolution is missing.
2. **Recent decisions** — last 10 `events.kind='decision'` rows in this session, ordered by recency, then deduplicated against the project's promoted-to-`semantic` decisions to avoid repeating durable facts.
3. **Recent failures** — `failure_memories` with `last_attempted_at` in this session OR `target_problem` matching any active subtask goal (fuzzy). Cap 5.
4. **Files / commands** — last 20 `events.kind='tool_call'` rows, partitioned by `status='ok'` vs `status!='ok'`.
5. **Relevant knowledge** — top-5 hits from `retrieval_log` in this session, weighted by `selected` count (if known).
6. **Open questions** — `events.kind='reflection'` rows ending in `?` or carrying frontmatter flag `open_question: true`, this session, unresolved.

**Token budget enforcement (default 500 tokens):**

Each category gets a soft allocation:
- active_subtask: 100 tok
- recent_decisions: 120 tok
- recent_failures: 80 tok
- files/commands: 60 tok
- relevant_knowledge: 80 tok
- open_questions: 60 tok

If a category exceeds its allocation, items are dropped in reverse selection order (lowest weight first). Total enforced via `tokens` accumulator. If total > budget after all categories, render with `[truncated]` marker and a "see full bundle: brain bundle show <id>" pointer.

**Lifecycle:**

- `PreCompact` hook (Claude Code) generates a bundle with `trigger='pre_compact'` and **persists it** to `session_resume_bundles`. PreCompact's stdout is NOT a documented context-injection channel; rendering the bundle into the agent's next message happens via the `SessionStart` hook's `hookSpecificOutput.additionalContext` field (or via the `UserPromptSubmit` hook for mid-session re-injection if needed). PreCompact's job is *persistence*, not *delivery*.
- `SessionEnd` hook generates a `trigger='session_end'` bundle; this is what `SessionStart` consumes next session. (NOT `Stop` — `Stop` fires per-turn, which would generate a bundle on every agent response.)
- `SessionStart` reads the most recent un-superseded bundle for the active project (via `bundles_project_active_idx`). If `generated_at` is > 14 days old, it regenerates rather than using the stale one.
- Manual: `brain bundle generate --project <slug>` for testing or before a planned context wipe.

**Retention:**

- Active bundles (one per project, `superseded_at IS NULL`) — keep forever.
- Superseded bundles — kept 30 days for retrospective inspection, then archived (manifest preserved, rendered text discarded).
- `brain health` reports oldest-active-bundle age; bundles >14 days old in active projects are flagged.

**Compliance assertion:** if a session contains <3 captured events when `Stop` fires, the bundle generator emits a warning into the rendered bundle: `⚠ Session under-captured (N events). Resume context is partial.` This is the enforcement teeth for §Compliance (see below).

### Anthropic Skills (procedural memory mirror)

Procedural memory lives in TWO forms: rows in `sources` (queryable from SQL) and on-disk skills in the existing `skills/` directory (loadable by agents). The brain keeps them in sync.

```sql
CREATE TABLE skills_index (
  source_id    BIGINT PRIMARY KEY REFERENCES sources(id),
  skill_name   TEXT NOT NULL UNIQUE,
  description  TEXT NOT NULL,
  triggers     TEXT[],                  -- when-to-use phrases
  file_path    TEXT NOT NULL,           -- relative path to SKILL.md
  installed_in TEXT[],                   -- 'claude-code'|'codex'|'cursor'|…
  version      TEXT
);
```

## Capture mechanism

Three paths, all converging at `brain.write(...)`:

### Path 1: agent-proactive (mandatory)

The agent must capture as it works. Discipline rule added to `_meta/AGENTS.md` and the cross-agent contract: **between substantive subtasks, capture**. Specific moments:

| Moment | What to capture |
|---|---|
| Start of subtask | `subtasks` row with goal |
| After non-trivial tool call | `events` row (hook may do this automatically; agent ensures semantic context) |
| Decision made | `events.kind='decision'` + a `sources.kind='decision'` body |
| Hypothesis formed | `events.kind='reflection'` |
| Failure / dead end | `events.kind='blocker'` + classify the source as `bucket='failure'` |
| End of subtask | mark `outcome`, write a 2-sentence summary as `sources.kind='subtask_summary'` |
| End of session | full session summary via reasoning helper, store in `sessions.summary_id` |

### Path 2: Claude Code hooks

Configured in `~/.claude/settings.json` (user installs once). Hooks call a Python helper that writes rows.

| Hook | Action |
|---|---|
| `PostToolUse` | Insert `events` row + truncated output into `sources` (under `kind='tool_call_output'`). Bash output capture: **head + tail + error-span preservation**. Default: 4KB head + 4KB tail, PLUS any lines matching `(FAIL|ERROR|panic|trace|exception|Traceback)` from anywhere in the middle (capped at 4KB additional). Each retained span is delimited; truncation gap shows `[N lines elided]`. Truncation metadata stored on `sources.flags`. Configurable via `brain_config.tool_output_cap`. |
| `PreCompact` | Generate a `session_resume_bundle` snapshotting current state before the compactor runs. |
| `SessionStart` | If a resume bundle exists for the active project, agent should consult it. |
| `Stop` | Fires **per-turn** when Claude finishes responding (NOT per-session). Used for: incremental capture-completeness check (count events written during this turn), flush of any pending per-turn buffer, refresh of working-state pointer. **Does NOT set `sessions.ended_at` and does NOT generate `trigger='session_end'` bundles** — that would fire on every turn. |
| `SessionEnd` | The true end-of-session hook (fires when the conversation actually terminates). Sets `sessions.ended_at`, generates a `trigger='session_end'` resume bundle, classifies the session into memory buckets, runs the §Compliance capture-completeness check. |
| `SubagentStop` | Mark subtask outcome if subagent was running a subtask. |

The hooks are installed by the setup skill (opt-in, gated on user approval) and edit `~/.claude/settings.json` carefully.

Cross-platform: Codex CLI v0.128+ has analogous lifecycle events; an adapter layer ships in Phase 4. Cursor and Gemini lack equivalent hooks today.

**Non-Claude user experience in Phase 1–2:**

Cursor / Gemini / Aider users don't get hook-driven capture. Their workflow during Phase 1–2:

1. At session start, manually run `brain resume <project>` in the terminal; paste the rendered bundle into the agent's chat.
2. During the session, the agent uses Path 1 (proactive captures via the `brain` CLI) — the AGENTS.md contract directs them to do so explicitly.
3. At session end, manually run `brain session end` to trigger summary + bundle generation.

This is degraded vs Claude Code's automatic flow, and the spec is explicit about it. Phase 4's MCP server closes the gap by exposing brain operations as MCP tools that those agents can call as if they were native.

### Path 3: user-explicit

Two surfaces:

- CLI: `brain remember "<text>"`, `brain link <slug> <slug>`, `brain invalidate <id>`.
- Obsidian: user edits a markdown file directly; a file-watcher Python helper detects the change, re-ingests, and updates rows. (Obsidian write → markdown is the source of one ingestion path; the canonical Postgres row is updated.)

## Compliance (enforcement of "the agent must comply")

v1's enforcement was implicit hope. v2 adds three teeth:

1. **`SessionEnd` hook capture-completeness check.** When the session actually ends (not per-turn), count `events` and `subtask_summary` rows written across the whole session. If the session had ≥ 5 Claude turns (detectable from session transcript metadata) AND < 3 capture events, the bundle generator marks the session under-captured. `brain health` surfaces under-captured sessions in its report. (`Stop` may also emit a lightweight per-turn capture-count signal to the same counter, but the threshold check fires at `SessionEnd`.)
2. **Bundle-generator quality signal.** A session that produces a near-empty bundle (no active subtask, no decisions, no failures) is auto-flagged in `sessions.summary_id` as a "thin session." Repeated thin sessions for the same project trigger a `brain status` warning recommending review.
3. **Optional strict mode.** Users opt in via `brain_config.key = 'strict_mode' value = 'true'`. When strict, the `SessionEnd` hook returns a non-zero exit if the session is under-captured, surfacing a system-reminder visible to the next session. This is opt-in because false positives during exploratory or one-shot work would create friction.

Compliance is observability + nudges, not a hard block. The brain cannot literally compel an LLM to capture; it can make non-capture visible, persistent, and uncomfortable.

## Memory taxonomy (LangMem canonical)

| Bucket | What goes here | Lifetime |
|---|---|---|
| **semantic** | Facts about the world / domain / codebase / APIs / glossary | Long-lived; promoted via curation |
| **episodic** | Sessions, subtasks, events, tool calls, observations | All retained (compaction operates by relevance + recency, not delete) |
| **procedural** | Skills, recipes, heuristics, "when X, try Y first" | Long-lived; updated as evidence accumulates |
| **failure** | "Tried X for purpose P, failed because Y, learned Z" | Long-lived; critical for "don't do this again" |

The router (in capture path) classifies each new source. The classifier is the existing `agent-store-decide` skill, extended with the new `failure` type.

## Retrieval

**Stack (locked in by prior research, refined by FP/FN research):**

1. **Metadata pre-filter** — every retrieval first narrows the candidate set with this contract:

   ```sql
   WHERE s.t_valid_to IS NULL                              -- bi-temporal: still current
     AND s.status = 'active'                                -- visibility filter
     AND (
           $project_id IS NULL                              -- caller didn't scope
        OR s.project_id = $project_id                       -- primary project match
        OR EXISTS (SELECT 1 FROM source_projects sp        -- or M2M membership
                   WHERE sp.source_id = s.id AND sp.project_id = $project_id)
         )
     AND (
           $buckets IS NULL
        OR EXISTS (SELECT 1 FROM memory_classifications mc
                   WHERE mc.source_id = s.id AND mc.bucket = ANY($buckets))
         )
     AND ($kinds IS NULL OR s.kind = ANY($kinds))
   ```

   `$project_id` / `$buckets` / `$kinds` come from `obsidian-recall` invocation context (current active project, requested buckets, optional kind filter). Sources with `status='archived'` are hidden by default; pass `--include-archived` to include them.
2. **Hybrid candidate generation, parallel:**
   - Postgres FTS (BM25-like via `ts_rank_cd`) over `sources_fts.tsv`. k=100.
   - pgvector kNN over `embeddings_1024.vec` with HNSW. k=100. **Always** filtered by `model_id = $active AND model_ver = $active_ver` (read from `brain_config`) — never compare across embedding models.
3. **Reciprocal Rank Fusion (RRF)** to fuse the two lists. One-line algorithm, no score normalization needed.
4. **Cross-encoder rerank** of top 30–50 candidates. mxbai-rerank-large-v2 as default (local model). Cohere Rerank or ColBERT plug-in as alternatives.
5. **Return top 5–10** with provenance (source URI, span, score).

**SLO tiers** — not every recall pays the same cost:

| Tier | Pipeline | Target latency | Used by |
|---|---|---|---|
| Fast (default) | metadata + FTS + dense + RRF + rerank | p99 < 500ms | inline agent calls (`brain.recall` from a skill) |
| Deep | + multi-query fusion + CRAG verification gate | p99 < 3s | explicit `brain.recall --deep`, bundle generation, research queries |
| Bulk | + decomposition + iterative retrieve | p99 < 15s | `brain.research`, hand-off generation |

Success criterion #7 ("skill loop unchanged in latency vs v1 bash-only") applies to the Fast tier only. Deep and Bulk tiers have separate budgets and are opt-in per call.

**Embedding-model swap protocol.** Changing `brain_config.active_embedding_model_*` is a deliberate operation:

1. New rows go into `embeddings_<dim>` with the new `(model_id, model_ver)`.
2. Existing rows are re-embedded in batches by a background job (`brain reindex --to <model>`).
3. Until reindex completes, retrieval reads the OLD active model. The config flip happens only when 100% of currently-valid sources have an embedding under the new model. `brain status` shows progress.
4. Old-model embeddings are kept until explicit cleanup (`brain reindex --gc-old`), so a rollback is one config flip away.

**FP/FN-specific hardening:** see §Retrieval hardening below.

### Retrieval hardening (FP/FN minimization)

The locked-in 2026 stack, chosen against documented failure modes. Each layer eliminates a specific class of FP or FN.

#### Embedding model

**BGE-M3** (Apache-2.0, local). Reasons:
- Single model emits dense + sparse + ColBERT-style multi-vector in one forward pass — replaces three separate models we'd otherwise run.
- 100+ languages, 8192-token context (matches long agent-memory notes).
- Self-hostable on the user's GPU; matches commercial-API quality for retrieval.
- ColBERT vectors available for Phase 3 rerank without re-embedding.

Phase 1 uses dense vectors only (matches our HNSW schema). Phase 3 enables the sparse + multi-vector legs.

Fallback configs (via `embeddings.model_id`):
- `mxbai-embed-large-v1` — lower VRAM footprint
- `voyage-3-large` (cloud, paid) — when retrieval quality dominates cost
- `qwen3-embedding-8b` — best MTEB-Code score (80.68); use if code-heavy retrieval underperforms

#### Chunking

**Parent-document retrieval** (the 2026 default):
- Split each source into 128–256-token **child chunks**. Embed children.
- Maintain `parent_id` linking each chunk to its 512–1024-token parent context.
- At retrieval time: vector/FTS searches over children; we return the **parent** to the agent for reading.
- Eliminates boundary-cut FNs (the Q/A separated across 512-token splits problem).

For agent-memory notes specifically (often pronoun- or header-dependent), use **late chunking**:
- Run the embedding model over the full 8k-token note first, get token-level embeddings, then split into chunks. Chunks inherit document-wide context.
- This is BGE-M3 specifically — the model supports it out-of-box.

#### Contextual Retrieval (Anthropic, Sep 2024)

For every chunk at ingest, generate a **chunk-context summary** (1–3 sentences placing the chunk in its document) via Claude Haiku. Prepend the summary to the chunk before embedding.

- Empirical: 49% reduction in retrieval failures with FTS, 67% with FTS + reranker (Anthropic, Sep 2024 blog post, on Anthropic's own evaluation corpus). Independent 2025–26 replications confirm the direction; effect size varies by domain. We re-measure on our hand-curated eval set in §Eval rather than assuming the headline numbers transfer to coding-agent memory.
- Cost: ~$1.02 per 1M doc tokens with prompt caching. Negligible at personal-corpus scale.
- Adoption: this is the highest-ROI single intervention in the field. Day-1 commitment in Phase 2.

Implementation: `brain.ingest()` runs the contextualization step before writing the embedding row. The summary is also stored in `sources` as a separate row (`kind='chunk_context'`, `parent_id` pointing at the chunk) for transparency and re-use.

#### Hybrid candidate generation

Parallel, top-100 each:

```
                  ┌──────────────────────────────────────────┐
query             │ Postgres FTS  (BM25-like, ts_rank_cd)    │ → 100
  │ ┌─────────────┤   on sources_fts.tsv, GIN-indexed         │
  ├─┤                                                          │
  │ │  ┌──────────────────────────────────────────────────────┤
  │ └──┤ pgvector kNN  (cosine, HNSW, halfvec, BGE-M3 dense)  │ → 100
  │    └──────────────────────────────────────────────────────┘
  │
  └─→ Metadata pre-filter applied first to both:
        WHERE project_id = ? AND t_valid_to IS NULL
              AND bucket IN (?) AND status != 'archived'
```

#### Fusion: Reciprocal Rank Fusion (RRF)

Standard formula: for each doc, `score = Σᵢ 1/(k + rank_i)` across the two retrievers, k=60. One-line implementation. No score normalization needed.

#### Reranking

**mxbai-rerank-large-v2** (Apache-2.0, local). 57.49 BEIR, runs on the same GPU as BGE-M3. Reranks top 30–50 candidates from RRF.

Swappable via config:
- `cohere-rerank-v4` (zero-ops, paid)
- `jina-reranker-v3` (188ms, 131k context — for long-context bundles)
- `bge-reranker-v2-m3` (lightweight baseline)

#### Query expansion (recall hardening, FN)

For ambiguous or recall-critical queries (auto-detected by query characteristics, or explicit `--expand` flag):

1. **Multi-query fusion** (RAG-Fusion / MQRF-RAG): LLM generates 3–5 query variants. Each goes through the hybrid stack. RRF-fuse the K result lists.
   - Best single FN-reducer in 2026 benchmarks (+1.5 EM, +3.75 F1 on AmbigQA).
2. **Self-Query** (LangChain): LLM extracts structured filters from query text (date ranges, project, type). Filters applied as metadata pre-filter; remainder embedded.
   - Non-optional for an agent brain — most queries imply "in this project" or "recent."
3. **HyDE** (Hypothetical Document Embeddings): only when query is keyword-poor AND BM25 leg returned <5 hits. Skip on factoid queries (LLM hallucinates wrong docs).
4. **Query decomposition** (LLM splits multi-hop into sub-queries): only triggered when query is detectably multi-hop ("compare X and Y in context Z"). Iterative retrieve per sub-query, then synthesize.

#### Verification (precision hardening, FP)

**CRAG (Corrective RAG)** as a conditional gate (NOT on the Fast-tier path):
- LLM-as-judge scores each top-K candidate's relevance to the query.
- 3-way verdict: ≥0.7 keep, ≤0.3 discard, else "merge" (combine with another candidate or expand search).
- Cost: +100–800ms latency, one Claude Haiku call.
- **Trigger conditions** (avoid blanket application — see §Retrieval SLO tiers):
  1. Reranker top-1 score is in [0.5, 0.7) — confidence-band where verification helps most.
  2. Caller explicitly requested `--deep` tier.
  3. Query is in the `failure_memory` bucket (false negatives are especially costly there — see #4 success criterion).
- Implementation: `reasoning.verify(query, candidates)` runs as the last retrieval stage when triggered.

**Confidence threshold + abstain (per-bucket τ)**:

Default thresholds at which the reranker's top-1 score causes the system to return "no high-confidence match":

| Bucket | Default τ | Reason |
|---|---|---|
| `semantic` (curated facts) | 0.75 | High precision required; a wrong fact misleads more than no fact |
| `episodic` (sessions, events) | 0.65 | Relevance is fuzzier; near-matches still useful for "show me what I was doing" |
| `procedural` (recipes, skills) | 0.70 | Recipe misapplication is moderately costly |
| `failure` (don't-do-this-again) | 0.55 | LOW intentionally — near-matches are the point ("you tried something kind of like this") |

**τ-tuning protocol.** Initial values come from sweeping the hand-curated eval set (see §Eval) and picking the precision/recall knee per bucket. Re-tuning is triggered when `retrieval_log` shows the retrieved-vs-used ratio drops below 40% over 100 queries in a bucket (suggesting τ is too low — too many irrelevant results), or above 90% with frequent "no result" returns (suggesting τ is too high — abstaining when matches exist). `brain health` reports the rolling ratio per bucket.

Abstain beats wrong is the policy, but failure memory specifically benefits from low τ — surfacing near-misses ("you tried something similar 2 weeks ago, here's the lesson") is the point.

**FP-target tuning for auto-mutation passes (ClueBot NG framing).** READ thresholds and WRITE/MUTATE thresholds are different problems. For passes that mutate the brain (auto-deprecate procedures, link-back rewrites by `revise_on_ingest`, contradiction surfacing by `brain-health`), calibrate against a **target false-positive rate**, not accuracy. Default targets:

| Auto-mutation pass | Target FP rate | Reasoning |
|---|---|---|
| `revise_on_ingest` link-back rewrites (semantic bucket) | ≤ 5% | Human-gated; FP just adds review burden |
| `revise_on_ingest` link-back rewrites (episodic/failure) | ≤ 10% | Unattended; minor drift acceptable |
| Auto-deprecate procedures (success/failure ratio) | ≤ 2% | Deprecation is sticky; FP loses real knowledge |
| Contradiction prompts to user (`brain-health` NLI pass) | ≤ 1 prompt/week false positive | Nuisance prompts erode user trust |
| Auto-invalidate stale `active` claims | ≤ 5% | Bi-temporal preserves history; cost is recall noise |

Calibration set: hand-labeled subset of `retrieval_log` + paired NLI labels. Re-calibrate per release. **Mutations of `provenance_kind='captured'` rows require strictly higher confidence than mutations of `'synthesized'` rows** — captured content is ground truth; synthesized content is conjecture.

#### Synthesized-content retrieval down-weight (brain-rot defense)

The Oct-2025 LLM brain-rot study (recursive training on junk → irreversible representational drift) applies to retrieval too. As `brain-promote-answer` and `revise_on_ingest` add `provenance_kind='synthesized'` rows, the corpus accumulates LLM-derived content alongside captured content. Without a counterweight, semantic search increasingly surfaces synthesis-of-synthesis rather than ground truth.

**Down-weight rule.** At RRF fusion time, multiply the rank score of `provenance_kind='synthesized'` rows by a recency-aware factor:

```
weight(row) = 1.0                                  if provenance_kind = 'captured' or 'ingested'
            = 0.7 * (1.0 / (1 + generation_depth)) if provenance_kind = 'synthesized'
```

`generation_depth` is recursive: a synthesized row built only from captured rows has depth 1; a synthesized row that includes another synthesized row in `synthesized_from` has depth 2; and so on. Computed at write time by `brain.write()`, stored as a column on `sources` (see §Schema). Hard cap at depth 3 — `brain.write()` rejects writes that would produce depth > 3 (caller must consolidate inputs first).

**Worked example.** A synthesized row built from captured sources → depth=1 → weight = `0.7 × 1/2 = 0.35`. A synthesized-from-synthesized row → depth=2 → weight = `0.7 × 1/3 = 0.23`. Depth=3 → weight = `0.7 × 1/4 = 0.175`. Depth≥4 → rejected at write. So the effective cap on synthesized-row influence is **0.35** in best case, dropping fast.

**Stale-provenance flag.** If any source in a synthesized row's `synthesized_from` is later invalidated (via `revise_on_ingest` or otherwise), the synthesized row is auto-flagged via `sources.flags = {'stale_provenance': true, 'invalidated_inputs': [ids]}`. The down-weight formula additionally multiplies by 0.5 when `stale_provenance` is true. The synthesized row is not auto-invalidated — re-grounding is `revise_on_ingest`'s job, run on the next ingest that touches the topic.

**Result-set diversity cap.** If a candidate result set contains > 60% synthesized rows, the retriever automatically expands the candidate pool to surface more captured content. This is what prevents the "the brain only finds its own prior thoughts" failure mode.

#### Provenance and consolidation tracking

Every retrieval call writes a row to `retrieval_log`:

```sql
CREATE TABLE retrieval_log (
  id          BIGSERIAL PRIMARY KEY,
  query       TEXT NOT NULL,
  filters     JSONB,
  candidates  JSONB,             -- top-K with scores per stage; each entry includes source_id + provenance_kind
  selected    BIGINT[],          -- which source_ids the agent actually used (filled in post-hoc)
  -- Derived metrics, populated at recall time when result set is finalized.
  -- Cheap to compute (no join needed at aggregation time, just SELECT AVG(...)).
  synthesized_ratio REAL,        -- fraction of result-set rows with provenance_kind='synthesized'
  captured_ratio    REAL,        -- fraction with provenance_kind IN ('captured','ingested','user_authored')
  abstained         BOOLEAN NOT NULL DEFAULT FALSE,
  top1_score        REAL,        -- reranker's top-1 score (for τ-tuning)
  agent       TEXT,
  session_id  BIGINT REFERENCES sessions(id),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX retrieval_log_session_idx ON retrieval_log(session_id, occurred_at);
```

This lets us detect:
- **Context consolidation failures** — retrieved-but-not-used (40% of RAG quality is here, per 2026 production writeups).
- **Recurrent recall misses** — same query, low scores, agent abandoned retrieval.
- **Hard negatives** for future fine-tuning (Phase 4).

#### Sanitization at ingest (poisoned-doc defense — Phase 2 minimum, Phase 4 hardening)

Agent memory is a write-anything surface. The threat is real: a malicious file in a mapped repo, a `curl` output with injected instructions, a tool output containing "ignore previous instructions and …". The full threat model (referenced as `docs/security/threat-model.md`, written in Phase 4) is out of scope for v2.0; the Phase 2 minimum is documented here and explicitly limited.

**Phase 2 minimum (specific, implementable):**

1. **ANSI escape and control-character stripping** on `tool_call` and `command` content via `re.sub(r'\x1b\[[\d;]*[a-zA-Z]', '', text)` plus a non-printable-character filter. These break renders and have no value in stored content.
2. **Instruction-density flagging** — a heuristic detector that counts occurrences of suspicious phrases (`ignore previous instructions`, `you are now`, `system:`, `disregard`, `new instructions`) per 1000 chars. If density exceeds 1.0, set `sources.flags = {'suspicious': true, 'reason': 'instruction_density', 'score': X}`.
3. **Origin-aware quoting** — content from `kind IN ('tool_call', 'command', 'web_page')` is wrapped at retrieval time with a delimiter (`<tool-output>...</tool-output>`) so the consuming LLM treats it as data, not instructions. This is a render-time defense layered on the storage; both layers matter.
4. **No rejection — only flagging.** Suspicious content still ingests. The agent sees the flag in retrieval results and can decide whether to trust it.

Phase 4 adds: structural anomaly detection, embedding-time prompt-injection detection (Lakera-style), per-source provenance trust scores, optional opt-in rejection mode. v2.0 explicitly does not claim defense against motivated prompt-injection — only against accidental ingestion of obviously instruction-shaped text.

#### What we adopt vs. defer

| Technique | Phase | Reason |
|---|---|---|
| Postgres FTS | 1 | Always free, never lossy, ships day 1 |
| Metadata pre-filter | 1 | Already needed for project/validity filtering |
| BGE-M3 dense + HNSW + halfvec | 2 | First semantic capability |
| RRF | 2 | One-line, free quality |
| Parent-document retrieval | 2 | Standard chunking, eliminates boundary FN |
| Contextual Retrieval (chunk context prepend) | 2 | Highest-ROI intervention |
| mxbai-rerank-large-v2 | 2 | Standard reranker |
| Multi-query fusion | 3 | LLM-cost gated; ship after corpus is real |
| Self-Query (structured filter extraction) | 3 | Needs query log to tune |
| CRAG verification gate | 3 | LLM cost per query; opt-in via flag first |
| Late chunking | 3 | Specific to agent-memory notes |
| BGE-M3 sparse + ColBERT legs | 3 | Triple-leg fusion + multi-vector rerank |
| HyDE | 4 | Only when known to help on logs |
| Query decomposition | 4 | Multi-hop is later |
| Fine-tuning + hard-negative mining | 4 | Premature until query log exists |

#### Eval

- **Hand-curated 50–100-question eval set** against this very repo's content (the brain about the brain). Captures real query patterns from session transcripts.
- **LongMemEval-V2** (arxiv 2605.12493, real web-agent trajectories, the V1 successor) + **MemoryAgentBench** (ICLR 2026, explicit "session N+1 uses session N" protocol) + **BEAM** for long-context. The MemoryAgentBench protocol *is* our compounding metric — we don't need to invent one.
- Track precision/recall@k, MRR, abstain rate, **retrieved-vs-used ratio** from `retrieval_log`, and **synthesized:captured ratio** per result set (brain-rot guard).
- Threshold τ is swept on the hand-curated set; pick the precision/recall knee.

**Compounding regression test (the only honest answer to "is the brain working").** Weekly automated job. Replay semantics: we re-run *queries*, not tool calls — the `retrieval_log` table is the replay source, not `events`.

1. `SELECT * FROM retrieval_log WHERE occurred_at > NOW() - INTERVAL '7 days' AND cardinality(selected) > 0`, grouped by `session_id`. Each row is a query the agent issued whose result it actually used.
2. For each, re-issue the same `query` + `filters` against the **current** brain state.
3. Score:
   - **Recall@K stability:** did each row in the original `selected` list rank as high or higher in the new result?
   - **Surfacing delta:** did any NEW sources (not in the original `candidates`) surface that would have answered the question? (A "now I know it" hit — captured by `brain-promote-answer` or `revise_on_ingest` since the original query.)
   - **Abstain delta:** queries that originally returned a low-confidence result and now surface a high-confidence answer.
4. Aggregate per week: mean Recall@K stability, count of surfacing deltas, count of abstain deltas, mean `synthesized_ratio` trend.
5. A brain that's actually compounding shows: stable-or-improving Recall@K, positive surfacing-delta count, decreasing abstain rate, **stable synthesized:captured ratio** (no brain-rot trend).

If the trend is flat or negative for 4 weeks running, OR synthesized:captured ratio breaches 60% sustained, the brain is rotting/sprawling without consolidation — `brain-health` escalates with `--lint` recommendations.

## Reasoning helpers (higher-order operations)

These are what makes the brain a cognition substrate, not a notes app. Each is a Python function exposed both as a CLI subcommand and as a skill. All operate over **structured retrieval results**, never against blind queries — that's what makes them higher-order rather than LLM-wrapped grep.

Organized by what kind of thinking they support. Operations compose: `plan_research` calls `decompose_question` calls `brain.recall` calls `synthesize_thesis` calls `identify_unknowns`. The brain orchestrates the cascade.

### Category A — Synthesis (multi-source → unified understanding)

| Helper | Input | Output | LLM |
|---|---|---|---|
| `summarize(source_ids[])` | sources | ≤500-token brief, every claim cited | yes |
| `synthesize_thesis(sources, hypothesis)` | sources + claim text | `{verdict, evidence[], counter_evidence[], confidence}` | yes |
| `extract_consensus(sources)` | sources | claims all sources agree on, with per-source citation | yes |
| `extract_disagreement(sources)` | sources | `[{claim_a, claim_b, axis, source_a_span, source_b_span}]` — axis ∈ scope/time/mechanism/evidence | yes |
| `compare(a_id, b_id)` | two sources | side-by-side: agreements / disagreements / scope diff | yes |
| `contrast(query, candidate_ids[])` | question + candidates | which best answers, why others miss | yes |
| `revise_on_ingest(new_source_id)` | a newly-ingested source | list of affected existing pages, with revision summaries + contradiction flags. **Implements the A-MEM "writes are mutations, not appends" pattern**: on ingest, retrieve top-k semantically neighboring sources, propose updates. **What it rewrites:** `extracted_claims` (invalidate-and-reassert via bi-temporal) and `edges` (link-back). **What it never touches:** `sources.content` — the canonical body store is append-only via the re-assertion semantics; only structured derivations change. This keeps the markdown view stable (no per-ingest body churn) while keeping the structured layer current. Human-gated for `bucket=semantic` claim revisions. | yes |

### Category B — Causal reasoning (trace mechanism through episodic chain)

| Helper | Input | Output | LLM |
|---|---|---|---|
| `trace_causality(event_id, hops=5)` | an event | event chain backward from here: what precursors led to this | partial (chain assembly is SQL; narration is LLM) |
| `trace_consequences(event_id, hops=5)` | an event | event chain forward: what followed | partial |
| `attribute_failure(failure_id)` | a failure_memories row | root-cause hypothesis + supporting event spans | yes (over deterministic event chain) |
| `explain_outcome(subtask_id)` | a subtask | why it succeeded / failed, with cited events + failures + decisions | yes |
| `entity_timeline(entity_id, from?, to?)` | an entity + optional date range | chronological list of every event, decision, failure, and source referencing this entity, with span citations | no (pure SQL over `events` + `edges`) |

`entity_timeline` answers questions like "show me everything I did to the auth module last week" or "every decision and failure connected to pgvector in this project." It's a SQL-only helper (no LLM), driven by the `entities` + `edges` + `events` schema already in spec. Output is structured `[{occurred_at, kind, source_id, summary, role}]` ordered by time — the caller decides whether to feed it to `summarize` for a narrative or render directly as a timeline view.

### Category C — Abstraction (specific → general)

| Helper | Input | Output | LLM |
|---|---|---|---|
| `distill_pattern(subtask_ids[])` | N similar subtasks | candidate procedural recipe (Anthropic Skills format), with provenance to source subtasks | yes |
| `generalize_failure(failure_id)` | a single failure | class-of-failures rule + scope conditions | yes |
| `extract_invariants(sources)` | sources | what's true across all of these — surfaces latent assumptions | yes |

### Category D — Decomposition (fuzzy → answerable)

| Helper | Input | Output | LLM |
|---|---|---|---|
| `decompose_question(query)` | fuzzy query | atomic sub-queries the recall layer can answer | yes |
| `plan_research(topic, depth=2)` | topic | ordered structured plan: what to read, run, measure, in what order | yes (composes other helpers) |
| `identify_unknowns(claim)` | a claim | what would need to be true for this to hold — surfaces hidden assumptions | yes |

### Category E — Counterfactual

| Helper | Input | Output | LLM |
|---|---|---|---|
| `counterfactual(event_id, alternative_action)` | an event + a hypothetical alternative | predicted downstream change, using prior episodes as analogs | yes |
| `predict_outcome(plan_text)` | a plan | likely outcome + confidence + per-step risk, drawn from failure_memories + procedural recipes | yes |

### Category F — Meta-cognitive (brain reasoning about itself)

| Helper | Input | Output | LLM |
|---|---|---|---|
| `find_contradictions(scope)` | a scope (project / bucket / time window) | pairs of claims that conflict, with axes — semantic conflicts beyond bi-temporal | yes |
| `identify_gaps(corpus)` | the corpus | under-represented topics relative to active projects | yes |
| `assess_confidence(claim)` | a claim | calibrated confidence from evidence weight + source recency + retrieval abstain stats | yes |
| `where_am_i_confused(session_id)` | a session | queries with low-confidence results, contradictions surfaced, abstain hits | no (pure SQL over retrieval_log) |

### Category G — Procedural (Voyager skill-library analog)

| Helper | Input | Output | LLM |
|---|---|---|---|
| `propose_skill(episodic_set)` | N similar episodes | draft skill in Anthropic Skills format with provenance | yes |
| `validate_skill(skill_id, episodic_set)` | existing skill + new episodes | drift detection: does the recipe still match practice? | yes |

### Category H — Foundational (already covered, kept for completeness)

| Helper | Input | Output | LLM |
|---|---|---|---|
| `cite(claim_text)` | a claim | sources that support it, character spans, entailment-checked | yes |
| `extract_claims(source_id)` | a doc | structured claims (subject/predicate/object/qualifier), stored in `extracted_claims` | yes |
| `propose_links(source_id)` | a source | semantically/structurally related sources for `[[wikilinks]]` | no |
| `generate_resume_bundle(project_id)` | a project | see §Compaction-survival bundles | partial |
| `trace_data_flow(symbol, repo)` | code symbol | call graph / data flow from `entities` + `edges` | no |

### Composition example

> Agent: "Why did the docker-compose Postgres install fail last month? Is the lesson generalizable?"

```
brain.recall(query="docker postgres install", deep=true)
  → 3 candidates including failure_memories row F42
attribute_failure(F42)
  → trace_causality(events around F42)
        → chain: [docker compose up] → [permission denied] → [agent reflects "uid mismatch"]
  → root cause: "host volume uid mismatch under docker default user"
synthesize_thesis(
    sources=[F42, decision D17="use native install"],
    hypothesis="docker-compose for Postgres is unreliable on Arch")
  → {verdict: "supported", evidence: [...], confidence: 0.85}
generalize_failure(F42)
  → class rule: "Postgres + Arch + host-mounted volumes → prefer native install"
  → written to procedural bucket as candidate recipe
```

One agent turn, four reasoning ops, one new procedural artifact. The brain orchestrates; the agent gets structured output back.

### Composition is recursive

`plan_research(topic)` for a research-mode user:

```
plan_research("vector quantization tradeoffs in 2026 pgvector")
  ├─ decompose_question → [
  │     "what quantization methods does pgvector support?",
  │     "halfvec vs binary tradeoffs?",
  │     "production reports of recall loss?",
  │     "best practices from PostgresConf 2026"
  │   ]
  ├─ for each sub-query:
  │     brain.recall(deep=true) → candidates
  │     synthesize_thesis(candidates, sub_query) → finding
  │     identify_unknowns(finding) → follow-up questions
  ├─ extract_consensus(findings) → "established view"
  ├─ extract_disagreement(findings) → "open debates"
  └─ assess_confidence per finding
  → returns: structured research plan + provisional answer + next-read list
```

### Grounding contract (load-bearing spec commitment; applies to every LLM-grounded helper)

1. **Every output claim cites ≥1 `source_id` with a character span.** An output sentence without an inline `[id:N]` citation is treated as model speculation and discarded by the wrapper. Helpers return structured JSON, not freeform prose — this is enforceable in code, not via prompt-discipline alone.
2. **Span-level provenance.** When a citation is attached, the helper resolves it to a specific character span (`source_id`, `span_start`, `span_end`). The wrapper validates the quoted excerpt actually appears in the source content; mismatches are rejected and the helper retries once.
3. **Output schema is strict JSON.** A retry-and-validate loop runs up to 3 times before returning `{"error": "schema_violation"}`. Schema mismatches don't propagate to the caller as silent failure.
4. **Cache key = `(helper_name, canonicalized_input_hash, prompt_template_ver)`.** Stored as `reasoning_cache` rows joined to the input sources. Cache hits are exact; prompt-version bump invalidates the cache. *(Phase 2.5 dropped `llm_model_id`/`llm_model_ver` from the hash — the calling agent IS the model, so per-model partitioning no longer applies. Cache becomes cross-agent shareable.)*
5. **Token budget per helper** declared in `brain_config.reasoning_budgets` and enforced. Exceeding the budget returns `{"error": "budget_exceeded", "tokens_used": X}` rather than truncating output silently.
6. **Cost-capped per session** per §Operational concerns. Hard fail or override-prompt, never silent overspend.

### Structured outputs (schemas committed in spec; prompt templates deferred to plan)

```sql
-- Extracted claims persist for later cross-source comparison.
CREATE TABLE extracted_claims (
  id           BIGSERIAL PRIMARY KEY,
  source_id    BIGINT NOT NULL REFERENCES sources(id),
  subject      TEXT NOT NULL,
  predicate    TEXT NOT NULL,
  object       TEXT NOT NULL,
  qualifier    TEXT,                          -- "under condition X" / "in domain Y"
  evidence_span_start INT NOT NULL,
  evidence_span_end   INT NOT NULL,
  confidence   REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  extracted_by_model TEXT NOT NULL,
  extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  t_valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  t_valid_to   TIMESTAMPTZ
);
CREATE INDEX extracted_claims_subject_idx ON extracted_claims USING GIN(to_tsvector('english', subject));

-- LLM call cache. Keyed for cache safety across model swaps.
CREATE TABLE reasoning_cache (
  cache_key    BYTEA PRIMARY KEY,           -- sha256(helper_name + input_hash + prompt_ver)
  helper_name  TEXT NOT NULL,
  input_hash   BYTEA NOT NULL,
  prompt_ver   TEXT NOT NULL,
  output_json  JSONB NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  hit_count    INT NOT NULL DEFAULT 1
);
-- Phase 2.5 dropped llm_model_id, llm_model_ver, tokens_used (no embedded LLM call to track).
```

Prompt templates themselves (the actual Haiku prompt strings) live in `brain/reasoning/prompts/<helper>.txt` and are versioned (`prompt_ver` bumps invalidate the cache). The spec deliberately doesn't fix prompts in the design doc — they will evolve faster than the schema.

## Obsidian markdown view (derived view + partial DR fallback — scope corrected)

The markdown files under `<vault>/Agent-Brain/` serve two roles, but neither is a complete substitute for the DB:

1. **Primary role:** human-readable derived view of the narrative subset of the brain (decisions, gotchas, patterns, project indexes, daily logs, session summaries, failure-memory narratives). Generated by a Python helper, refreshed on demand or via cron.
2. **Partial DR fallback:** if Postgres is corrupted, the markdown files preserve the **narrative knowledge layer** — what was thought, decided, learned. They do NOT preserve: the episodic stream (`events`, `tool_call_output` history, ordered subtask traces), retrieval logs, embeddings, knowledge-graph edges, procedure lifecycle counters, or any structured derivation. Markdown-only re-ingest reconstructs roughly the `bucket=semantic` slice + project indexes; everything else is lost.

**Primary DR is `pg_dump`, not markdown.** Per §Operational concerns, nightly `pg_dump` is the canonical disaster-recovery path. Markdown serves as a second-tier fallback for the human-readable subset only.

**Lossless contract per kind:** the markdown export preserves byte-identical `content` for the kinds listed in §Content fidelity rule as "lossless." `kind='tool_call_output'` rows are *not* exported to markdown by default (high volume, low human value) — they live in DB only and depend on `pg_dump` for DR.

**Round-trip semantic equivalence** (for the exported subset): re-ingesting an exported markdown file produces a `sources` row whose `content` matches the original (modulo regenerated frontmatter). Wikilinks resolve to the same target rows. Frontmatter includes `db_id: <source_id>` to enable re-pairing on re-ingest.

Export shape inside `<vault>/Agent-Brain/`:

```
Agent-Brain/
├── _meta/                # unchanged (AGENTS.md, frontmatter-schema, …)
├── projects/<slug>/
│   ├── index.md          # rendered from projects + recent sessions + open subtasks
│   ├── sessions/         # one .md per session, rendered from sessions + events
│   ├── decisions/        # rendered from sources where bucket=semantic ∧ kind=decision
│   └── failures/         # rendered from bucket=failure (new section)
├── knowledge/            # rendered from bucket=semantic
└── daily/                # rendered from sessions grouped by day
```

Markdown frontmatter includes `db_id: <source_id>` so an Obsidian-side edit can be matched back to the canonical row. A file-watcher reads edits and updates the DB; on conflict (DB updated since render), warn.

**Phase 1 limitation (lifted in Phase 3a):** The export is currently *forward-only* —
re-ingesting the exported markdown via `brain reingest` creates new rows rather than
matching back to the original source (because Phase 1 sources written via `brain.write`
have `uri=NULL` and the exported files have new `file://` URIs). The `db_id` frontmatter
is preserved on export but not yet honored on re-ingest. Phase 3a adds db_id-based
re-ingest, completing the lossless round-trip.

## Interfaces

### Skills (Anthropic Skills format)

The existing `skills/obsidian-*/` directories evolve. Each skill keeps `SKILL.md` (the agent-facing instructions) but its scripts become thin Python wrappers calling the brain's Python API. Skills affected:

- `obsidian-setup` → `brain-setup` (installs Postgres if missing, creates DB, runs migrations, installs hooks)
- `obsidian-recall` → `brain-recall` (calls retrieval pipeline)
- `obsidian-capture` → `brain-capture` (writes via Python API, classifies via `agent-store-decide`)
- `obsidian-project-bootstrap` → `brain-project-bootstrap`
- `obsidian-map-repo` → `brain-map-repo` (uses tree-sitter for symbol index)

Plus new skills (from the expansion spec, mapped onto v2):

- `brain-session-log`, `brain-session-resume` (use `session_resume_bundles`)
- `brain-link` (uses `propose_links`)
- `brain-curate`, `brain-status` (SQL queries with reasoning helpers)
- `brain-decide` (ADR-format via `reasoning.compare`)
- `brain-graph-walk` (recursive CTE over `edges`)
- `brain-health` (vacuum, re-embed, invalidate stale, audit)
- `brain-handoff` (renders a project to portable markdown bundle)

### CLI

```
brain setup                                       # install + migrate + configure
brain capture --kind decision --project brain  …  # explicit write
brain recall "<query>" --project brain --k 5     # retrieve
brain summarize <id1> <id2> …                     # reasoning helper
brain resume <project>                            # print latest resume bundle
brain export --to obsidian                        # refresh markdown view
brain health                                      # diagnostics
brain skill install <name>                        # symlink Anthropic Skills layout
```

### MCP server (later)

Phase 4. Exports brain operations as MCP tools, lets Cursor / Gemini / others use the brain without Python access.

## Migration from v1.0

The current markdown pack contains real content. One-shot migration:

1. Read every `.md` file under `<vault>/Agent-Brain/` recursively.
2. For each: parse frontmatter, classify by type → bucket mapping per §Memory taxonomy. A `decision` source gets both `semantic` and `episodic` bucket rows (matching the multi-bucket schema).
3. Insert as `sources` row, with `kind` matching the original markdown type and `content` = the file body (without frontmatter). Compute `content_hash` for dedup.
4. Resolve wikilinks: for each `[[target-slug]]` in the body, look up the target's `db_id` (from its frontmatter if migrated, else by slug match). Record a `sources` cross-reference (not a content rewrite — the wikilink stays in the text).
5. **Round-trip semantic equivalence check** — re-render the markdown view from the DB. Compare content body byte-for-byte (frontmatter is regenerated with `db_id` added, so cannot be byte-identical and we don't try). If a content body differs, abort the migration for that file and log; the user can inspect and re-run.
6. Keep the markdown files in place. They are now the disaster-recovery store; the watcher takes over for further edits.

The migration script is idempotent and re-runnable. **Wikilink failure handling:** a wikilink whose target slug doesn't exist in the migration set is logged but doesn't abort migration — the link stays in the body as an orphan link, matching Obsidian's own behavior. `brain health` reports orphan-link count.

## Phasing

The build ships in 6 phases (Phase 3 split into 3a/3b/3c per review). Each phase produces working software.

### Implementation status table (2026-05-28, current = v0.10.1)

| Phase | Status | Tag | Notes |
|---|---|---|---|
| **Phase 1 — Foundation** | ✅ shipped | v0.2.0 | All bullets complete |
| **Phase 2 — Hybrid retrieval + Fast-tier reasoning** | ✅ shipped | v0.3-0.5 (pivot 2.5) | All bullets complete; agent-driven pivot in Phase 2.5 |
| **Phase 3a-1 — Compaction-survival core** | ✅ shipped | v0.5.0 | Hooks + bundles + 3 lifecycle skills |
| **Phase 3a-2 — Failure capture + sanitization** | ✅ shipped | v0.6.0 | `brain-failure` skill + Stop-hook auto-flag + ANSI/density/origin-quoting |
| **Phase 3a-3 — Obsidian file watcher** | ❌ pending | — | Originally planned; never implemented. Vault→DB sync still manual |
| **Phase 3a-4 — Compliance subsystem** | ✅ shipped | v0.7.0 | `under_captured`/`thin_session`/`strict_mode`/`brain-compliance` |
| **Phase 3b — Retrieval hardening (Deep tier)** | ⚠️ partial | — | See per-bullet annotations below |
| **Phase 3c — Multi-vector retrieval** | ❌ pending | — | BGE-M3 sparse + ColBERT + late chunking + HyDE all unshipped |
| **Phase 4 — Power features + multi-platform** | ❌ pending | — | None of the bullets shipped |

### Out-of-spec extensions shipped (session-derived, 2026-05-27 / 2026-05-28)

| Item | Tag | What |
|---|---|---|
| `/using-agent-brain` skill + `/brain` slash command | v0.8.0/v0.8.1 | Active capture-recall discipline at session start |
| Bug-cleanup release | v0.8.2 | Isolated `brain_test` DB (was wiping dev brain), psql/Docker docs, TRUNCATE deadlock retry, dropped `session_events_kind_check` |
| Option G retrieval stack (wired hybrid recall as default) | v0.8.3 | `brain recall` CLI now defaults to FTS+BGE-M3+RRF+rerank; `bge-reranker-v2-m3` auto-selected on ≤6GB GPUs; per-reranker tau calibration; `brain ingest backfill` |
| Auto-embed + heuristic contextual ingest | v0.8.4 | Substantive captures auto-embed on `brain write`; multi-chunk sources get `[From <kind>] [Section: <md-header>]` prefix per chunk |
| Stop-hook noise filters | v0.8.5 | 6 filters (system markers, blocklisted tools, recursive brain CLI, CLI-usage errors, etc.) cut FP rate ~66% → <10% |
| Code-aware staleness | v0.9.0 | `sources.provenance_meta` + `brain write --from-file` + `brain staleness check/diff` + SessionEnd records `staleness_detected` event |
| **`brain revise --from-diff`** | v0.10.0 | Extension of Phase 2.5 brain-revise; closes the semantic gap between staleness (file changed) and certainty (claim invalidated). NOT in original spec. |
| **PreToolUse auto-recall hook** | v0.10.1 | Hook fires before Bash/Edit/Write/MultiEdit, runs FTS-only `brain recall` on a topic heuristic, injects top-3 into `additionalContext`. NOT in original spec. |

### Phase 1 — Foundation (v2.0) — ✅ SHIPPED in v0.2.0

Schema scope: `sources` (with `project_id`, `status`, `provenance_kind`, `generation_depth`, `flags`), `sources_fts`, `source_projects` (M2M), `memory_classifications`, `projects`, `sessions`, `subtasks`, `events` (with `procedure_id` FK), `failure_memories`, `procedures` (created empty; populated by user-authored imports in Phase 1, by `distill_pattern`/`propose_skill` from Phase 4), **`entities` and `edges`** (Phase 1 includes minimal entity/edge tables to support `entity_timeline` and `brain-decompose-document` building blocks; LLM-based extraction lands Phase 2), `retrieval_log`, `brain_config`. **Does not include** `embeddings_1024` or HNSW index — pgvector install can be a Phase 1 dependency (extension is created) but no embedding rows are written yet, no HNSW index is built.

- [x] Postgres install + `vector` + `pg_trgm` extensions (via setup skill, optional `docker-compose.yml` provided)
- [x] Schema migrations (alembic): all Phase-1 tables above + the `vector` extension declaration so Phase 2's migration is a single `CREATE TABLE` away
- [x] Python package skeleton (`brain/` Python module)
- [x] `brain.write` / `brain.read` low-level API (text-only path, enforces `generation_depth` computation and depth-3 reject)
- [x] FTS retrieval (full §Retrieval pipeline minus embedding/RRF/rerank)
- [x] Migrate v1 markdown content into DB (per §Migration from v1.0)
- [x] Obsidian markdown view (lossless export, co-equal DR substrate)
- [x] `brain-setup`, `brain-recall`, **`brain-health`** (basic audit: orphan rows, FK integrity, size-by-table, under-captured-session warnings per §Compliance), and **`entity_timeline`** helper (pure SQL, no LLM dependency) skills

### Phase 2 — Hybrid retrieval + Fast-tier reasoning — ✅ SHIPPED in v0.3-0.5

- [x] Alembic migration adding `embeddings_1024` + HNSW index + `extracted_claims` + `reasoning_cache`
- [x] pgvector embeddings via **BGE-M3** (local, Apache-2.0, dense leg first; 1024d HALFVEC)
- [x] **Parent-document chunking** (128–256-tok children, 512–1024-tok parents)
- [x] **Contextual Retrieval** (per-chunk context summary prepended before embedding) — heuristic contextual ships in v0.8.4; LLM-driven via `brain-ingest-contextual` skill (agent-in-loop)
- [x] RRF fusion of FTS + dense candidates
- [x] **mxbai-rerank-large-v2** cross-encoder on top 30–50 — auto-fallback to `bge-reranker-v2-m3` on ≤6GB GPUs (v0.8.3)
- [x] Per-bucket τ thresholds + abstain — per-reranker tau defaults (v0.8.3)
- [x] **Synthesized-content retrieval down-weight** (provenance-aware RRF multiplier using `generation_depth`, depth-3 cap, 60% result-set diversity cap) — required for `brain-promote-answer` safety; both ship together
- [x] Reasoning helpers Fast-tier: `summarize`, `compare`, `cite`, `propose_links`, **`revise_on_ingest`** (paired with `brain-promote-answer` — both write `synthesized` rows, both rely on the down-weight) (with grounding policy + structured JSON outputs)
- [x] `brain-link`, `brain-decide`, `brain-status` skills
- [x] `brain-health` extended with τ-rolling-ratio reports per bucket (full audit + compliance signal stays from Phase 1)
- [x] **`brain-promote-answer`** skill — promotes a high-confidence `reasoning_cache` entry into a permanent `sources` row with `provenance_kind='synthesized'` and `synthesized_from = [input_source_ids]`. Human-gated. Closes the "good answers shouldn't disappear into chat history" gap. Safe because the down-weight ships in the same phase.
- [x] **`brain-decompose-document`** skill — composite that takes an unfamiliar document (PDF, markdown, web page) and produces an interconnected slice of the brain: ingests the source, runs `extract_claims`, identifies entities (people, concepts, terms), creates an `entities`+`edges` subgraph, and renders Obsidian markdown files with wikilinks back to a central index note. The exact composition: `brain.ingest(path) → extract_claims(source_id) → extract_entities(source_id) → upsert edges → obsidian_export(subgraph)`. Used for: reading a paper into the brain, mapping a new repo's README into a project shell, importing external research artifacts. The schema tables (`entities`, `edges`) ship in Phase 1; the LLM-driven `extract_claims` + `extract_entities` helpers ship in Phase 2 — this skill arrives in Phase 2 as the named composition + ships a default Obsidian render template.

**Post-ship pivot (Phase 2.5):** ✅ all five reasoning helpers and Contextual Retrieval were refactored to be agent-driven. The brain prepares the prompt + JSON schema + cache key; the calling agent synthesizes inline; the brain validates and persists. `AnthropicClient`, `BudgetExceeded`, `cost_log`, and the `anthropic` / `pyyaml` dependencies were removed. The schema (embeddings_1024, extracted_claims, reasoning_cache) and the retrieval pipeline (FTS + dense + RRF + cross-encoder + provenance defenses + tau abstain) are unchanged. See `docs/phase2_5.md` and `docs/superpowers/plans/2026-05-24-agent-brain-v2-phase-2-5.md`.

### Phase 3a — Capture fidelity + compaction-survival (the cognition-preservation core)

- [x] Claude Code hooks (PostToolUse, PreCompact, Stop, SessionStart, SessionEnd) — installable opt-in (3a-1 v0.5.0). Note: `SessionStart` delivers the bundle into agent context via `additionalContext`; `PreCompact` only *persists* the bundle (no documented stdout-injection channel). **Out-of-spec addition:** PreToolUse hook auto-injects recall (v0.10.1).
- [x] `session_resume_bundles` generator with the full selection algorithm and token-budget enforcement (3a-1 v0.5.0)
- [x] Failure-memory capture flow (`brain-failure` skill + auto-flag from `Stop` hook) (3a-2 v0.6.0); Stop-hook noise filters (v0.8.5) further refine
- [ ] **PENDING** — File-watcher (Obsidian-side edits → DB update with conflict detection). **Originally Phase 3a-3; never implemented.** Code staleness via `brain staleness` (v0.9.0) is the code-side analogue but does not cover Obsidian vault edits.
- [x] Compliance subsystem (under-captured session detection + warnings) (3a-4 v0.7.0)
- [x] `brain-session-log`, `brain-session-resume`, `brain-handoff` skills (3a-1 v0.5.0)
- [x] Sanitization minimum (ANSI stripping + instruction-density flagging + origin-aware retrieval quoting) (3a-2 v0.6.0)

### Phase 3b — Retrieval hardening (Deep tier) — ⚠️ PARTIAL

- [ ] **PENDING** — Multi-query fusion (3–5 LLM-generated query variants, RRF-fused)
- [ ] **PENDING** — Self-Query (LLM extracts structured filters from query text)
- [ ] **PENDING** — CRAG verification gate (conditional per §Retrieval hardening trigger conditions)
- [ ] **PENDING** — `brain-recall --deep` tier integration
- [x] Eval harness: 20-question hand-curated set against this repo's content shipped in v0.8.3 (see `eval/questions.yaml` + `eval/run_ab.py`). **PENDING** — extension to 50–100 questions + LongMemEval + MemoryAgentBench cross-comparison.

### Phase 3c — Multi-vector retrieval + agent-memory chunking — ❌ PENDING

- [ ] BGE-M3 sparse + ColBERT legs (triple-leg RRF + multi-vector rerank via VectorChord)
- [ ] Late chunking for agent-memory notes (long-context model embeds whole note, then splits)
- [ ] HyDE for keyword-poor queries (conditional)
- [ ] Query decomposition for multi-hop queries

### Phase 4 — Power features + multi-platform + maintenance loops — ❌ PENDING

- [ ] Tree-sitter symbol index (Python helper, populated `entities` + `edges`)
- [ ] Knowledge-graph traversal helpers (`brain-graph-walk`)
- [ ] **`brain-health --lint` (generative lint)** — the basic `brain-health` shipped in Phase 1, the τ reports in Phase 2; Phase 4 adds the `--lint` mode: nightly NLI pass over top-k semantically similar chunks (knowledgebase_guardian pattern, contradiction surfacing) + `identify_gaps` + `find_contradictions` orchestration. **Surfaces results as user-facing questions** (ARIA pattern: "is X still true given Y? [yes/no]"), not silent flags. Tunable per §Retrieval hardening to a target false-positive rate (ClueBot NG framing: 10 missed contradictions beat 1 spurious user prompt).
- [ ] **`brain-schema-evolve`** skill — periodic (or user-invoked) reviews `retrieval_log` patterns, capture-failure stats (under-captured sessions per §Compliance), rejected `brain-promote-answer` / `revise_on_ingest` proposals, and `events.kind='user_correction'` rows to propose specific `_meta/AGENTS.md` amendments. Treats schema as living code, not scripture. Human-gated. Closes the LLM-Wiki article's "schema co-evolution" pattern.
- [ ] **`brain-sleep-time`** (Letta sleep-time-compute pattern, arxiv 2504.13171) — background pass during idle: (a) **FAQs** written to `sources` with `kind='faq'`, `provenance_kind='synthesized'`, `synthesized_from = [source_ids]` (participate in down-weight + depth cap), (b) **distilled summaries** cached in `reasoning_cache`, (c) **resume-bundle refresh** for active projects via `session_resume_bundles`. Amortizes ~2.5× cost on later queries. Opt-in via `brain_config.sleep_time_compute=true`. Cost-capped per §Operational concerns.
- [ ] MCP server (exports brain tools to Cursor/Gemini/Codex)
- [ ] Codex CLI hook adapter
- [ ] Cross-tool handoff format (portable export)
- [ ] Sanitization hardening (structural anomaly detection, optional reject mode, trust scores) — Phase 3a-2 ships the minimum; Phase 4 hardening pending
- [ ] Hard-negative mining + fine-tuning (when query log has enough labeled examples)

Each phase is one implementation plan, written after this spec is approved. Phase 3a is the highest-priority cognition-preservation work; Phase 3b and 3c can land in either order.

### Summary as of v0.10.1 (2026-05-28)

| Bucket | Done | Pending | Total |
|---|---|---|---|
| Phase 1 | 8/8 | 0 | 8 |
| Phase 2 | 13/13 | 0 | 13 |
| Phase 3a (1+2+4) | 6/7 | 1 (Obsidian file watcher) | 7 |
| Phase 3b | 1/5 | 4 (multi-query, self-query, CRAG, --deep wrapper) + eval-50Q | 5 |
| Phase 3c | 0/4 | 4 | 4 |
| Phase 4 | 0/9 | 9 | 9 |
| **Spec total** | **28/46** (61%) | **18** | **46** |
| Out-of-spec extensions shipped | 8 | — | — |

## Test plan

Unit tests in pytest. Integration tests use a throwaway Postgres test database. Categories:

- **Schema migrations** — alembic `upgrade head` then `downgrade base` cycle; idempotent on re-run.
- **Capture round-trip** — write a source, read it back, hash matches.
- **Bi-temporal** — invalidate a row at T1; recall at T0 sees it, recall at T2 doesn't.
- **Hybrid retrieval** — known corpus, known queries, expected top-K. Synthetic data and a small real corpus.
- **RRF correctness** — fixed input ranks, verify output matches reference implementation.
- **Cross-encoder rerank** — sanity check ordering changes vs FTS+vector alone.
- **Hook handlers** — simulate `PostToolUse` payload, verify event + source rows written.
- **Migration from v1** — sample vault, run migrate, diff round-trip render against original.
- **End-to-end** — agent runs a synthetic 50-event session; resume bundle generated; new session reads bundle; agent answers a question about the prior session correctly.

Performance budgets (per phase, per tier):

| Phase | Operation | Budget |
|---|---|---|
| 1 | Capture (single event write) | <50ms p99 |
| 1 | Recall (FTS only) | <100ms p99 for k=5, corpus <100k rows |
| 2 | Recall Fast tier (FTS + dense + RRF + rerank) | <500ms p99 for k=5, corpus <100k chunks |
| 3a | Resume bundle generation (Stop hook) | <2s p99 |
| 3a | Capture via hook (PostToolUse) | <30ms p99 (synchronous on hot path) |
| 3b | Recall Deep tier (+ multi-query + CRAG) | <3s p99 |
| 3c | Recall with multi-vector rerank | <800ms p99 |

Success criterion #7 ("skill loop unchanged in latency vs v1 bash-only") applies to Phase-2 Fast-tier recall — explicitly NOT to Deep tier with CRAG.

## Operational concerns

### Backup & disaster recovery

- **Nightly `pg_dump` cron** writes a logical backup to `<vault>/Agent-Brain/_backups/brain-YYYY-MM-DD.sql.gz`. Retention: 30 days rolling. The setup skill installs the cron.
- **Markdown view is a PARTIAL second-tier fallback** (per §Obsidian markdown view). If both `pg_dump` backups AND Postgres are lost, `brain reingest --from-markdown <vault>/Agent-Brain/` reconstructs the narrative knowledge layer (decisions, gotchas, patterns, project indexes, session summaries). Embeddings, FTS indexes, retrieval logs, `events`/`tool_call_output`, knowledge-graph edges, and procedure lifecycle counters are **permanently lost** in this path. Treat markdown DR as "save the thinking, lose the activity log."
- **WAL archiving** is opt-in for users running long-lived projects (`brain config set wal_archiving on` enables Postgres archive_mode + an `archive_command` to a directory). Default off — adds setup complexity.

### Mid-write corruption

All multi-table writes (a capture that touches `sources`, `sources_fts`, `events`, `memory_classifications`) execute inside a single transaction. `ON DELETE CASCADE` chains are deliberate — partial deletes are prevented by atomicity, not just constraints. The `brain.write` API never auto-commits between table writes.

### Conflict resolution (Obsidian edit ↔ agent write)

A markdown file edited in Obsidian is detected by the file-watcher. Conflict policy:

1. Watcher reads the file, computes `content_hash`, compares against the current valid `sources` row pointing at that file (`uri` match).
2. If the DB hash matches the previous file content → straightforward edit; create a new `sources` row with the new content, invalidate the old.
3. If the DB hash matches the new file content → already in sync (concurrent agent write that happened first), no-op.
4. **If both content versions differ from each other AND from the DB** → genuine conflict. The watcher writes both as `sources` rows, marks the newer one valid, the older one invalidated with `invalidation_reason='conflict: see <other_id>'`. The user sees both in `brain health` and resolves manually. The agent sees a flag in retrieval results.

### Large-table migrations

For schema changes on `sources` or `events` when the corpus exceeds ~100k rows, alembic migrations use the **expand-contract** pattern explicitly: add new column nullable, backfill in batches outside the transaction, then add the constraint. The migration playbook is documented in `docs/migrations/playbook.md` (written in Phase 1). No long-running locks against the working DB.

### LLM API key management

Required for: Contextual Retrieval (Haiku at ingest), CRAG verification (Haiku at retrieve, Deep tier only), reasoning helpers (Haiku/Sonnet by helper).

- Default lookup order: `BRAIN_ANTHROPIC_API_KEY` env var → `ANTHROPIC_API_KEY` env var → `~/.config/brain/keys.yaml` (mode 0600, not in vault).
- Setup skill prompts for keys interactively on first run; stores in `~/.config/brain/keys.yaml`. **Never** in `brain_config` (which gets backed up to vault) and **never** in a checked-in file.
- **Graceful degradation when keys are absent:** Contextual Retrieval is skipped (chunks embedded without context prepend; quality warning logged). CRAG falls back to confidence-threshold-only (no LLM verification). Reasoning helpers return a structured error `{"error": "llm_unavailable"}` — not a silent fallback to a worse result.

### Cost guards

`brain_config.cost_caps` defines per-session ceilings (default values, tunable):

| Operation | Default cap | Action when exceeded |
|---|---|---|
| Contextual Retrieval (ingest, Haiku) | $0.50 / session | Stop contextualizing further chunks; warn in `brain health`. Already-contextualized rows persist. |
| CRAG verifications (Haiku) | 50 calls / session | Fall back to confidence-only retrieval for remainder. |
| Reasoning helpers (Haiku/Sonnet) | $2.00 / session | Hard fail with `{"error": "cost_cap_exceeded", "spent": X, "cap": Y}`. |

*(Phase 2.5 removed cost_log and the cost-cap subsystem entirely; reasoning is now agent-driven, so all token cost is borne by the host agent's session — already budgeted by the host runtime. The cost-cap table above describes the legacy Phase 2 embedded-Haiku model retained for historical context only.)*

## Risks and mitigations

- **Postgres install friction.** Mitigation: setup skill ships `docker-compose.yml` and a native-install fallback (pacman/apt/brew detection). User picks.
- **Embedding model drift.** Mitigation: `embeddings(model_id, version)` PK lets two models coexist; re-embed is a single SQL query; old vectors stay until explicit cleanup.
- **DB growth.** Mitigation: `tool_call` event outputs are head+tail-truncated by default. `brain health` reports size by table/bucket. Archive policy: invalidate (don't delete) after N months stale.
- **Markdown↔DB drift.** Mitigation: file-watcher + content-hash. Conflict surfaces in `brain health`.
- **Cross-platform hook gaps.** Mitigation: Phase 3 ships adapters per platform; Phase 1–2 work via Path-1 (agent-proactive) only.
- **Failure memory bloat.** Mitigation: failure memories deduplicated by `content_hash`; re-occurring failures bump a `retry_count` rather than spawning new rows. `brain-curate` surfaces unresolved failures for periodic review.
- **Privacy.** Default local-only (Postgres on localhost, local embeddings). Cloud embedders are opt-in and config-flagged.
- **Brain-rot from synthesized pollution.** Recursive LLM-derived content drives representational drift (Oct-2025 brain-rot research). Mitigation: `provenance_kind` typing + `generation_depth` recursive cap at 3 + RRF down-weight `0.7 / (1 + depth)` + stale-provenance flag ×0.5 + 60% result-set diversity cap + synthesized-ratio escalation in the compounding regression test.
- **Procedure rot (deprecated recipes re-applied).** Without lifecycle state, the procedural store accumulates stale recipes that get re-applied and re-fail. Mitigation: `procedures` table with Memp lifecycle, success/failure counters, auto-deprecate trigger (`failure_count > 0.5 * total AND n >= 5`), partial unique index enforcing one active step + one active script per situation, `deprecated_at IS NOT NULL` excluded from apply-path retrieval.
- **Contradiction-prompt fatigue.** Generative-lint can degenerate into nuisance prompts that erode user trust. Mitigation: `brain-health --lint` NLI pass tuned to ≤1 false-positive prompt per week per the ClueBot NG framing; questions surfaced via ARIA pattern (structured Q with yes/no), never silent flags or vague alerts.

## Success criteria

1. Cold-start a Claude Code session in this brain repo. `brain-session-resume` returns a ≤500-token brief that includes: most recent subtask, last 5 decisions, current open threads. Reading it gets the agent 80% of the context it would otherwise re-derive over 10 minutes.
2. After a session ends and gets compacted, the next session's `brain-recall "what did I try last time for X"` returns the actual attempts including the failed ones, with reasoning attached.
3. Same query routed three ways (project filter, FTS, semantic) returns consistent top-3 — verifying the hybrid stack isn't producing nonsense.
4. Failure memories prevent at least one observable repeat: agent gets a "you tried this approach 2 weeks ago, here's why it failed" hit before retrying.
5. The Obsidian view in `<vault>/Agent-Brain/` remains readable by a human, browseable in Obsidian, with clean links. The human's existing vault content outside `Agent-Brain/` is untouched (existing namespace rule preserved).
6. Brain is portable: a Codex CLI session can call the brain via the MCP server (Phase 4) and capture/recall using the same vocabulary.
7. p99 recall <500ms; p99 capture <50ms; end-to-end skill loop unchanged in latency vs v1 bash-only.

## Appendix A — Adversarial walkthrough

To verify the schema-feature gap is closed, here's a real scenario from this repo traced through the system. Each step lists what gets written, where, when, and what `brain-recall` finds later.

**Scenario:** Agent is installing Postgres + pgvector on Arch Linux. First tries `docker compose` with the `pgvector/pgvector:pg16` image. Hits a permissions issue with the host-mounted data volume. Abandons docker, switches to native install via `pacman -S postgresql && pacman -S postgresql-pgvector`. Native install succeeds.

| Step | Action | Rows written | Notes |
|---|---|---|---|
| 1 | Agent starts task: "install postgres + pgvector" | `subtasks(goal='install postgres + pgvector')`, `events(kind='plan', source_id=...)` | Plan is a `sources` row of `kind='note'`, classified as `episodic`. |
| 2 | Runs `docker compose up -d` (hook fires) | `events(kind='tool_call', tool='Bash', input_id=A, output_id=B, status='error', duration_ms=2400)`. A = the command string, B = the output containing "permission denied on /var/lib/pgsql". Both as `sources(kind='command')` / `sources(kind='tool_call_output')`, classified `episodic`. | Output captured via head+tail+error-span; the "permission denied" line is preserved because it matches the error pattern. |
| 3 | Agent reflects: "docker is fighting me here, switching to native" | `events(kind='reflection', source_id=C)`. C is the reflection note. Classified `episodic`. | |
| 4 | Agent captures the failed approach (Path 1, mandatory) | `failure_memories(target_problem='install postgres + pgvector on Arch', attempted_approach='docker compose with pgvector/pgvector:pg16 image', outcome_evidence='[id:B] permission denied on /var/lib/pgsql', root_cause='host-volume uid mismatch', lesson='for Postgres on Arch prefer native install over docker', retry_count=1)`. Linked `sources` row holds the narrative; classifications `failure` + `episodic`. | This is the row that makes step 9 work. |
| 5 | Agent runs `pacman -S postgresql postgresql-pgvector`, succeeds | `events(kind='tool_call', tool='Bash', status='ok', ...)`. | |
| 6 | Agent captures the decision: "native install over docker for Postgres on Arch" | `events(kind='decision', source_id=D)`. D classified `episodic` (in this session) + `semantic` (the rule itself is durable). | Multi-bucket classification via the new schema. |
| 7 | Subtask ends successfully | `subtasks.ended_at = NOW(), outcome='success', subtask_summary` written to `sources` | |
| 8 | Session ends (`Stop` hook fires) | `session_resume_bundles` row written. Manifest includes: active_subtask=null (just resolved), recent_decisions=[D], recent_failures=[failure_memories row], recent_commands_succeeded=[pacman command], recent_commands_failed=[docker command with output tail]. Rendered as ≤500-token markdown. | |
| 9 | **Two weeks later**, new session starts on this repo. Agent considers using docker for Postgres on another project. | `SessionStart` hook reads latest active bundle for this project. Bundle text doesn't immediately mention docker. Agent proceeds. Then agent runs `brain-recall "docker postgres install"` before pulling the trigger. | |
| 10 | The recall pipeline | Metadata filter: project=brain, t_valid_to IS NULL, bucket IN ('failure', 'semantic'). FTS hits the docker-related failure row + decision row. Dense kNN hits same. RRF fuses, reranker promotes the failure row. Top result: the failure_memories row from step 4. | |
| 11 | Agent sees: "you tried docker compose with pgvector/pgvector:pg16 → permission denied on /var/lib/pgsql; root cause: host-volume uid mismatch; lesson: prefer native install on Arch. retry_count=1, last_attempted=2026-05-09." | Doesn't re-attempt the failed approach. Captures a new failure_memories row if the new project actually has a different attempted_approach. | Success criterion #4 met: agent prevented from repeating the same dead end. |

**Schema-feature gaps surfaced during the walkthrough:** none in the current design. (Before the review fixes: step 4 had no `failure_memories` table to write to; step 6's multi-bucket was forbidden by the old PK; step 10 didn't know which embedding model to query against. All three are resolved in the current spec.)

## Open questions resolved by research

| Question | Resolution |
|---|---|
| Best embedding model for code + markdown + papers? | **BGE-M3** (local, Apache-2.0, dense+sparse+ColBERT in one model). Voyage-3-large as cloud upgrade path. |
| Contextual Retrieval worth the LLM cost? | **Yes** — highest-ROI single intervention. ~$1.02/1M doc tokens with caching. Day-1 adoption in Phase 2. |
| Chunking strategy? | **Parent-document retrieval** as default; **late chunking** for agent-memory notes. RecursiveCharacterTextSplitter is the floor, not the goal. |
| ColBERT-style multi-vector? | **Phase 3** as a reranker (top-50 from RRF → ColBERT MaxSim). VectorChord ships pgvector integration. Not a primary index — 30–100× storage. |
| Best reranker today? | **mxbai-rerank-large-v2** (Apache-2.0, self-hosted). Cohere Rerank v4 if zero-ops. |
| FP / FN mitigations? | Multi-query fusion (recall), CRAG verification gate (precision), confidence threshold + abstain (precision). All Phase 3. |
| Eval methodology? | Hand-curated 50–100-question set against this repo's own content. LongMemEval + MemoryAgentBench for cross-field comparison. |
