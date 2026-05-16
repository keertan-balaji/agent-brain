# Obsidian Second Brain — Skill Expansion Design

**Date:** 2026-05-17
**Status:** Draft, awaiting user review
**Author:** keertan + Claude
**Predecessor:** `2026-05-17-obsidian-second-brain-skill-pack-design.md` (Phase 1 — shipped)

## Goal

Add 13 skills to the second-brain pack, across 4 phases, to close gaps discovered while building and using Phase 1. The new skills cover the storage routing decision (memory vs brain — used every time something is worth persisting), the session lifecycle (every session), vault quality and orientation (periodic), power-user navigation, and conveniences for maintaining the brain over time.

## Problem

Phase 1 shipped 5 skills covering setup, project bootstrap, repo mapping, recall, and capture. Using the pack in a real session surfaced gaps:

- **No routing decision between Claude Code's auto-memory and the Obsidian brain.** Both stores exist; the agent has no protocol for deciding which one a finding belongs to. The result: user preferences and feedback get captured as Obsidian decisions (wrong layer, slow recall, vault sprawl); project-specific architecture knowledge gets saved as auto-memory entries (wrong layer, not cross-agent, not cross-device). Both layers underperform.
- No support for daily/session logs, despite the `daily/` section in the vault and the original spec calling for one.
- No "what was I doing?" at session start — agents pay a cold-start tax on every session.
- After capture, adding `[[wikilinks]]` to related notes is documented but manual; the procedure is inconsistent in practice.
- `agent-memory/` accumulates indefinitely; nothing promotes good notes into `knowledge/`. Curation was specified but never built.
- No orientation skill: "show me what's active." Agents either spelunk or ask the user.
- No graph traversal: a single recall query misses notes one hop away.
- No vault-health audit: frontmatter drift, orphans, dead links can go unnoticed for weeks.
- No handoff format: sharing project context with a teammate or a second agent means concatenating files by hand.
- When `vault-template/_meta/*` conventions change in the skill-pack repo, the live vault doesn't pick up the update — we hand-copied 4 times this session alone.

## Non-goals

- Semantic / embedding search. Re-evaluate after Phase 4 if grep-based recall plateaus.
- A daemon, file watcher, or hooks-based auto-trigger system. Every skill is user- or agent-initiated.
- Importing from other note systems (Notion, Roam, Logseq).
- Multi-user concurrency or write locking. Obsidian Sync remains the cross-device transport.
- Touching files outside `Agent-Brain/`. The namespace boundary is preserved everywhere.

## Architecture

Unchanged from Phase 1. Each new skill follows the same shape:

```
skills/<name>/
├── SKILL.md          # agent-facing instructions (when + how)
└── scripts/
    └── <action>.sh   # deterministic helper called via Bash
tests/test-<name>.sh  # bash assertions covering the helper end-to-end
```

What's new is a tier of **shared helpers** at `skills/obsidian-setup/scripts/`, alongside the existing resolvers. Multiple new skills consume them, so building once buys leverage.

## Shared helpers

Three new helpers under `skills/obsidian-setup/scripts/`:

### `link-graph.sh <brain>`

Builds the link adjacency graph of the brain.

- **Input:** brain root path.
- **Output (stdout):** TSV, one edge per line: `<source-rel-path>\t<target-slug>`. `<source-rel-path>` is the file containing the link (relative to `<brain>`). `<target-slug>` is whatever appears inside `[[...]]` (without `.md`).
- **Implementation:** `rg -o -n -t md '\[\[[^]]+\]\]' <brain>`; strip surrounding `[[` `]]`; resolve source path. Treats `[[slug|display]]` and `[[slug#heading]]` correctly (target is the bare slug before `|` or `#`).
- **Cost:** runs once per skill invocation that needs it. ≤2s on a 1k-note brain.

**Consumers:** `obsidian-link` (find related candidates), `obsidian-curate` (count inbound links per note), `obsidian-graph-walk` (traverse), `obsidian-brain-health` (find orphans and dead links).

### `frontmatter-extract.sh <note> <key>`

Reads a single key out of a note's YAML frontmatter.

- **Input:** note path + key name.
- **Output (stdout):** value, with surrounding whitespace stripped. YAML arrays returned as raw bracketed text (`[a, b, c]`). Empty stdout if key absent. Exit code 0 in both cases.
- **Exit 1 only on:** missing file, or malformed frontmatter (no opening `---`).
- **Implementation:** awk over lines between the first two `---`, match `^<key>:`. Reuse pattern from `validate-frontmatter.sh`.

**Consumers:** `obsidian-curate` (read `status:`, `created:`), `obsidian-status` (filter by `status: active`), `obsidian-brain-health` (audit all required keys), `obsidian-link` (read `tags:`).

### `list-notes.sh <brain> [--type T] [--status S] [--newer-than-days N] [--project P]`

Filters notes by frontmatter criteria.

- **Input:** brain root, optional flags. Flags compose with AND.
- **Output (stdout):** paths of matching notes, one per line, absolute, sorted by mtime descending.
- **Implementation:** `find <brain> -name '*.md' -type f`, then `frontmatter-extract.sh` per file to read criteria. Cache-friendly because find is fast and extract is line-scoped.

**Consumers:** `obsidian-curate`, `obsidian-status`, `obsidian-brain-health`, `obsidian-handoff`.

## Templates

Two new templates under `vault-template/templates/`:

### `decision-adr.md`

ADR-style. Used by `obsidian-decide`.

```yaml
---
type: decision
tags: []
project:
status: active
created: {{date}}
updated: {{date}}
related: []
---
# {{title}}

## Context
[What forced this decision]

## Options considered

| Option | Pros | Cons |
|---|---|---|
|  |  |  |

## Choice

[Which option chosen]

## Consequences

[What this enables, rules out, things to revisit]

## References

- [[ ]]
```

### `handoff.md`

Generated by `obsidian-handoff`, never hand-edited. Frontmatter:

```yaml
---
type: project
tags: [handoff]
project: {{project}}
status: active
created: {{date}}
updated: {{date}}
related: []
---
# Handoff — {{project}} — {{date}}

## Goal
[from project index]

## Current state
[summary, last meaningful commits / captures]

## Decisions taken
- [[ ]]

## Open threads
- ...

## Where to read next
- [[index]]
- [[repo-map]]
- ...

## How to resume
[3-5 line walkthrough of how the next agent or teammate gets going]
```

## Skill specifications

### Phase 2 — Tier 1: routing + session lifecycle

#### `agent-store-decide`

The routing protocol between two persistence layers: Claude Code's auto-memory (at `~/.claude/projects/<sanitized-cwd>/memory/`) and the Obsidian brain (at `<vault>/Agent-Brain/`).

- **Trigger:** any time the agent recognizes something worth persisting beyond the current turn — a fact, a decision, a preference, a finding, an external pointer, a learning. Invoked **before** `obsidian-capture` or before writing to auto-memory.
- **Args:** brief description of the thing to persist (in plain text), optional hint about context.
- **Behavior:** runs a decision tree, returns a routing decision plus a one-sentence reason. No file writes of its own — the decision is consumed by the agent, which then calls the appropriate writer.

**Decision tree:**

```
About the user themselves (role, expertise, preferences, constraints)?
  → memory:user

User explicitly corrected approach or stated a preference?
  → memory:feedback

Project state, deadline, motivation, stakeholder, decision-context that decays in weeks?
  → memory:project

Pointer to an external system (Linear, Slack, dashboard URL, jira board)?
  → memory:reference

Domain term, internal API surface, architecture boundary, system glossary?
  → brain:knowledge   (gated — needs user approval, see write discipline)

Non-obvious technical decision with reasoning that another agent needs?
  → brain:decision

Surprise that took >5 min to diagnose, footgun, "looks simple but…"?
  → brain:gotcha

Reusable solution template across projects?
  → brain:pattern

Cross-device or cross-agent useful and >1 paragraph of structured content?
  → brain (pick the closest type above)

Trivial summary of what just happened, obvious from the diff?
  → discard

Hybrid (1-line fact for fast recall + full reasoning worth keeping)?
  → both   (memory:project for the fact, brain:decision for the body)
```

**Routing outputs (canonical):**

| Output | Where it goes | Writer |
|---|---|---|
| `memory:user` | `~/.claude/projects/<sanitized-cwd>/memory/` with `type: user` frontmatter | Write tool, per the auto-memory format |
| `memory:feedback` | Same dir, `type: feedback` | Write tool |
| `memory:project` | Same dir, `type: project` | Write tool |
| `memory:reference` | Same dir, `type: reference` | Write tool |
| `brain:decision` | `<brain>/agent-memory/decisions/YYYY-MM-DD-<slug>.md` | `obsidian-capture` |
| `brain:gotcha` | `<brain>/agent-memory/gotchas/YYYY-MM-DD-<slug>.md` | `obsidian-capture` |
| `brain:pattern` | proposed for `<brain>/knowledge/patterns/` (gated) | `obsidian-capture` (after user approves) |
| `brain:knowledge:<subtype>` | proposed for `<brain>/knowledge/<subtype>/` (gated) | `obsidian-capture` (after user approves) |
| `discard` | nowhere | none |
| `both` | both layers, with cross-reference: the memory entry mentions `Brain: [[<slug>]]`, the brain note mentions `Memory: <path>` | both |

**Key distinctions surfaced by the tree:**

| Property | Memory | Brain |
|---|---|---|
| About the user vs. about the project | user | project |
| Short fact (≤2 sentences worth) | yes | maybe |
| Structured + multi-paragraph | no | yes |
| Cross-device useful | no | yes (via Obsidian Sync) |
| Cross-agent useful | no | yes |
| Always-loaded into context cost-free | yes | no — agent has to recall |
| Decays in weeks (deadline, in-progress state) | yes | no |
| Code/architecture details | no | yes |
| Reusable across projects | no | yes |
| External system pointer | yes | no |

- **Helper:** none. The decision tree is markdown-only. `agent-store-decide/SKILL.md` is the entirety of the skill — the agent reads it, walks the tree, returns a routing string.
- **Why a skill and not a heuristic baked into capture:** the agent needs to consult this *before* deciding which write tool to invoke. Embedding it in `obsidian-capture` would skip auto-memory candidates entirely.
- **Anti-patterns:**
  - Capturing user preferences as `brain:decision` (route says `memory:feedback`).
  - Saving multi-paragraph architecture notes as `memory:project` (route says `brain:knowledge:architecture`, gated).
  - Skipping the decision entirely and writing to whichever layer feels closer.
  - Doubling up by default — `both` is for genuine cross-layer needs, not laziness.

#### `obsidian-session-log`

- **Trigger:** end of substantive work, user says "log this session", `/session-log`, or post-task summarization moments.
- **Args:** brain root, project name (optional, defaults to last-touched active project), summary text, plus structured items (files touched, decision-note paths, gotcha-note paths, open threads).
- **Behavior:**
  1. Locate `daily/YYYY-MM-DD.md`; create with frontmatter (`type: session`, `status: active`) if absent.
  2. Append a session block: `## HH:MM-HH:MM — <summary>` plus subsections for files, decisions (as `[[wikilinks]]` to capture notes), gotchas, open threads.
  3. Set `updated: <today>` in frontmatter.
- **Helper:** `session-log.sh <brain> <summary> [project=] [files=...] [decisions=...] [gotchas=...] [open-threads=...]`. Args accept comma-separated lists for the list fields.

#### `obsidian-session-resume`

- **Trigger:** session start (agent recognizes a fresh conversation in a familiar project), user says "what was I doing", `/session-resume`.
- **Args:** brain root, optional project filter.
- **Behavior:**
  1. Read latest 3 days of `daily/*.md`.
  2. Find projects with `status: active` (via `list-notes.sh --type project --status active`).
  3. List 5 most recent captures in `agent-memory/` by mtime.
  4. Synthesize a ≤500-token brief: active projects + last session highlights + recent captures.
- **Helper:** `session-resume.sh <brain> [project]`. Returns the brief on stdout.

#### `obsidian-link`

- **Trigger:** after capture, user says "link this note", `/obsidian-link <note-path>`.
- **Args:** brain root, note path.
- **Behavior:**
  1. Read note title (first H1) + `tags:` frontmatter + body's bare nouns.
  2. For each term, run `recall-search.sh` (capped to 3 hits per term).
  3. Cross-check against `link-graph.sh` to skip already-linked targets.
  4. Return ranked candidate slugs.
  5. Agent uses the Edit tool to add `[[slug]]` to the note's `Related` section + frontmatter `related:` list.
- **Helper:** `link-suggest.sh <brain> <note-path>`. Returns ranked slugs, one per line.

### Phase 3 — Tier 2: quality + orientation

#### `obsidian-curate`

- **Trigger:** periodic (user-invoked), `/curate`, or auto-suggest when `obsidian-status` reports a note with ≥3 inbound links still in `agent-memory/`.
- **Args:** brain root, optional `--age-days N` (default 30), `--min-inbound N` (default 3).
- **Behavior:**
  1. `list-notes.sh --status active` over `agent-memory/`.
  2. For each, count inbound links via `link-graph.sh`.
  3. Surface candidates meeting threshold (≥`min-inbound` OR `age >= --age-days`).
  4. Present candidate list with metadata: title, link count, age, suggested target `knowledge/<subdir>/`.
  5. **Human approves** each promotion individually.
  6. On approval: move to target, rewrite frontmatter (`status: promoted`, append `promoted: <date>`), update all inbound links to the new slug.
- **Helper:** `curate-candidates.sh <brain> [--age-days N] [--min-inbound N]` returns candidates. A second helper `promote-note.sh <brain> <source> <target-subdir>` does the move + rewrite.
- **Never** moves without explicit user approval. Always human-gated.

#### `obsidian-status`

- **Trigger:** session start when not explicitly resuming, user says "what's active", `/status`.
- **Args:** brain root.
- **Behavior:**
  1. List `status: active` projects (via `list-notes.sh`).
  2. Count captures in past 7 days (`list-notes.sh --newer-than-days 7`).
  3. List `daily/` entries in past 7 days.
  4. List `tasks/` dirs with unticked items (grep `- \[ \]` in `projects/*/tasks/*.md`).
  5. Render a compact dashboard, ≤400 tokens.
- **Helper:** `status.sh <brain>`. Pure read, no writes.

#### `obsidian-decide`

- **Trigger:** agent is about to make a non-trivial decision with multiple options worth weighing.
- **Args:** title, options array (each with pros/cons), choice, brain root, project.
- **Behavior:**
  1. Call `make-note.sh --template decision-adr <brain> decision <title> <tags> <project>`.
  2. Edit the resulting file to fill the Options table and Choice/Consequences sections.
  3. Validate frontmatter.
- **Helper:** extend `make-note.sh` to accept `--template <name>` overriding the type→template default map.
- **Why a separate skill:** the prompt-shape difference matters. `obsidian-decide` reminds the agent to enumerate options *before* committing to a choice. The vanilla `decision.md` template doesn't enforce that structure.

### Phase 4 — Tier 3: power features

#### `obsidian-graph-walk`

- **Trigger:** user says "what do we know about X and its connections", "/graph-walk `<slug>`", ambiguous concept needs expansion.
- **Args:** brain root, starting slug, optional `--hops N` (default 2).
- **Behavior:**
  1. Use `link-graph.sh` to build the brain graph once.
  2. BFS from starting note up to N hops.
  3. For each reached note, capture: title, hop distance, direction (forward / backward), first body line.
  4. Return slice as a markdown list, ≤500 tokens.
- **Helper:** `graph-walk.sh <brain> <slug> [--hops N]`. Returns the slice on stdout.

#### `obsidian-brain-health`

- **Trigger:** weekly, user says "audit the brain", `/health`.
- **Args:** brain root.
- **Behavior — checks:**
  1. **Frontmatter violators:** run `validate-frontmatter.sh` on every `.md` under brain. Count + list bad files.
  2. **Orphan notes:** notes with zero inbound links per `link-graph.sh` (excluding `_meta/`, daily entries, project indexes, repo maps).
  3. **Dead wikilinks:** `[[slug]]` references whose target file doesn't exist.
  4. **Stale active:** `status: active` notes older than 90 days (`list-notes.sh --status active --newer-than-days -90` inverted).
  5. **Sprawl signal:** `agent-memory/` byte-size vs. `knowledge/` byte-size ratio. Threshold for warning: agent-memory > 5x knowledge.
- **Output:** structured report, ≤600 tokens. No fixes applied — surfaces problems, user/agent acts.
- **Helper:** `health.sh <brain>`. Sole consumer of all three shared helpers.

#### `obsidian-handoff`

- **Trigger:** end of project, user says "/handoff <project>", or before sharing context with another agent / teammate.
- **Args:** brain root, project name.
- **Behavior:**
  1. Read `projects/<project>/index.md` → extract Goal section, frontmatter.
  2. `list-notes.sh --project <project>` → all captures linked to this project.
  3. From the index's frontmatter `related:` list, pull linked `knowledge/` notes.
  4. Concatenate using `templates/handoff.md` shape, save to `projects/<project>/handoff-<date>.md`.
- **Helper:** `handoff.sh <brain> <project>`. Returns the path of the generated handoff file.

### Phase 5 — Tier 4: convenience

#### `obsidian-refresh-map`

- **Trigger:** `/refresh-map`, repo structure visibly changed, periodic.
- **Args:** brain root, repo path.
- **Behavior:**
  1. Copy existing `projects/<repo>/repo-map.md` to `/tmp/repo-map-prev.md` if present.
  2. Run `map-repo.sh <brain> <repo-path> --force`.
  3. Diff old vs. new at the section level (Stack, Top-level layout, File counts).
  4. If diff is material (stack changed, ≥3 top-level entries changed, file-count category shift >20%), `make-note.sh` a `gotcha` describing the change.
- **Helper:** `refresh-map.sh <brain> <repo-path>`. Returns the new map path; logs diff summary to stderr.

#### `obsidian-template-add`

- **Trigger:** user says "add a template for X", `/template-add <name>`.
- **Args:** template name, type (matches `frontmatter-schema`), body skeleton (stdin or file).
- **Behavior:**
  1. Validate name is kebab-case and not already taken.
  2. Validate type is in the enumerated set.
  3. Write `vault-template/templates/<name>.md` with prefilled frontmatter (matching the schema) + body skeleton.
  4. Copy into live `Agent-Brain/templates/<name>.md`.
  5. Suggest the user run `obsidian-sync-conventions` to push across devices.
- **Helper:** `template-add.sh <name> <type> < body-file`. Updates both repo and live brain.
- **Does NOT** update `make-note.sh`'s type→template map; the new template is opt-in via `--template <name>`.

#### `obsidian-sync-conventions`

- **Trigger:** after editing files in `vault-template/_meta/` or `vault-template/templates/` in the skill-pack repo.
- **Args:** brain root.
- **Behavior:**
  1. For each file in `vault-template/_meta/` and `vault-template/templates/`:
     - Compare against the matching path in `<brain>/_meta/` or `<brain>/templates/`.
     - If different, show a unified diff.
     - Ask the user to confirm overwriting.
  2. Apply approved changes.
- **Helper:** `sync-conventions.sh <brain>`. Always asks before overwriting; never silent.
- **Why a skill, not a hook:** conventions changes are intentional and infrequent; gating on user input keeps the live brain stable.

## Repo layout additions

```
brain/
├── skills/
│   ├── agent-store-decide/SKILL.md                # NEW (no helper script — decision tree in markdown)
│   ├── obsidian-session-log/SKILL.md
│   ├── obsidian-session-log/scripts/session-log.sh
│   ├── obsidian-session-resume/SKILL.md
│   ├── obsidian-session-resume/scripts/session-resume.sh
│   ├── obsidian-link/SKILL.md
│   ├── obsidian-link/scripts/link-suggest.sh
│   ├── obsidian-curate/SKILL.md
│   ├── obsidian-curate/scripts/curate-candidates.sh
│   ├── obsidian-curate/scripts/promote-note.sh
│   ├── obsidian-status/SKILL.md
│   ├── obsidian-status/scripts/status.sh
│   ├── obsidian-decide/SKILL.md
│   ├── obsidian-graph-walk/SKILL.md
│   ├── obsidian-graph-walk/scripts/graph-walk.sh
│   ├── obsidian-brain-health/SKILL.md
│   ├── obsidian-brain-health/scripts/health.sh
│   ├── obsidian-handoff/SKILL.md
│   ├── obsidian-handoff/scripts/handoff.sh
│   ├── obsidian-refresh-map/SKILL.md
│   ├── obsidian-refresh-map/scripts/refresh-map.sh
│   ├── obsidian-template-add/SKILL.md
│   ├── obsidian-template-add/scripts/template-add.sh
│   ├── obsidian-sync-conventions/SKILL.md
│   ├── obsidian-sync-conventions/scripts/sync-conventions.sh
│   └── obsidian-setup/scripts/
│       ├── link-graph.sh            # NEW shared
│       ├── frontmatter-extract.sh   # NEW shared
│       └── list-notes.sh            # NEW shared
├── skills/obsidian-capture/scripts/make-note.sh    # MODIFIED: --template flag
├── vault-template/templates/decision-adr.md        # NEW
├── vault-template/templates/handoff.md             # NEW
└── tests/test-<each-new-skill>.sh                  # NEW: 12 test files
```

## Test plan

Each new skill ships with one bash test file. Coverage focus:

- **Shared helpers tested independently first** (`test-link-graph.sh`, `test-frontmatter-extract.sh`, `test-list-notes.sh`) — every skill test then trusts them.
- **Routing** (`test-agent-store-decide.sh`): since this skill is markdown-only, the test is a corpus of sample inputs (in `tests/store-decide-cases.tsv` — fact-description → expected routing) and a small bash driver that asks the agent's decision tree to map each input. The test validates the decision tree's *coverage* (every routing output is reachable by at least one input) and *consistency* (re-running on the same input returns the same routing). When the test fails because a real case routed wrong, the fix is: update the decision tree in `SKILL.md`, add the failing case to the corpus.
- **Session lifecycle** (`test-session-log.sh`, `test-session-resume.sh`, `test-link.sh`): create synthetic brain with daily entries + active projects + captures, run each helper, assert output shape and content.
- **Curate** (`test-curate.sh`): create notes with engineered inbound-link counts, verify the threshold logic surfaces correct candidates; verify `promote-note.sh` moves and rewrites inbound links correctly.
- **Status / health** (`test-status.sh`, `test-brain-health.sh`): plant known violators (missing frontmatter, dead links, orphans), assert report identifies them.
- **Graph-walk** (`test-graph-walk.sh`): build a known graph (A→B→C, A→D), assert BFS at hops=2 returns {B, C, D} with correct hop distances.
- **Handoff** (`test-handoff.sh`): set up a project with index + captures, generate handoff, assert all sections populated and validate frontmatter.
- **Refresh-map** (`test-refresh-map.sh`): map repo, modify structure, refresh, assert new map written and a gotcha captured if change material.
- **Template-add** (`test-template-add.sh`): assert template file written to both repo and live brain, frontmatter valid, name conflict rejected.
- **Sync-conventions** (`test-sync-conventions.sh`): plant a diff in `vault-template/_meta/AGENTS.md`, run sync, assert diff is reported and apply step requires confirmation (mock stdin yes/no).

End-to-end test extended to exercise a representative workflow: setup → bootstrap → map → recall → capture → link → session-log → session-resume.

## Phasing

Each phase ships as its own implementation plan after this spec is approved:

- **Phase 2 plan:** shared helpers (`link-graph.sh`, `frontmatter-extract.sh`, `list-notes.sh`) + Tier 1 skills (`agent-store-decide`, `session-log`, `session-resume`, `link`). `agent-store-decide` ships first in this phase because every subsequent capture is supposed to flow through it. End-to-end check: a full session loop routes, logs, and resumes correctly.
- **Phase 3 plan:** `curate`, `status`, `decide` + `decision-adr.md` template + `make-note.sh --template` flag.
- **Phase 4 plan:** `graph-walk`, `brain-health`, `handoff` + `handoff.md` template.
- **Phase 5 plan:** `refresh-map`, `template-add`, `sync-conventions`.

Each phase produces working, testable software on its own. Phase order is strict because Phase 2's shared helpers underpin Phases 3 and 4.

## Cross-platform impact

All new skills follow the existing convention: SKILL.md + bash + per-skill test. The other platform manifests (`.codex-plugin/`, `.cursor-plugin/`, `gemini-extension.json`) auto-discover skills from `skills/`, so each new skill is picked up by every platform without manifest edits. README updated to list the 17 total skills.

The `clients/agent-instructions.md` universal contract gets a one-paragraph addition under "When to write" pointing at the new lifecycle skills (`session-log` at session end, `session-resume` at session start), for agents without skill runtimes.

## Risks and mitigations

- **`link-graph.sh` performance** at scale. Mitigation: ripgrep is fast; 1k notes ≤2s on tested hardware. If a brain crosses 10k notes, add a simple cache file (mtime-keyed) — out of scope until that need is real.
- **`obsidian-link` false positives.** Noisy noun extraction could suggest unrelated notes. Mitigation: candidates returned ranked; agent gates which to actually add; user gates the agent.
- **`obsidian-curate` premature promotion.** Notes promoted too soon become unstable. Mitigation: human-gated, default threshold high (≥3 inbound OR >30 days active).
- **Frontmatter-extract YAML fragility.** Bash YAML parsing is brittle. Mitigation: we only handle the schema we own (flat key/value + bracketed arrays); reject malformed frontmatter at write time via `validate-frontmatter.sh`. Don't generalize.
- **`obsidian-sync-conventions` data loss.** Overwriting hand-edited `_meta/AGENTS.md` is destructive. Mitigation: always show diff; always require explicit confirmation; back up to `_meta/AGENTS.md.bak.<timestamp>` before overwrite.
- **`agent-store-decide` decision-tree drift.** As new use cases appear, the tree must evolve. Mitigation: every miss is added to the test corpus (`store-decide-cases.tsv`) as a regression case. The tree is short and lives in `SKILL.md`, so updates are fast and reviewable.
- **`agent-store-decide` bypass.** Agents may skip the skill and capture directly. Mitigation: the description on `obsidian-capture` explicitly says "If you have not just run `agent-store-decide`, run it first." Same for any direct auto-memory write described in the universal `agent-instructions.md`.

## Success criteria

1. `agent-store-decide` is invoked before every capture. Over a sample session, ≥80% of routing decisions match user judgment when audited (sample at least 10 captures).
2. Auto-memory entries are short, user/feedback/project/reference-typed, and don't duplicate brain content. Brain captures are project-scoped and structured. Each layer holds what belongs there.
3. `obsidian-session-resume` at the start of a fresh conversation in a known project delivers a ≤500-token brief that lets the agent skip "what was I doing?" round-trips with the user.
4. After 30 days of real use, `obsidian-curate` has surfaced ≥3 promotion candidates and ≥1 has been promoted to `knowledge/`.
5. `obsidian-brain-health` reports 0 frontmatter violators against any brain whose notes were all written via skills (enforcement at write time, not retroactive cleanup).
6. A second agent (Copilot, Cursor, etc.) given a project's `handoff-<date>.md` can resume work without contacting the originating agent or user.
7. After Phase 5, no manual `cp vault-template/...` commands are needed when conventions change in the skill-pack repo — `obsidian-sync-conventions` handles propagation.
8. Each new skill's test passes; all-tests harness stays under 30 seconds wall time.
