# Obsidian Second Brain

A skill pack that turns an Obsidian vault into a persistent, organized second brain for coding agents. Filesystem-direct (no MCP server), agent-agnostic (Claude Code, Codex, Cursor, GitHub Copilot, Gemini, Aider, and anything else that reads markdown).

## What it does

Coding agents waste time and context every session rediscovering enterprise knowledge — architecture, APIs, process docs, prior decisions, recurring gotchas. This pack gives agents:

- A **namespaced workspace** at `~/Documents/ObsidianVault/Agent-Brain/` with sections for durable knowledge, agent working memory, per-project notes, and daily logs. The rest of your vault — your own notes, journals, references — is off-limits to every skill.
- **Skills** that tell agents *when* to recall context (before non-trivial work) and *how* to capture learnings (decisions, gotchas, patterns).
- **A mandatory project-bootstrap rule** — every new project starts with `projects/<name>/` and a task-typed index. Non-negotiable. Cross-agent.
- **Cross-agent interop** via `<vault>/Agent-Brain/_meta/AGENTS.md` — any agent with filesystem access uses the same brain.
- **Cross-device sync** by riding Obsidian Sync (you bring your own).

## Install

The repo ships parallel plugin manifests for each platform. Pick yours.

### Claude Code

Register this repo as a marketplace, then install the plugin:

```bash
/plugin marketplace add keertan-balaji/agent-brain
/plugin install agent-brain@agent-brain
```

Or, for local development (no GitHub round-trip), point the marketplace at the local clone:

```bash
/plugin marketplace add <path-to-repo>
/plugin install agent-brain@agent-brain
```

Symlink fallback (no marketplace, no plugin system):

```bash
bash clients/install-claude-code.sh
```

Then add the vault path to `~/.claude/settings.json` so native file tools reach it (auto-mode correctly blocks the agent from doing this for you):

```json
"permissions": { "additionalDirectories": ["~/Documents/ObsidianVault"] }
```

### Codex CLI / Codex App

```bash
/plugins
# search "agent-brain", install
```

The repo includes `.codex-plugin/plugin.json` with the full Codex interface manifest.

### Cursor

In Cursor agent chat:

```
/add-plugin agent-brain
```

Or, for ambient instructions without the plugin runtime, drop the universal instructions file into the repo you're working in:

```bash
mkdir -p .cursor/rules
cp clients/agent-instructions.md .cursor/rules/agent-brain.mdc
```

### Gemini CLI

```bash
gemini extensions install https://github.com/keertan-balaji/agent-brain
gemini extensions update agent-brain   # to refresh later
```

### GitHub Copilot CLI

```bash
copilot plugin marketplace add keertan-balaji/agent-brain
copilot plugin install agent-brain@agent-brain
```

For VS Code Copilot (no plugin marketplace), drop the instructions file:

```bash
mkdir -p .github
cp clients/agent-instructions.md .github/copilot-instructions.md
```

### Aider

```bash
cp clients/agent-instructions.md CONVENTIONS.md
aider --read CONVENTIONS.md
```

### Anything else (AGENTS.md spec, Cline, Continue, Zed, Windsurf)

Drop `clients/agent-instructions.md` at the path your agent reads. See `clients/<platform>/README.md` for specifics.

## After install

1. `/obsidian-setup` — asks where your vault is (Obsidian Sync path, custom location, or default `~/Documents/ObsidianVault`), scaffolds gaps, persists choice.
2. `/obsidian-map-repo` — onboards the current repo: bootstraps `projects/<repo>/` and writes a stack/tree/README/git scan into `repo-map.md`.
3. From here on:
   - `/obsidian-recall <topic>` before non-trivial work.
   - `/obsidian-capture <decision|gotcha|pattern>` after substantive moments.

## Skills

| Skill | When to use |
|---|---|
| `obsidian-setup` | First run; asks where your vault is, scaffolds gaps, persists choice |
| `obsidian-project-bootstrap` | **Mandatory** — first action on any new project |
| `obsidian-map-repo` | Onboard a coding repo: stack/tree/README/git → `projects/<repo>/repo-map.md` |
| `obsidian-recall` | Before non-trivial work; when topic mentioned; before brainstorming |
| `obsidian-capture` | After non-trivial decision; gotcha hit; pattern emerged |

## Why this design

- **No MCP server.** The vault is plain markdown; agents use their native file tools. One fewer moving part, fewer failure modes, and the same vault works for every agent on day one.
- **Conventions are runtime-loaded.** Agents read `<vault>/Agent-Brain/_meta/AGENTS.md` at session start. Update conventions there once and every agent picks them up — no re-install across N repos.
- **Single namespace, no vault pollution.** Everything the agent creates lives under `<vault>/Agent-Brain/`. Your existing notes, daily journal, and references stay untouched. Override the subdir name with `BRAIN_SUBDIR=Some-Name` if `Agent-Brain` clashes.
- **Bootstrap is mandatory.** Every new project gets a folder + task-typed index before any other vault writes. Encoded in both the platform skills and the cross-agent contract.
- **Write isolation.** Agents write freely to `agent-memory/` and `projects/`. `knowledge/` is human-curated, never agent-clobbered.

## Repo layout

```
.claude-plugin/plugin.json       # Claude Code manifest
.claude-plugin/marketplace.json  # single-plugin marketplace, registerable directly
.codex-plugin/plugin.json        # Codex manifest (with interface block)
.cursor-plugin/plugin.json       # Cursor manifest
gemini-extension.json            # Gemini CLI extension
AGENTS.md → clients/agent-instructions.md  # universal contract (symlink)
CLAUDE.md → clients/agent-instructions.md  # same content under each agent's filename
GEMINI.md → clients/agent-instructions.md
skills/                          # the 5 skills (auto-discovered)
vault-template/                  # initial vault scaffold
clients/                         # per-platform install docs + universal instructions file
docs/superpowers/                # spec + plan
tests/                           # 9 test files, run-all.sh harness
```

## Agent Brain v2 — Phase 1

Phase 1 ships: Postgres-backed schema, Python core (`brain.write` / `brain.read`), FTS retrieval, 3 skills (`brain-setup`, `brain-recall`, `brain-health`), v1 markdown migration, Obsidian export.

Quick start:

```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
bash skills/brain-setup/scripts/setup.sh
brain --help
```

Full install + operations: `docs/installation.md`, `docs/operations.md`.

Embeddings, RRF, reranker, hooks, MCP — all later phases. See `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md`.

## Agent Brain v2 — Phase 2

> **Superseded by Phase 2.5 (below).** The embedded-Haiku flow described in this section was deleted: `BRAIN_ANTHROPIC_API_KEY` is no longer read, and `anthropic` is no longer a dependency. The retrieval pipeline (BGE-M3 + RRF + mxbai rerank + provenance defenses) is unchanged. Follow the Phase 2.5 quick-start below.

Phase 2 originally shipped hybrid retrieval, parent-document chunking, Contextual Retrieval (Haiku), provenance-aware ranking, 5 Fast-tier reasoning helpers, 4 new skills, and a tau-rolling-ratio health report.

Historical quick-start (DO NOT use on a fresh install — Phase 2.5 is current):

```bash
# Historical only — anthropic dep removed in Phase 2.5
export BRAIN_ANTHROPIC_API_KEY=sk-ant-...
uv pip install -e ".[dev]"
brain --help
```

New skills:

| Skill | When to use |
|---|---|
| `brain-link` | After capturing a new source — surfaces related sources for wikilinking |
| `brain-decide` | Capture an ADR-formatted decision instead of a free-form note |
| `brain-status` | Session-start orientation: active projects + recent captures + recent failures |
| `brain-promote-answer` | Save a good reasoning-helper output as a durable source |

Operations + setup: `docs/phase2.md`. Spec: `docs/superpowers/specs/2026-05-23-agent-brain-v2-design.md`.

Phase 3 (hooks, compaction survival, multi-query fusion, sparse/ColBERT legs) — see spec.

## Agent Brain v2 — Phase 2.5

Phase 2.5 pivots reasoning helpers + Contextual Retrieval to agent-driven. **No Anthropic API key required.** Same hybrid retrieval + reranker stack as Phase 2.

```bash
# Existing Phase 2 install — just re-install to pick up dropped deps
source .venv/bin/activate && uv pip install -e ".[dev]" && alembic upgrade head
brain --help
```

5 new agent-facing skills:

| Skill | When to use |
|---|---|
| `brain-summarize` | After recalling 2+ sources; produces cited structured synthesis |
| `brain-compare` | Pairwise comparison of two sources (typed disagreement axis) |
| `brain-cite` | Ground a claim in verbatim source spans (hallucination defense) |
| `brain-revise` | A-MEM neighbor-rewrite plan after ingesting a contradicting source |
| `brain-ingest-contextual` | 3-step contextual retrieval for long docs (>2k tokens) |

Operations: `docs/phase2_5.md`. Plan: `docs/superpowers/plans/2026-05-24-agent-brain-v2-phase-2-5.md`.

## Agent Brain v2 — Phase 3a-1

Phase 3a-1 ships the compaction-survival core. Claude Code's session lifecycle hooks (SessionStart/End, UserPromptSubmit, Stop, PreCompact) now write to the brain, and on `/compact` a structured resume bundle is persisted and re-injected at the next session's start.

```bash
alembic upgrade head    # migration 010
/plugin install agent-brain@agent-brain   # carries the hooks
/reload-plugins
```

3 new skills:

| Skill | When to use |
|---|---|
| `brain-session-log` | List recent session_events |
| `brain-session-resume` | Inspect or regenerate the latest bundle |
| `brain-handoff` | Export the bundle to markdown/JSON |

Operations: `docs/phase3a_1.md`. Plan: `docs/superpowers/plans/2026-05-25-agent-brain-v2-phase-3a-1.md`.

## Agent Brain v2 — Phase 3a-2

Phase 3a-2 turns the previously-dormant `failure_memories` table into a live capture surface. The Stop hook now scans the session transcript for failure signatures (Bash `is_error`, `Traceback`, `FAILED`, mid-line `command not found`, non-zero `Exit code`) and upserts `failure_memories` rows. The dedup key is `(target_problem, attempted_approach)` — a re-attempt bumps `retry_count` rather than creating a duplicate row. The ingest path now strips ANSI escapes and flags suspicious instruction-density content (`flags.suspicious=true`) for high-risk kinds (`tool_call_output`, `command`, `web_page`, `code_file`). Recall output wraps high-risk content in `<tool-output>` / `<web-content>` delimiters so consumer LLMs treat it as data.

```bash
# No new migration. Just:
git pull && /reload-plugins
```

New skill + CLI:

| Skill | When to use |
|---|---|
| `brain-failure` | Record a failure explicitly, list active failures, or invalidate a stale one |

```bash
brain failure record --target-problem "..." --attempted-approach "..." --outcome-evidence "..."
brain failure list [--limit N] [--project-id ID]
brain failure invalidate <id> --reason "..."
```

Operations: `docs/phase3a_2.md`. Plan: `docs/superpowers/plans/2026-05-26-agent-brain-v2-phase-3a-2.md`.

Follow-on plans queued: 3a-3 (file watcher), 3a-4 (compliance subsystem).

## Design docs

- Spec: `docs/superpowers/specs/2026-05-17-obsidian-second-brain-skill-pack-design.md`
- Plan: `docs/superpowers/plans/2026-05-17-obsidian-second-brain-phase-1.md`

## Tests

```bash
bash tests/run-all.sh
```

9 test files: scaffold, frontmatter validation, recall priority ranking, capture, project bootstrap, repo mapping, vault connect/resolve, end-to-end loop, Claude Code installer.

## Credits

Plugin distribution pattern adapted from [obra/superpowers](https://github.com/obra/superpowers).
