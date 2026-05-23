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
| Failure memory as typed entity | Missing in popular frameworks | First-class `failure_memory` type |
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
  content         TEXT NOT NULL,        -- the actual text — never truncated, never lossy
  content_hash    BYTEA NOT NULL,       -- sha256 of content for dedup
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
  span_end        INT
);
CREATE INDEX sources_kind_idx ON sources(kind);
CREATE INDEX sources_validity_idx ON sources(t_valid_from, t_valid_to);
CREATE UNIQUE INDEX sources_hash_idx ON sources(content_hash);

-- Full-text index, generated from content.
CREATE TABLE sources_fts (
  source_id  BIGINT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
  tsv        TSVECTOR NOT NULL
);
CREATE INDEX sources_fts_idx ON sources_fts USING GIN(tsv);

-- Embeddings. Multiple per source allowed (different models).
CREATE TABLE embeddings (
  source_id  BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  model_id   TEXT NOT NULL,             -- 'openai/text-embedding-3-large' | 'nomic-embed-text-v2' | …
  model_ver  TEXT NOT NULL,             -- specific version tag
  dim        INT NOT NULL,              -- 768 / 1024 / 3072 …
  vec        HALFVEC NOT NULL,          -- float16, 50% storage vs float32
  embedded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (source_id, model_id, model_ver)
);
CREATE INDEX embeddings_hnsw_idx ON embeddings
  USING hnsw (vec halfvec_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Memory taxonomy: every source belongs to exactly one bucket.
CREATE TABLE memory_classifications (
  source_id  BIGINT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
  bucket     TEXT NOT NULL CHECK (bucket IN ('semantic', 'episodic', 'procedural', 'failure')),
  classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  classifier TEXT NOT NULL                 -- 'agent' | 'hook' | 'user' | 'auto-router'
);
CREATE INDEX memory_classifications_bucket_idx ON memory_classifications(bucket);
```

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
                                         -- 'decision' | 'plan' | 'blocker' | 'resolution'
  tool         TEXT,                     -- for tool_call: 'Bash' | 'Edit' | 'Read' | …
  input_id     BIGINT REFERENCES sources(id),  -- tool input (cmd, file path, …)
  output_id    BIGINT REFERENCES sources(id),  -- tool output (stdout, file contents, …)
  source_id    BIGINT REFERENCES sources(id),  -- semantic note attached to event
  status       TEXT,                     -- 'ok' | 'error' | 'timeout' | 'denied'
  duration_ms  INT,
  occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX events_session_ordinal_idx ON events(session_id, ordinal);
CREATE INDEX events_subtask_idx ON events(subtask_id);
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

### Compaction-survival

```sql
-- Pre-computed "what should be in context next session" bundles, per project.
CREATE TABLE session_resume_bundles (
  project_id    BIGINT NOT NULL REFERENCES projects(id),
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  manifest      JSONB NOT NULL,          -- ordered list of source_ids with rationale
  rendered      TEXT NOT NULL,           -- the ≤500-token brief, ready to paste
  PRIMARY KEY (project_id, generated_at)
);
```

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
| `PostToolUse` | Insert `events` row + truncated head/tail of output into `sources` (under `kind='tool_call'`). Bash output capped at 4KB head + 4KB tail by default, configurable. |
| `PreCompact` | Generate a `session_resume_bundle` snapshotting current state before the compactor runs. |
| `SessionStart` | If a resume bundle exists for the active project, agent should consult it. |
| `Stop` | Finalize current session row: set `ended_at`, generate session summary, classify session into memory buckets. |
| `SubagentStop` | Mark subtask outcome if subagent was running a subtask. |

The hooks are installed by the setup skill (opt-in, gated on user approval) and edit `~/.claude/settings.json` carefully.

Cross-platform: Codex CLI v0.128+ has analogous lifecycle events; an adapter layer translates. Cursor and Gemini lack equivalent hooks today — those agents rely on Path 1 + Path 3.

### Path 3: user-explicit

Two surfaces:

- CLI: `brain remember "<text>"`, `brain link <slug> <slug>`, `brain invalidate <id>`.
- Obsidian: user edits a markdown file directly; a file-watcher Python helper detects the change, re-ingests, and updates rows. (Obsidian write → markdown is the source of one ingestion path; the canonical Postgres row is updated.)

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

1. **Metadata pre-filter** — every retrieval first narrows by `project_id`, `t_valid` covers now, `bucket`, optional `kind` / `status`.
2. **Hybrid candidate generation, parallel:**
   - Postgres FTS (BM25-like via `ts_rank_cd`) over `sources_fts.tsv`. k=100.
   - pgvector kNN over `embeddings.vec` with HNSW. k=100.
3. **Reciprocal Rank Fusion (RRF)** to fuse the two lists. One-line algorithm, no score normalization needed.
4. **Cross-encoder rerank** of top 30–50 candidates. BGE-reranker-v2 as default (local model). Cohere Rerank or ColBERT plug-in as alternatives.
5. **Return top 5–10** with provenance (source URI, span, score).

**FP/FN-specific hardening:** *(filled in after research subagent returns; see §Retrieval hardening below)*

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

- Empirical: 49% reduction in retrieval failures with FTS, 67% with FTS + reranker (Anthropic's numbers, replicated in 2025–26).
- Cost: ~$1.02 per 1M doc tokens with prompt caching. Negligible at personal-corpus scale.
- Adoption: this is the highest-ROI single intervention in the field. Day-1 commitment.

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

**CRAG (Corrective RAG)** as the final gate:
- LLM-as-judge scores each top-K candidate's relevance to the query.
- 3-way verdict: ≥0.7 keep, ≤0.3 discard, else "merge" (combine with another candidate or expand search).
- Cost: +100–800ms latency, one Claude Haiku call.
- Implementation: `reasoning.verify(query, candidates)` runs as the last retrieval stage.

**Confidence threshold + abstain**:
- If the reranker's top-1 score is below τ=0.7 (tunable), the system returns **"no high-confidence match"** rather than a weak result.
- Empirically the single most effective FP guard. Abstain beats wrong.

#### Provenance and consolidation tracking

Every retrieval call writes a row to `retrieval_log`:

```sql
CREATE TABLE retrieval_log (
  id          BIGSERIAL PRIMARY KEY,
  query       TEXT NOT NULL,
  filters     JSONB,
  candidates  JSONB,             -- top-K with scores per stage
  selected    BIGINT[],          -- which source_ids the agent actually used (filled in post-hoc)
  agent       TEXT,
  session_id  BIGINT REFERENCES sessions(id),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

This lets us detect:
- **Context consolidation failures** — retrieved-but-not-used (40% of RAG quality is here, per 2026 production writeups).
- **Recurrent recall misses** — same query, low scores, agent abandoned retrieval.
- **Hard negatives** for future fine-tuning (Phase 4).

#### Sanitization at ingest (poisoned-doc defense)

Agent memory is a write-anything surface. Every ingested document runs through a sanitization pass:
- Detect prompt-injection patterns (instruction-like text in surprising positions).
- Strip ANSI escapes, control characters from tool outputs.
- Flag (don't reject) suspicious content with `sources.flags={'suspicious': true, 'reason': ...}` — the agent sees the flag in retrieval results.

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
- **LongMemEval** (ICLR 2025) and **MemoryAgentBench** (ICLR 2026) for cross-comparison with the field.
- Track precision/recall@k, MRR, abstain rate, and **retrieved-vs-used ratio** from `retrieval_log`.
- Threshold τ is swept on the hand-curated set; pick the precision/recall knee.

## Reasoning helpers

Each is a Python function exposed both as a CLI subcommand and as a skill. All operate over retrieval results, never against blind queries.

| Helper | Input | Output |
|---|---|---|
| `summarize(source_ids[]) → text` | a set of sources | concise synthesis ≤500 tokens, with citations |
| `compare(a_id, b_id) → text` | two sources | side-by-side analysis: agreements, disagreements, scope difference |
| `contrast(query, candidate_ids[]) → text` | a question, candidates | which best answers, why others miss |
| `cite(claim_text) → sources[]` | a natural-language claim | sources that support it, with character spans |
| `extract_claims(source_id) → claims[]` | a paper / doc | structured claims (subject, predicate, object, qualifier) |
| `propose_links(source_id) → candidate_ids[]` | a source | semantically/structurally related sources for `[[wikilinks]]` |
| `generate_resume_bundle(project_id) → bundle` | a project | ≤500-token brief: active subtask, last decisions, open threads, top-N relevant chunks |
| `trace_data_flow(start_symbol, repo) → graph` | a code symbol | call graph / data flow extracted from `entities` + `edges` |

LLM calls are batched and cached by input hash; reused across sessions.

## Obsidian export (derived view)

The brain remains the source of truth; Obsidian sees a markdown render of selected slices. Generated by a Python helper, refreshed on demand or via a cron.

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

The current markdown pack contains real content (the `projects/brain/` self-host, the decision about Agent-Brain namespacing). One-shot migration:

1. Read every `.md` file under `<vault>/Agent-Brain/` recursively.
2. For each: parse frontmatter, classify by type → bucket mapping (`decision` → semantic+episodic; `gotcha` → failure; `pattern` → procedural; `session` → episodic; etc.).
3. Insert as `sources` row, with `kind` matching the original markdown type and `content` = the file body (without frontmatter).
4. Re-render markdown view from the DB (round-trip identity check).
5. Keep markdown files in place (they're the rendered view; the watcher takes over from here).

The migration script is idempotent and re-runnable.

## Phasing

The build ships in 4 phases, each producing working software.

### Phase 1 — Foundation (v2.0)

- Postgres install + pgvector + pg_trgm extensions
- Schema migrations (alembic)
- Python package skeleton (`brain/` Python module)
- `brain.write` / `brain.read` low-level API
- FTS retrieval (no vectors yet)
- Migrate v1 markdown content into DB
- Obsidian export (read-only, generates markdown from DB)
- `brain-setup` and `brain-recall` skills (replacing the bash equivalents)

### Phase 2 — Hybrid retrieval + reasoning

- pgvector embeddings via **BGE-M3** (local, Apache-2.0, dense leg first)
- HNSW index over halfvec; `embedding(model_id, version)` from day one
- **Parent-document chunking** (128–256-tok children, 512–1024-tok parents)
- **Contextual Retrieval** (per-chunk context summary prepended before embedding)
- RRF fusion of FTS + dense candidates
- **mxbai-rerank-large-v2** cross-encoder on top 30–50
- Reasoning helpers (`summarize`, `compare`, `cite`, `propose_links`)
- `brain-link`, `brain-decide`, `brain-status` skills

### Phase 3 — Capture fidelity + compaction-survival + retrieval hardening

- Claude Code hooks (PostToolUse, PreCompact, Stop, SessionStart) — installable opt-in
- `session_resume_bundles` generator (in PreCompact + Stop)
- Failure-memory typing + the `brain-failure` capture flow
- File-watcher (Obsidian-side edits → DB update)
- **Retrieval hardening**: multi-query fusion, Self-Query filter extraction, CRAG verification gate, confidence-threshold abstain, late chunking for agent-memory notes
- BGE-M3 sparse + ColBERT legs added (triple-leg RRF + multi-vector rerank via VectorChord)
- `brain-session-log`, `brain-session-resume`, `brain-handoff` skills

### Phase 4 — Power features + multi-platform

- Tree-sitter symbol index (Python helper, populated `entities` + `edges`)
- Knowledge-graph traversal helpers (`brain-graph-walk`)
- `brain-health` (audit, vacuum, re-embed, invalidate stale)
- MCP server (exports brain tools to Cursor/Gemini/Codex)
- Codex CLI hook adapter
- Cross-tool handoff format (portable export)

Each phase is one implementation plan, written after this spec is approved.

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

Performance budgets:
- Capture: <50ms p99 for a single event write.
- Recall (hybrid + rerank): <500ms p99 for k=5, corpus <100k chunks.
- Resume bundle generation: <2s p99.

## Risks and mitigations

- **Postgres install friction.** Mitigation: setup skill ships `docker-compose.yml` and a native-install fallback (pacman/apt/brew detection). User picks.
- **Embedding model drift.** Mitigation: `embeddings(model_id, version)` PK lets two models coexist; re-embed is a single SQL query; old vectors stay until explicit cleanup.
- **DB growth.** Mitigation: `tool_call` event outputs are head+tail-truncated by default. `brain health` reports size by table/bucket. Archive policy: invalidate (don't delete) after N months stale.
- **Markdown↔DB drift.** Mitigation: file-watcher + content-hash. Conflict surfaces in `brain health`.
- **Cross-platform hook gaps.** Mitigation: Phase 3 ships adapters per platform; Phase 1–2 work via Path-1 (agent-proactive) only.
- **Failure memory bloat.** Mitigation: failure memories deduplicated by `content_hash`; re-occurring failures bump a `retry_count` rather than spawning new rows. `brain-curate` surfaces unresolved failures for periodic review.
- **Privacy.** Default local-only (Postgres on localhost, local embeddings). Cloud embedders are opt-in and config-flagged.

## Success criteria

1. Cold-start a Claude Code session in this brain repo. `brain-session-resume` returns a ≤500-token brief that includes: most recent subtask, last 5 decisions, current open threads. Reading it gets the agent 80% of the context it would otherwise re-derive over 10 minutes.
2. After a session ends and gets compacted, the next session's `brain-recall "what did I try last time for X"` returns the actual attempts including the failed ones, with reasoning attached.
3. Same query routed three ways (project filter, FTS, semantic) returns consistent top-3 — verifying the hybrid stack isn't producing nonsense.
4. Failure memories prevent at least one observable repeat: agent gets a "you tried this approach 2 weeks ago, here's why it failed" hit before retrying.
5. The Obsidian view in `<vault>/Agent-Brain/` remains readable by a human, browseable in Obsidian, with clean links. The human's existing vault content outside `Agent-Brain/` is untouched (existing namespace rule preserved).
6. Brain is portable: a Codex CLI session can call the brain via the MCP server (Phase 4) and capture/recall using the same vocabulary.
7. p99 recall <500ms; p99 capture <50ms; end-to-end skill loop unchanged in latency vs v1 bash-only.

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
