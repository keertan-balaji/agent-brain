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
/plugin marketplace add keertan/obsidian-second-brain
/plugin install obsidian-second-brain@obsidian-second-brain
```

Or, for local development (no GitHub round-trip), point the marketplace at the local clone:

```bash
/plugin marketplace add /home/keertan/codes/brain
/plugin install obsidian-second-brain@obsidian-second-brain
```

Symlink fallback (no marketplace, no plugin system):

```bash
bash clients/install-claude-code.sh
```

Then add the vault path to `~/.claude/settings.json` so native file tools reach it (auto-mode correctly blocks the agent from doing this for you):

```json
"permissions": { "additionalDirectories": ["/home/keertan/Documents/ObsidianVault"] }
```

### Codex CLI / Codex App

```bash
/plugins
# search "obsidian-second-brain", install
```

The repo includes `.codex-plugin/plugin.json` with the full Codex interface manifest.

### Cursor

In Cursor agent chat:

```
/add-plugin obsidian-second-brain
```

Or, for ambient instructions without the plugin runtime, drop the universal instructions file into the repo you're working in:

```bash
mkdir -p .cursor/rules
cp clients/agent-instructions.md .cursor/rules/obsidian-brain.mdc
```

### Gemini CLI

```bash
gemini extensions install https://github.com/keertan/obsidian-second-brain
gemini extensions update obsidian-second-brain   # to refresh later
```

### GitHub Copilot CLI

```bash
copilot plugin marketplace add keertan/obsidian-second-brain
copilot plugin install obsidian-second-brain@obsidian-second-brain
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

Phase 2 ships hybrid retrieval, parent-document chunking, Contextual Retrieval, provenance-aware ranking, 5 Fast-tier reasoning helpers, 4 new skills, and a tau-rolling-ratio health report.

Quick start (assumes Phase 1 already set up):

```bash
export BRAIN_ANTHROPIC_API_KEY=sk-ant-...
# Re-install deps to pull fastembed, sentence-transformers, anthropic, etc.
uv pip install -e ".[dev]"
# Models download on first use (~3GB total: BGE-M3 + mxbai-rerank)
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
