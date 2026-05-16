# Obsidian Second Brain — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working Claude Code skill pack at `/home/keertan/codes/brain/` that scaffolds an Obsidian vault and gives coding agents three skills — setup, recall, capture — for using that vault as persistent memory.

**Architecture:** Plain-markdown vault at `~/Documents/ObsidianVault/`. Agents read/write via native Read/Edit/Write/Grep tools (no MCP, no server). Skills are markdown files with YAML frontmatter under `skills/<name>/SKILL.md`. Supporting bash helpers under `skills/<name>/scripts/`. Vault structure and `_meta/AGENTS.md` are the cross-agent contract (Claude Code, Copilot, Cursor, etc.).

**Tech Stack:** Bash, ripgrep, Python 3 (only for YAML validation in tests via `python3 -c "import yaml"` — falls back to grep if pyyaml absent), Markdown, YAML frontmatter, git.

**Spec reference:** `docs/superpowers/specs/2026-05-17-obsidian-second-brain-skill-pack-design.md`

---

## File Structure

Files created in this phase:

```
brain/
├── README.md                                    # install + quick start
├── plugin.json                                  # Claude Code marketplace manifest
├── .gitignore
├── skills/
│   ├── obsidian-setup/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── scaffold-vault.sh
│   ├── obsidian-recall/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── recall-search.sh
│   └── obsidian-capture/
│       ├── SKILL.md
│       └── scripts/
│           ├── make-note.sh
│           └── validate-frontmatter.sh
├── vault-template/
│   ├── knowledge/{architecture,api,process,glossary,patterns}/.gitkeep
│   ├── agent-memory/{decisions,sessions,gotchas,prompts}/.gitkeep
│   ├── projects/.gitkeep
│   ├── daily/.gitkeep
│   ├── _meta/
│   │   ├── MOC.md
│   │   ├── AGENTS.md
│   │   ├── frontmatter-schema.md
│   │   └── linking-conventions.md
│   └── templates/
│       ├── decision.md
│       ├── session.md
│       ├── gotcha.md
│       ├── api-note.md
│       └── architecture.md
├── copilot/
│   ├── instructions.md                          # .github/copilot-instructions.md template
│   └── README.md
└── tests/
    ├── run-all.sh
    ├── test-scaffold.sh
    ├── test-frontmatter.sh
    ├── test-recall.sh
    ├── test-capture.sh
    └── test-end-to-end.sh
```

Each file has one clear responsibility:
- `SKILL.md` files are the agent-facing instructions.
- `scripts/*.sh` are the deterministic helpers skills call via Bash.
- `vault-template/` is copied verbatim by `obsidian-setup`.
- `tests/*.sh` are runnable bash assertions, no test framework needed.

---

## Task 1: Repo skeleton

**Files:**
- Create: `/home/keertan/codes/brain/README.md`
- Create: `/home/keertan/codes/brain/plugin.json`
- Create: `/home/keertan/codes/brain/.gitignore`
- Create: `/home/keertan/codes/brain/tests/run-all.sh`

- [ ] **Step 1: Write the failing test (run-all harness)**

Create `/home/keertan/codes/brain/tests/run-all.sh`:

```bash
#!/usr/bin/env bash
# Runs every test-*.sh script in this directory. Exits non-zero on any failure.
set -u
cd "$(dirname "$0")"
failed=0
shopt -s nullglob
for t in test-*.sh; do
  printf "=== %s ===\n" "$t"
  if bash "$t"; then
    printf "PASS: %s\n\n" "$t"
  else
    printf "FAIL: %s\n\n" "$t"
    failed=$((failed + 1))
  fi
done
if [ "$failed" -gt 0 ]; then
  printf "%d test file(s) failed\n" "$failed" >&2
  exit 1
fi
printf "all tests passed\n"
```

Make it executable: `chmod +x /home/keertan/codes/brain/tests/run-all.sh`

- [ ] **Step 2: Run harness to verify it handles empty dir**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: prints `all tests passed` and exits 0 (no test files yet — vacuously passes).

- [ ] **Step 3: Create plugin.json**

Write `/home/keertan/codes/brain/plugin.json`:

```json
{
  "name": "obsidian-second-brain",
  "version": "0.1.0",
  "description": "Skill pack that turns an Obsidian vault into a persistent second brain for coding agents. Filesystem-direct, no MCP, agent-agnostic.",
  "author": "keertan",
  "skills": [
    "skills/obsidian-setup",
    "skills/obsidian-recall",
    "skills/obsidian-capture"
  ]
}
```

- [ ] **Step 4: Create .gitignore**

Write `/home/keertan/codes/brain/.gitignore`:

```
*.tmp
*.bak
.DS_Store
node_modules/
__pycache__/
.tmp-vault/
```

- [ ] **Step 5: Create README.md**

Write `/home/keertan/codes/brain/README.md`:

```markdown
# Obsidian Second Brain

A Claude Code skill pack that turns an Obsidian vault into a persistent, organized second brain for coding agents. Filesystem-direct (no MCP server), agent-agnostic (Claude Code, GitHub Copilot, Cursor, etc.).

## What it does

Coding agents waste time and context every session rediscovering enterprise knowledge — architecture, APIs, process docs, prior decisions, recurring gotchas. This pack gives agents:

- A **structured vault** scaffolded at `~/Documents/ObsidianVault/` with sections for durable knowledge, agent working memory, per-project notes, and daily logs.
- **Skills** that tell agents *when* to recall context (before non-trivial work) and *how* to capture learnings (decisions, gotchas, patterns).
- **Cross-agent interop** via `_meta/AGENTS.md` — any agent with filesystem access can use the same vault.
- **Cross-device sync** by riding Obsidian Sync (you bring your own).

## Install

1. Clone this repo (any path is fine).
2. Symlink skills into Claude Code:
   ```bash
   ln -s "$(pwd)/skills/obsidian-setup" ~/.claude/skills/obsidian-setup
   ln -s "$(pwd)/skills/obsidian-recall" ~/.claude/skills/obsidian-recall
   ln -s "$(pwd)/skills/obsidian-capture" ~/.claude/skills/obsidian-capture
   ```
   Or add this repo to your Claude Code marketplace.
3. In Claude Code, run: `/obsidian-setup`
4. Done. Try `/obsidian-recall <topic>` and `/obsidian-capture <decision|gotcha|pattern>`.

## Skills

| Skill | When to use |
|---|---|
| `obsidian-setup` | First run; reconfigure vault path; verify install |
| `obsidian-recall` | Before non-trivial work; when topic mentioned; before brainstorming |
| `obsidian-capture` | After non-trivial decision; gotcha hit; pattern emerged |

## For other agents

Point GitHub Copilot, Cursor, Aider, etc. at `~/Documents/ObsidianVault/_meta/AGENTS.md`. That file is the cross-agent contract describing vault conventions. A copy of `copilot/instructions.md` can be dropped into any repo as `.github/copilot-instructions.md`.

## Design docs

- Spec: `docs/superpowers/specs/2026-05-17-obsidian-second-brain-skill-pack-design.md`
- Plan: `docs/superpowers/plans/2026-05-17-obsidian-second-brain-phase-1.md`

## Tests

```bash
bash tests/run-all.sh
```
```

- [ ] **Step 6: Init git, commit**

```bash
cd /home/keertan/codes/brain && git init && git add README.md plugin.json .gitignore tests/run-all.sh && git commit -m "chore: init obsidian second brain skill pack"
```

---

## Task 2: Vault template — directory tree

**Files:**
- Create: `vault-template/knowledge/{architecture,api,process,glossary,patterns}/.gitkeep`
- Create: `vault-template/agent-memory/{decisions,sessions,gotchas,prompts}/.gitkeep`
- Create: `vault-template/projects/.gitkeep`
- Create: `vault-template/daily/.gitkeep`
- Test: `tests/test-scaffold.sh` (partial — directory existence)

- [ ] **Step 1: Write the failing test**

Create `/home/keertan/codes/brain/tests/test-scaffold.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

required_dirs=(
  "vault-template/knowledge/architecture"
  "vault-template/knowledge/api"
  "vault-template/knowledge/process"
  "vault-template/knowledge/glossary"
  "vault-template/knowledge/patterns"
  "vault-template/agent-memory/decisions"
  "vault-template/agent-memory/sessions"
  "vault-template/agent-memory/gotchas"
  "vault-template/agent-memory/prompts"
  "vault-template/projects"
  "vault-template/daily"
  "vault-template/_meta"
  "vault-template/templates"
)
for d in "${required_dirs[@]}"; do
  if [ ! -d "$d" ]; then
    printf "missing dir: %s\n" "$d" >&2
    exit 1
  fi
done

required_files=(
  "vault-template/_meta/MOC.md"
  "vault-template/_meta/AGENTS.md"
  "vault-template/_meta/frontmatter-schema.md"
  "vault-template/_meta/linking-conventions.md"
  "vault-template/templates/decision.md"
  "vault-template/templates/session.md"
  "vault-template/templates/gotcha.md"
  "vault-template/templates/api-note.md"
  "vault-template/templates/architecture.md"
)
for f in "${required_files[@]}"; do
  if [ ! -f "$f" ]; then
    printf "missing file: %s\n" "$f" >&2
    exit 1
  fi
done

printf "scaffold ok\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: FAIL with `missing dir: vault-template/knowledge/architecture`

- [ ] **Step 3: Create vault template directory tree**

```bash
cd /home/keertan/codes/brain && \
mkdir -p vault-template/knowledge/{architecture,api,process,glossary,patterns} \
         vault-template/agent-memory/{decisions,sessions,gotchas,prompts} \
         vault-template/projects vault-template/daily \
         vault-template/_meta vault-template/templates && \
touch vault-template/knowledge/{architecture,api,process,glossary,patterns}/.gitkeep \
      vault-template/agent-memory/{decisions,sessions,gotchas,prompts}/.gitkeep \
      vault-template/projects/.gitkeep vault-template/daily/.gitkeep
```

(Files inside `_meta/` and `templates/` come in Tasks 3 and 4 — test still expected to fail at this step on those.)

- [ ] **Step 4: Confirm dirs created, files for _meta/templates still missing**

Run: `bash /home/keertan/codes/brain/tests/test-scaffold.sh`
Expected: FAIL with `missing file: vault-template/_meta/MOC.md` (dirs pass, files don't yet).

- [ ] **Step 5: Commit directory tree**

```bash
cd /home/keertan/codes/brain && git add vault-template/ tests/test-scaffold.sh && git commit -m "feat: scaffold vault-template directory tree"
```

---

## Task 3: Vault template — `_meta/` documentation

**Files:**
- Create: `vault-template/_meta/MOC.md`
- Create: `vault-template/_meta/AGENTS.md`
- Create: `vault-template/_meta/frontmatter-schema.md`
- Create: `vault-template/_meta/linking-conventions.md`

- [ ] **Step 1: Write `_meta/frontmatter-schema.md`**

Write `/home/keertan/codes/brain/vault-template/_meta/frontmatter-schema.md`:

```markdown
---
type: meta
tags: [schema, agents]
status: active
---

# Frontmatter schema

Every note in this vault must start with YAML frontmatter matching this schema:

```yaml
---
type: decision | session | gotcha | api | architecture | process | glossary | pattern | project | task | meta
tags: [list, of, kebab-case, tags]
project: <repo-name or null>
status: draft | active | archived | promoted
created: YYYY-MM-DD
updated: YYYY-MM-DD
related: ["[[other-note]]"]
---
```

## Required fields

- `type` — one of the enumerated values. Drives folder placement.
- `status` — `active` for current notes, `archived` for stale, `promoted` for memory→knowledge graduates.
- `created`, `updated` — ISO date.

## Optional fields

- `tags` — categorical, cross-cutting (`#performance`, `#auth`, `#legacy`).
- `project` — repo slug if note is project-scoped, else omit or `null`.
- `related` — list of `[[wikilinks]]` to relevant notes.
- `aliases` — list of alternative names; Obsidian honors these for autocomplete.

## Folder ↔ type mapping

| type | folder |
|---|---|
| decision | `agent-memory/decisions/` |
| session | `agent-memory/sessions/` or `daily/` |
| gotcha | `agent-memory/gotchas/` |
| api | `knowledge/api/` |
| architecture | `knowledge/architecture/` |
| process | `knowledge/process/` |
| glossary | `knowledge/glossary/` |
| pattern | `knowledge/patterns/` |
| project | `projects/<name>/` |
| task | `projects/<name>/tasks/` |
| meta | `_meta/` |
```

- [ ] **Step 2: Write `_meta/linking-conventions.md`**

Write `/home/keertan/codes/brain/vault-template/_meta/linking-conventions.md`:

```markdown
---
type: meta
tags: [conventions, agents]
status: active
---

# Linking conventions

## Wikilinks

Cross-note references use `[[note-name]]` — works in Obsidian and matchable via grep.

- `[[note-name]]` — links by filename slug (without `.md`).
- `[[note-name|display text]]` — link with custom display.
- `[[note-name#Heading]]` — link to a section.

Skills that follow links grep for the pattern `\[\[[^]]+\]\]`.

## Tags

`#kebab-case` for cross-cutting categories that span types/folders. Examples:

- `#performance`, `#security`, `#auth`, `#legacy`, `#external-api`, `#oncall`
- `#repo/<name>` for repo affinity when `project:` frontmatter is too coarse.

## File naming

- Kebab-case throughout.
- Time-ordered types (`decisions/`, `sessions/`, `gotchas/`, `daily/`) prefixed with date: `YYYY-MM-DD-<slug>.md`.
- Conceptual types (knowledge, glossary) prefer descriptive slugs without dates: `auth-token-rotation.md`.

## Aliases

When a concept has multiple names, list them in frontmatter:

```yaml
aliases: ["JWT rotation", "token refresh flow"]
```

Obsidian will resolve `[[JWT rotation]]` to the canonical note.
```

- [ ] **Step 3: Write `_meta/MOC.md`**

Write `/home/keertan/codes/brain/vault-template/_meta/MOC.md`:

```markdown
---
type: meta
tags: [moc, index]
status: active
---

# Map of Content

Top-level index of the vault. Hand-curated; updated when major sections evolve.

## Sections

- **knowledge/** — Curated, durable references.
  - [[knowledge/architecture]] — System diagrams, component boundaries
  - [[knowledge/api]] — External and internal API references
  - [[knowledge/process]] — Team rules, release flow, compliance
  - [[knowledge/glossary]] — Domain terms and project vocabulary
  - [[knowledge/patterns]] — Validated solutions and idioms

- **agent-memory/** — Working memory for agents. Grows freely; periodically curated.
  - decisions/ — Non-obvious choices with reasoning
  - sessions/ — Per-session notes
  - gotchas/ — Footguns and surprises
  - prompts/ — Reusable prompt fragments

- **projects/** — Per-repo workspace. One folder per codebase.

- **daily/** — Chronological session journal (`YYYY-MM-DD.md`).

- **_meta/** — Vault conventions (you are here).
  - [[AGENTS]] — How agents should use this vault
  - [[frontmatter-schema]] — Required fields per note type
  - [[linking-conventions]] — Wikilink and tag style

- **templates/** — Frontmatter-prefilled stubs new notes are copied from.

## Recently promoted

(Agents update this section when `obsidian-curate` promotes `agent-memory/` → `knowledge/`. Initially empty.)
```

- [ ] **Step 4: Write `_meta/AGENTS.md` — the cross-agent contract**

Write `/home/keertan/codes/brain/vault-template/_meta/AGENTS.md`:

```markdown
---
type: meta
tags: [agents, contract]
status: active
---

# Vault contract for AI coding agents

If you are an AI coding agent (Claude Code, GitHub Copilot, Cursor, Aider, etc.) with filesystem access to this vault, read this file first.

## Purpose

This vault is a persistent, organized second brain. Use it to recall context before non-trivial work, and to capture decisions, gotchas, and patterns at the end of substantive work. The goal is to *save* your context and the user's time — not to add bookkeeping.

## Read budget

Before reading anything, search. Before reading everything, read targeted.

- Use ripgrep (`rg`) or grep for keyword search across the vault.
- Rank search hits by path priority: `knowledge/` > `projects/<current-repo>/` > `agent-memory/` > `daily/`.
- Read at most 3–5 notes per recall round. If you need more, narrow the query.
- When summarizing for yourself or another agent, emit ≤500 tokens with note titles cited — never dump raw bodies.

## Write rules

- Write freely to `agent-memory/`, `projects/`, and `daily/`.
- **Do not** write to `knowledge/` directly. That section is human-curated. Notes graduate there via the `obsidian-curate` workflow.
- Every new note **must** start with the YAML frontmatter described in [[frontmatter-schema]].
- File names: kebab-case, `YYYY-MM-DD-<slug>.md` for time-ordered types.
- Add `[[wikilinks]]` to related notes. If the link target doesn't exist yet, that's fine — Obsidian shows orphan links and they signal future notes to write.

## When to write

Write at natural breakpoints, not on every turn:

- A non-obvious decision was made — `agent-memory/decisions/`.
- You hit a surprise that took >5 min to diagnose — `agent-memory/gotchas/`.
- You used a pattern you'd reach for again — eventually a candidate for `knowledge/patterns/` via curation.
- End of a substantive session — `daily/YYYY-MM-DD.md` append.

Avoid writing speculative notes ("might want to know"). Avoid summarizing what was already obvious from the diff.

## Concurrent edits

The user's Obsidian app may have the same file open. Mitigation:

- Before editing an existing note, check its mtime. If modified in the last 60 seconds, prefer append over overwrite, or wait.
- Never delete a note. Move to `agent-memory/_archive/` and leave a redirect note if necessary.

## Skills (Claude Code)

If you are Claude Code, three skills wrap these conventions:

- `obsidian-setup` — first-run vault scaffolding and config.
- `obsidian-recall` — search → rank → synthesize.
- `obsidian-capture` — pick template → fill frontmatter → write.

If you are not Claude Code, follow the conventions in this file directly using your native filesystem tools.
```

- [ ] **Step 5: Run scaffold test (still expected to fail on templates/)**

Run: `bash /home/keertan/codes/brain/tests/test-scaffold.sh`
Expected: FAIL with `missing file: vault-template/templates/decision.md` (all `_meta/` files now pass, templates not yet).

- [ ] **Step 6: Commit _meta files**

```bash
cd /home/keertan/codes/brain && git add vault-template/_meta/ && git commit -m "feat: add vault _meta docs (AGENTS contract, MOC, frontmatter schema, linking)"
```

---

## Task 4: Vault template — templates/

**Files:**
- Create: `vault-template/templates/decision.md`
- Create: `vault-template/templates/session.md`
- Create: `vault-template/templates/gotcha.md`
- Create: `vault-template/templates/api-note.md`
- Create: `vault-template/templates/architecture.md`

- [ ] **Step 1: Write `templates/decision.md`**

Write `/home/keertan/codes/brain/vault-template/templates/decision.md`:

```markdown
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

What was the situation that forced this decision?

## Decision

What was chosen.

## Reasoning

Why this over alternatives. Include the alternatives considered.

## Consequences

What this enables, what this rules out, what we'll have to revisit later.

## Related

- [[ ]]
```

- [ ] **Step 2: Write `templates/session.md`**

Write `/home/keertan/codes/brain/vault-template/templates/session.md`:

```markdown
---
type: session
tags: []
project:
status: active
created: {{date}}
updated: {{date}}
related: []
---

# Session — {{date}} — {{title}}

## Task

Brief: what was the goal.

## Files touched

- `path/to/file.ext`

## Decisions captured

- [[ ]]

## Gotchas captured

- [[ ]]

## Open threads

- Item to revisit next session.
```

- [ ] **Step 3: Write `templates/gotcha.md`**

Write `/home/keertan/codes/brain/vault-template/templates/gotcha.md`:

```markdown
---
type: gotcha
tags: []
project:
status: active
created: {{date}}
updated: {{date}}
related: []
---

# {{title}}

## Symptom

What looked wrong. Error message, unexpected behavior, surprising result.

## Cause

Root cause once found.

## Fix

What unblocked it.

## Lesson

The rule of thumb to remember. Why future-you should care.

## Related

- [[ ]]
```

- [ ] **Step 4: Write `templates/api-note.md`**

Write `/home/keertan/codes/brain/vault-template/templates/api-note.md`:

```markdown
---
type: api
tags: []
project:
status: active
created: {{date}}
updated: {{date}}
related: []
aliases: []
---

# {{title}}

## Endpoint / surface

`METHOD /path` or function signature.

## Purpose

What it does in one sentence.

## Inputs

| Name | Type | Required | Notes |
|---|---|---|---|

## Outputs

Shape of the response or return value.

## Errors / edge cases

- Code or condition — what triggers it, what to do.

## Examples

```text
example request / call
```

## Related

- [[ ]]
```

- [ ] **Step 5: Write `templates/architecture.md`**

Write `/home/keertan/codes/brain/vault-template/templates/architecture.md`:

```markdown
---
type: architecture
tags: []
project:
status: active
created: {{date}}
updated: {{date}}
related: []
---

# {{title}}

## Overview

System or component in one paragraph.

## Components

- **Component** — responsibility, boundary, key files.

## Data flow

How data moves through the system. Include a diagram if useful.

## Interfaces

External APIs, message contracts, file formats this component exposes or consumes.

## Constraints

Non-functional requirements, perf targets, deployment limits.

## Related

- [[ ]]
```

- [ ] **Step 6: Run scaffold test**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: PASS — `scaffold ok` and `all tests passed`.

- [ ] **Step 7: Commit templates**

```bash
cd /home/keertan/codes/brain && git add vault-template/templates/ && git commit -m "feat: add note templates (decision, session, gotcha, api-note, architecture)"
```

---

## Task 5: Frontmatter validator + test

**Files:**
- Create: `skills/obsidian-capture/scripts/validate-frontmatter.sh`
- Create: `tests/test-frontmatter.sh`

The validator is used by the capture skill and is the easiest piece to write/test in isolation, so we build it before the skills.

- [ ] **Step 1: Write the failing test**

Create `/home/keertan/codes/brain/tests/test-frontmatter.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

VALIDATOR=skills/obsidian-capture/scripts/validate-frontmatter.sh

if [ ! -x "$VALIDATOR" ]; then
  printf "validator not executable: %s\n" "$VALIDATOR" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Case 1: valid note passes
cat > "$tmp/good.md" <<'EOF'
---
type: decision
tags: [auth]
project: brain
status: active
created: 2026-05-17
updated: 2026-05-17
related: []
---
# Body
EOF
if ! bash "$VALIDATOR" "$tmp/good.md" >/dev/null 2>&1; then
  printf "valid note rejected\n" >&2; exit 1
fi

# Case 2: missing required field
cat > "$tmp/missing-status.md" <<'EOF'
---
type: decision
tags: [auth]
created: 2026-05-17
updated: 2026-05-17
---
# Body
EOF
if bash "$VALIDATOR" "$tmp/missing-status.md" >/dev/null 2>&1; then
  printf "missing-status not detected\n" >&2; exit 1
fi

# Case 3: invalid type
cat > "$tmp/bad-type.md" <<'EOF'
---
type: notathing
tags: []
status: active
created: 2026-05-17
updated: 2026-05-17
---
# Body
EOF
if bash "$VALIDATOR" "$tmp/bad-type.md" >/dev/null 2>&1; then
  printf "invalid type not detected\n" >&2; exit 1
fi

# Case 4: no frontmatter at all
printf '# just a body\n' > "$tmp/none.md"
if bash "$VALIDATOR" "$tmp/none.md" >/dev/null 2>&1; then
  printf "no-frontmatter not detected\n" >&2; exit 1
fi

printf "frontmatter validator ok\n"
```

- [ ] **Step 2: Run test, confirm fails**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: FAIL with `validator not executable: skills/obsidian-capture/scripts/validate-frontmatter.sh`

- [ ] **Step 3: Write the validator**

Create directories and write `/home/keertan/codes/brain/skills/obsidian-capture/scripts/validate-frontmatter.sh`:

```bash
#!/usr/bin/env bash
# validate-frontmatter.sh <path-to-note.md>
# Exits 0 if frontmatter is present and contains all required fields with valid type. Exits 1 otherwise.
# Prints diagnostics to stderr.

set -uo pipefail

file=${1:-}
if [ -z "$file" ] || [ ! -f "$file" ]; then
  printf "usage: %s <note.md>\n" "$0" >&2
  exit 1
fi

# Frontmatter must start at line 1 with '---' and close with another '---'.
if ! head -n1 "$file" | grep -q '^---$'; then
  printf "no opening frontmatter delimiter in %s\n" "$file" >&2
  exit 1
fi

# Extract frontmatter (lines between the first two '---').
fm=$(awk '
  BEGIN { in_fm = 0; count = 0 }
  /^---$/ { count++; if (count == 1) { in_fm = 1; next } else if (count == 2) { in_fm = 0; exit } }
  in_fm { print }
' "$file")

if [ -z "$fm" ]; then
  printf "empty frontmatter in %s\n" "$file" >&2
  exit 1
fi

# Required keys.
for key in type status created updated; do
  if ! printf '%s\n' "$fm" | grep -qE "^${key}:"; then
    printf "missing required key '%s' in %s\n" "$key" "$file" >&2
    exit 1
  fi
done

# Validate type is one of the allowed values.
type_value=$(printf '%s\n' "$fm" | grep -E '^type:' | head -n1 | sed -E 's/^type:[[:space:]]*//; s/[[:space:]]+$//')
case "$type_value" in
  decision|session|gotcha|api|architecture|process|glossary|pattern|project|task|meta) ;;
  *)
    printf "invalid type '%s' in %s\n" "$type_value" "$file" >&2
    exit 1
    ;;
esac

# Validate status is one of the allowed values.
status_value=$(printf '%s\n' "$fm" | grep -E '^status:' | head -n1 | sed -E 's/^status:[[:space:]]*//; s/[[:space:]]+$//')
case "$status_value" in
  draft|active|archived|promoted) ;;
  *)
    printf "invalid status '%s' in %s\n" "$status_value" "$file" >&2
    exit 1
    ;;
esac

# Validate dates look like YYYY-MM-DD.
for key in created updated; do
  v=$(printf '%s\n' "$fm" | grep -E "^${key}:" | head -n1 | sed -E "s/^${key}:[[:space:]]*//; s/[[:space:]]+$//")
  if ! printf '%s' "$v" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
    printf "invalid %s date '%s' in %s\n" "$key" "$v" "$file" >&2
    exit 1
  fi
done

exit 0
```

Make executable: `chmod +x /home/keertan/codes/brain/skills/obsidian-capture/scripts/validate-frontmatter.sh`

- [ ] **Step 4: Run test, confirm passes**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: PASS — `frontmatter validator ok`.

- [ ] **Step 5: Commit**

```bash
cd /home/keertan/codes/brain && git add skills/obsidian-capture/scripts/validate-frontmatter.sh tests/test-frontmatter.sh && git commit -m "feat: add frontmatter validator with tests"
```

---

## Task 6: `obsidian-setup` skill — scaffold script

**Files:**
- Create: `skills/obsidian-setup/scripts/scaffold-vault.sh`
- Modify: `tests/test-scaffold.sh` (add scaffold-script integration check)

- [ ] **Step 1: Extend test to cover scaffold-vault.sh behavior**

Append to `/home/keertan/codes/brain/tests/test-scaffold.sh` (after the existing `printf "scaffold ok\n"` line, replace it with):

```bash
# --- scaffold-vault.sh integration check ---
SCAFFOLD=skills/obsidian-setup/scripts/scaffold-vault.sh
if [ ! -x "$SCAFFOLD" ]; then
  printf "scaffold script missing: %s\n" "$SCAFFOLD" >&2
  exit 1
fi

tmpvault=$(mktemp -d)
trap 'rm -rf "$tmpvault"' EXIT

if ! bash "$SCAFFOLD" "$tmpvault" >/dev/null 2>&1; then
  printf "scaffold-vault.sh failed on empty dir\n" >&2
  exit 1
fi

for d in knowledge/architecture agent-memory/decisions projects daily _meta templates; do
  if [ ! -d "$tmpvault/$d" ]; then
    printf "scaffold missing dir: %s\n" "$d" >&2; exit 1
  fi
done
for f in _meta/AGENTS.md _meta/MOC.md _meta/frontmatter-schema.md _meta/linking-conventions.md templates/decision.md; do
  if [ ! -f "$tmpvault/$f" ]; then
    printf "scaffold missing file: %s\n" "$f" >&2; exit 1
  fi
done

# Idempotency: re-running on existing vault must not error and must not duplicate or overwrite user files.
echo "user content" > "$tmpvault/_meta/AGENTS.md"
if ! bash "$SCAFFOLD" "$tmpvault" >/dev/null 2>&1; then
  printf "scaffold-vault.sh failed on existing vault\n" >&2; exit 1
fi
if ! grep -q "user content" "$tmpvault/_meta/AGENTS.md"; then
  printf "scaffold overwrote existing _meta/AGENTS.md\n" >&2; exit 1
fi

printf "scaffold ok\n"
```

(Replace the final `printf "scaffold ok\n"` line of the existing file with the block above so the new checks run after the existing required_dirs/required_files loops.)

- [ ] **Step 2: Run test, confirm fails**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: FAIL with `scaffold script missing: skills/obsidian-setup/scripts/scaffold-vault.sh`

- [ ] **Step 3: Write scaffold-vault.sh**

Create `/home/keertan/codes/brain/skills/obsidian-setup/scripts/scaffold-vault.sh`:

```bash
#!/usr/bin/env bash
# scaffold-vault.sh <vault-path>
# Idempotently scaffolds an Obsidian vault: creates required dirs and copies vault-template/* into target.
# Existing files are preserved.

set -euo pipefail

vault=${1:-}
if [ -z "$vault" ]; then
  printf "usage: %s <vault-path>\n" "$0" >&2
  exit 1
fi

# Locate vault-template relative to this script.
script_dir=$(cd "$(dirname "$0")" && pwd)
template_dir=$(cd "$script_dir/../../../vault-template" 2>/dev/null && pwd) || {
  printf "vault-template not found relative to script at %s\n" "$script_dir" >&2
  exit 1
}

mkdir -p "$vault"

# Create directory structure first.
for d in \
  knowledge/architecture knowledge/api knowledge/process knowledge/glossary knowledge/patterns \
  agent-memory/decisions agent-memory/sessions agent-memory/gotchas agent-memory/prompts \
  projects daily _meta templates; do
  mkdir -p "$vault/$d"
done

# Copy template files without overwriting user edits.
copied=0
skipped=0
while IFS= read -r -d '' src; do
  rel=${src#"$template_dir/"}
  # Skip .gitkeep files — directories already created above.
  if [ "$(basename "$rel")" = ".gitkeep" ]; then
    continue
  fi
  dst="$vault/$rel"
  if [ -e "$dst" ]; then
    skipped=$((skipped + 1))
    continue
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  copied=$((copied + 1))
done < <(find "$template_dir" -type f -print0)

printf "vault scaffolded at %s (copied=%d skipped=%d)\n" "$vault" "$copied" "$skipped"
```

Make executable: `chmod +x /home/keertan/codes/brain/skills/obsidian-setup/scripts/scaffold-vault.sh`

- [ ] **Step 4: Run test, confirm passes**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: PASS — all tests including `scaffold ok` and `frontmatter validator ok`.

- [ ] **Step 5: Commit**

```bash
cd /home/keertan/codes/brain && git add skills/obsidian-setup/scripts/scaffold-vault.sh tests/test-scaffold.sh && git commit -m "feat: scaffold-vault.sh creates/repairs vault idempotently"
```

---

## Task 7: `obsidian-setup` skill — SKILL.md

**Files:**
- Create: `skills/obsidian-setup/SKILL.md`

- [ ] **Step 1: Write `skills/obsidian-setup/SKILL.md`**

Create `/home/keertan/codes/brain/skills/obsidian-setup/SKILL.md`:

````markdown
---
name: obsidian-setup
description: Use when the user wants to install or repair the Obsidian second-brain vault, when no vault exists at the configured path, or when other obsidian-* skills fail with "vault not found". Idempotent — safe to run repeatedly.
---

# obsidian-setup

Set up or repair the Obsidian vault used by the second-brain skill pack.

## When to use

- User runs `/obsidian-setup`, says "set up brain", or first-runs the pack.
- Another `obsidian-*` skill fails because the vault directory doesn't exist or is incomplete.
- The user changed vault location and wants to re-bootstrap.

## What it does

1. Determine vault path. Default: `$HOME/Documents/ObsidianVault/`. Honors `OBSIDIAN_VAULT` env var or a path the user supplies.
2. Run `scaffold-vault.sh <path>`. Creates required directory tree. Copies template files (AGENTS.md, MOC.md, schema, linking conventions, note templates) only where missing — never overwrites existing files.
3. Ensure the vault path is in Claude Code's `additionalDirectories` so Read/Edit/Write/Grep can reach it.
4. Verify by running the frontmatter validator on `_meta/AGENTS.md`.
5. Report path, files copied vs skipped, and next-step suggestions.

## How

### Step 1 — pick the path

```bash
VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/ObsidianVault}"
```

If the user named a different path, use that. Otherwise the default.

### Step 2 — scaffold

Run from this repo root:

```bash
bash skills/obsidian-setup/scripts/scaffold-vault.sh "$VAULT"
```

Expect output of the form `vault scaffolded at <path> (copied=N skipped=M)`.

### Step 3 — wire Claude Code permissions

Read `~/.claude/settings.json`. If the `additionalDirectories` array does not include the vault path, add it. Preserve existing keys and array entries. If the file does not exist, create it with the minimal shape:

```json
{
  "additionalDirectories": ["<vault-path>"]
}
```

Always re-read before write and merge — never blindly overwrite. If `permissions` or other top-level keys exist, leave them untouched.

### Step 4 — verify

```bash
bash skills/obsidian-capture/scripts/validate-frontmatter.sh "$VAULT/_meta/AGENTS.md"
```

Exit 0 = vault is healthy.

### Step 5 — report

Tell the user:
- vault path
- copied / skipped counts
- next suggested skills: `obsidian-recall <topic>` and `obsidian-capture <type>`

## Don't

- Don't overwrite user-edited files. The scaffold script handles this; trust it.
- Don't write into `knowledge/` — that's human-curated.
- Don't pre-populate seed notes beyond what `vault-template/` ships. Vault sprawl starts here.
- Don't add the vault path to `additionalDirectories` more than once — check before append.
````

- [ ] **Step 2: Verify SKILL.md frontmatter parses**

Run: `bash /home/keertan/codes/brain/skills/obsidian-capture/scripts/validate-frontmatter.sh /dev/stdin <<'EOF'
---
type: meta
tags: [test]
status: active
created: 2026-05-17
updated: 2026-05-17
---
EOF`

Expected: exit 0 (sanity check the validator itself; SKILL.md uses skill-flavored frontmatter, not vault-flavored, so we don't validate it directly).

- [ ] **Step 3: Commit**

```bash
cd /home/keertan/codes/brain && git add skills/obsidian-setup/SKILL.md && git commit -m "feat: obsidian-setup SKILL.md describing scaffold + permissions flow"
```

---

## Task 8: `obsidian-recall` skill — search helper

**Files:**
- Create: `skills/obsidian-recall/scripts/recall-search.sh`
- Create: `tests/test-recall.sh`

- [ ] **Step 1: Write the failing test**

Create `/home/keertan/codes/brain/tests/test-recall.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

SCRIPT=skills/obsidian-recall/scripts/recall-search.sh
if [ ! -x "$SCRIPT" ]; then
  printf "recall script missing: %s\n" "$SCRIPT" >&2
  exit 1
fi

if ! command -v rg >/dev/null 2>&1; then
  printf "ripgrep not installed — install with: sudo pacman -S ripgrep\n" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Seed a fake vault.
mkdir -p "$tmp/knowledge/architecture" "$tmp/agent-memory/decisions" "$tmp/projects/foo" "$tmp/daily"
cat > "$tmp/knowledge/architecture/auth.md" <<'EOF'
---
type: architecture
status: active
created: 2026-05-01
updated: 2026-05-01
---
# Auth subsystem
Uses JWT rotation every 15 minutes.
EOF
cat > "$tmp/agent-memory/decisions/2026-05-10-jwt-store.md" <<'EOF'
---
type: decision
status: active
created: 2026-05-10
updated: 2026-05-10
---
# Decided to store JWT keys in redis
EOF
cat > "$tmp/projects/foo/index.md" <<'EOF'
---
type: project
status: active
created: 2026-05-15
updated: 2026-05-15
---
# foo project
EOF

# Run recall — should return hits ordered: knowledge first, then agent-memory, then projects.
out=$(bash "$SCRIPT" "$tmp" "JWT")
if [ -z "$out" ]; then
  printf "no output from recall\n" >&2; exit 1
fi

first=$(printf '%s\n' "$out" | head -n1)
if ! printf '%s' "$first" | grep -q 'knowledge/architecture/auth.md'; then
  printf "expected knowledge/ first, got: %s\n" "$first" >&2
  exit 1
fi

# Should include the agent-memory hit too.
if ! printf '%s\n' "$out" | grep -q 'agent-memory/decisions/2026-05-10-jwt-store.md'; then
  printf "missing agent-memory hit\n" >&2; exit 1
fi

# Should NOT match the project note since query was JWT.
if printf '%s\n' "$out" | grep -q 'projects/foo/index.md'; then
  printf "unexpected projects hit for JWT query\n" >&2; exit 1
fi

# Max 5 hits by default.
many=$(printf '%s\n' "$out" | wc -l)
if [ "$many" -gt 5 ]; then
  printf "too many hits (%d > 5)\n" "$many" >&2; exit 1
fi

printf "recall search ok\n"
```

- [ ] **Step 2: Run test, confirm fails**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: FAIL with `recall script missing`.

- [ ] **Step 3: Check ripgrep is available**

Run: `command -v rg && rg --version | head -n1`
Expected: prints rg version. If missing: `sudo pacman -S ripgrep` (Arch).

- [ ] **Step 4: Write recall-search.sh**

Create `/home/keertan/codes/brain/skills/obsidian-recall/scripts/recall-search.sh`:

```bash
#!/usr/bin/env bash
# recall-search.sh <vault-path> <query> [max-hits]
# Searches vault for query, ranks by section priority, prints up to max-hits paths to stdout.
# Output: one absolute path per line, ordered by priority.
# Priority: knowledge/ > projects/ > agent-memory/ > daily/ > everything else.

set -euo pipefail

vault=${1:-}
query=${2:-}
max=${3:-5}

if [ -z "$vault" ] || [ -z "$query" ]; then
  printf "usage: %s <vault-path> <query> [max-hits]\n" "$0" >&2
  exit 1
fi

if [ ! -d "$vault" ]; then
  printf "vault not found: %s\n" "$vault" >&2
  exit 1
fi

# Collect files-with-matches; rg is case-insensitive and limited to .md.
matches=$(rg --files-with-matches --type md --ignore-case --fixed-strings -- "$query" "$vault" 2>/dev/null || true)

if [ -z "$matches" ]; then
  exit 0
fi

# Score each path by section.
score_path() {
  local p=$1
  case "$p" in
    */knowledge/*) printf "0\t%s\n" "$p" ;;
    */projects/*)  printf "1\t%s\n" "$p" ;;
    */agent-memory/*) printf "2\t%s\n" "$p" ;;
    */daily/*) printf "3\t%s\n" "$p" ;;
    *) printf "4\t%s\n" "$p" ;;
  esac
}

while IFS= read -r line; do
  score_path "$line"
done <<< "$matches" | sort -k1,1n -k2,2 | cut -f2- | head -n "$max"
```

Make executable: `chmod +x /home/keertan/codes/brain/skills/obsidian-recall/scripts/recall-search.sh`

- [ ] **Step 5: Run test, confirm passes**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: PASS — `recall search ok` plus all earlier tests.

- [ ] **Step 6: Commit**

```bash
cd /home/keertan/codes/brain && git add skills/obsidian-recall/scripts/recall-search.sh tests/test-recall.sh && git commit -m "feat: recall-search ranks vault hits by section priority"
```

---

## Task 9: `obsidian-recall` skill — SKILL.md

**Files:**
- Create: `skills/obsidian-recall/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Create `/home/keertan/codes/brain/skills/obsidian-recall/SKILL.md`:

````markdown
---
name: obsidian-recall
description: Use BEFORE starting non-trivial work, when the user mentions a feature/module/concept that may be documented, or before brainstorming/implementation. Searches the Obsidian vault and returns a synthesized brief (≤500 tokens) — never dumps raw note bodies. Replaces ad-hoc grep + Read sprees that burn context.
---

# obsidian-recall

Pull just-enough context from the vault before working.

## When to use

- Start of any non-trivial task — *before* you read code.
- User says: "what do we know about X", "is there a doc for Y", "have we decided about Z".
- Before invoking `superpowers:brainstorming` or `superpowers:writing-plans` on a topic the vault might cover.
- A concept appears in the conversation that you don't have full context for.

## When NOT to use

- The query is about the *current* file or current diff — read those directly.
- The vault is brand new and obviously empty — run `obsidian-setup` instead.
- You already pulled vault context for the same topic this session.

## What it does

1. Resolves vault path from `$OBSIDIAN_VAULT` or defaults to `$HOME/Documents/ObsidianVault`.
2. Calls `recall-search.sh <vault> <query>` to get up to 5 paths ranked by section priority (knowledge > projects > agent-memory > daily).
3. Reads each hit (using the Read tool).
4. Emits a synthesis with this shape, in ≤500 tokens:

   ```
   Vault recall — "<query>"
   - **[note title]** (`<path>`): one-sentence claim or finding.
   - …
   No-hits sections (so the user knows): <list>
   ```

5. If zero hits: emit `No vault notes for "<query>"` and proceed; suggest `obsidian-capture` once a finding emerges.

## How

### Step 1 — resolve vault

```bash
VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/ObsidianVault}"
```

### Step 2 — search

From the brain repo root:

```bash
bash skills/obsidian-recall/scripts/recall-search.sh "$VAULT" "<query>"
```

Use `<query>` as a fixed string. For multi-word queries, quote them. If you need broader matching, run multiple queries with the key terms separately and merge.

### Step 3 — read selectively

Use the Read tool on each returned path. Cap at 5 files. If a file is large, read with `limit` to stay tight.

### Step 4 — synthesize

Produce a single brief, ≤500 tokens, formatted as above. Cite source paths. Do not paste raw bodies. If a note is critical and the user will want the full body, say "Read `<path>` for full content" — don't pre-emptively dump it.

## Anti-patterns

- ❌ Dumping every matched note body inline.
- ❌ Running `rg` against the vault directly when this script exists — you lose priority ranking.
- ❌ Recalling on every turn — recall once per topic per session.
- ❌ Falling back to web search before checking the vault.

## Related skills

- `obsidian-capture` — write findings back so the next recall pays off.
- `obsidian-setup` — fix "vault not found".
````

- [ ] **Step 2: Commit**

```bash
cd /home/keertan/codes/brain && git add skills/obsidian-recall/SKILL.md && git commit -m "feat: obsidian-recall SKILL.md with budget rules and anti-patterns"
```

---

## Task 10: `obsidian-capture` skill — make-note helper

**Files:**
- Create: `skills/obsidian-capture/scripts/make-note.sh`
- Create: `tests/test-capture.sh`

- [ ] **Step 1: Write the failing test**

Create `/home/keertan/codes/brain/tests/test-capture.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

SCRIPT=skills/obsidian-capture/scripts/make-note.sh
VALIDATOR=skills/obsidian-capture/scripts/validate-frontmatter.sh

if [ ! -x "$SCRIPT" ]; then
  printf "make-note script missing\n" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# Seed a vault skeleton (just the dirs make-note will write into).
mkdir -p "$tmp/agent-memory/decisions" "$tmp/agent-memory/gotchas" "$tmp/templates"
# Provide a minimal template the script will read.
cat > "$tmp/templates/decision.md" <<'EOF'
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
EOF

# Case 1: create a decision note
out=$(bash "$SCRIPT" "$tmp" decision "Use redis for jwt store" "auth,security" "brain")
if [ -z "$out" ]; then printf "no output\n" >&2; exit 1; fi
path=$(printf '%s' "$out" | tr -d '\n')
if [ ! -f "$path" ]; then printf "note not created at %s\n" "$path" >&2; exit 1; fi
case "$path" in
  *agent-memory/decisions/*-use-redis-for-jwt-store.md) ;;
  *) printf "unexpected path: %s\n" "$path" >&2; exit 1 ;;
esac

# Validates against the frontmatter validator.
if ! bash "$VALIDATOR" "$path" >/dev/null 2>&1; then
  printf "generated note failed validation\n" >&2
  cat "$path" >&2
  exit 1
fi

# Tags and title made it in.
grep -q "tags: \[auth, security\]" "$path" || { printf "tags missing\n" >&2; cat "$path" >&2; exit 1; }
grep -q "Use redis for jwt store" "$path" || { printf "title missing\n" >&2; cat "$path" >&2; exit 1; }
grep -q "project: brain" "$path" || { printf "project missing\n" >&2; cat "$path" >&2; exit 1; }

# Case 2: invalid type rejected
if bash "$SCRIPT" "$tmp" notathing "x" "" "" >/dev/null 2>&1; then
  printf "invalid type accepted\n" >&2; exit 1
fi

# Case 3: missing title rejected
if bash "$SCRIPT" "$tmp" decision "" "" "" >/dev/null 2>&1; then
  printf "empty title accepted\n" >&2; exit 1
fi

printf "capture make-note ok\n"
```

- [ ] **Step 2: Run test, confirm fails**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: FAIL with `make-note script missing`.

- [ ] **Step 3: Write make-note.sh**

Create `/home/keertan/codes/brain/skills/obsidian-capture/scripts/make-note.sh`:

```bash
#!/usr/bin/env bash
# make-note.sh <vault> <type> <title> [tags-csv] [project]
# Creates a new note from the matching template in <vault>/templates/, fills frontmatter,
# writes to the correct folder under the vault. Prints the absolute path of the created note.

set -euo pipefail

vault=${1:-}
ntype=${2:-}
title=${3:-}
tags_csv=${4:-}
project=${5:-}

usage() {
  printf "usage: %s <vault> <type> <title> [tags-csv] [project]\n" "$0" >&2
  printf "  type: decision|session|gotcha|api|architecture|process|glossary|pattern|task\n" >&2
}

if [ -z "$vault" ] || [ -z "$ntype" ] || [ -z "$title" ]; then
  usage; exit 1
fi
if [ ! -d "$vault" ]; then
  printf "vault not found: %s\n" "$vault" >&2; exit 1
fi

# Type → folder
case "$ntype" in
  decision)     folder="agent-memory/decisions"; dated=1 ;;
  session)      folder="agent-memory/sessions";  dated=1 ;;
  gotcha)       folder="agent-memory/gotchas";   dated=1 ;;
  api)          folder="knowledge/api";          dated=0 ;;
  architecture) folder="knowledge/architecture"; dated=0 ;;
  process)      folder="knowledge/process";      dated=0 ;;
  glossary)     folder="knowledge/glossary";     dated=0 ;;
  pattern)      folder="knowledge/patterns";     dated=0 ;;
  task)
    if [ -z "$project" ]; then
      printf "task type requires project arg\n" >&2; exit 1
    fi
    folder="projects/$project/tasks"; dated=1 ;;
  *) printf "invalid type: %s\n" "$ntype" >&2; usage; exit 1 ;;
esac

mkdir -p "$vault/$folder"

# Find matching template. Apis use api-note.md.
case "$ntype" in
  api) tpl_name="api-note.md" ;;
  *)   tpl_name="${ntype}.md" ;;
esac
tpl="$vault/templates/$tpl_name"
if [ ! -f "$tpl" ]; then
  printf "template not found: %s\n" "$tpl" >&2; exit 1
fi

# Slug: lowercase, alnum + dash; collapse runs.
slug=$(printf '%s' "$title" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')
if [ -z "$slug" ]; then
  printf "title produced empty slug: %s\n" "$title" >&2; exit 1
fi

today=$(date +%F)
if [ "$dated" = "1" ]; then
  fname="${today}-${slug}.md"
else
  fname="${slug}.md"
fi
dst="$vault/$folder/$fname"

if [ -e "$dst" ]; then
  printf "note already exists: %s\n" "$dst" >&2; exit 1
fi

# Render tags array. Empty → [].
if [ -n "$tags_csv" ]; then
  tags_yaml="[$(printf '%s' "$tags_csv" | sed -E 's/[[:space:]]*,[[:space:]]*/, /g')]"
else
  tags_yaml="[]"
fi

# Read template, substitute. The placeholders are {{date}} and {{title}}; we also rewrite the
# tags and project lines deterministically since templates ship with neutral defaults.
content=$(cat "$tpl")
content=${content//\{\{date\}\}/$today}
content=${content//\{\{title\}\}/$title}

# Replace tags: line.
content=$(printf '%s\n' "$content" | awk -v t="$tags_yaml" '
  BEGIN { in_fm=0; count=0; done=0 }
  /^---$/ { count++; print; if (count==2) in_fm=0; else in_fm=1; next }
  in_fm && /^tags:/ && !done { print "tags: " t; done=1; next }
  { print }
')

# Replace project: line if a project arg was given.
if [ -n "$project" ]; then
  content=$(printf '%s\n' "$content" | awk -v p="$project" '
    BEGIN { in_fm=0; count=0; done=0 }
    /^---$/ { count++; print; if (count==2) in_fm=0; else in_fm=1; next }
    in_fm && /^project:/ && !done { print "project: " p; done=1; next }
    { print }
  ')
fi

printf '%s\n' "$content" > "$dst"
printf '%s\n' "$dst"
```

Make executable: `chmod +x /home/keertan/codes/brain/skills/obsidian-capture/scripts/make-note.sh`

- [ ] **Step 4: Run test, confirm passes**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: PASS — `capture make-note ok` plus all earlier tests.

- [ ] **Step 5: Commit**

```bash
cd /home/keertan/codes/brain && git add skills/obsidian-capture/scripts/make-note.sh tests/test-capture.sh && git commit -m "feat: make-note.sh creates frontmatter-validated notes from templates"
```

---

## Task 11: `obsidian-capture` skill — SKILL.md

**Files:**
- Create: `skills/obsidian-capture/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Create `/home/keertan/codes/brain/skills/obsidian-capture/SKILL.md`:

````markdown
---
name: obsidian-capture
description: Use AFTER a non-obvious decision, when a gotcha eats >5 minutes, or when a reusable pattern emerges. Writes a properly-frontmattered note to the Obsidian vault with wikilinks to related notes. Do NOT use to summarize a turn or save speculative thoughts.
---

# obsidian-capture

Persist a finding to the vault so it shows up next time someone asks.

## When to use

- A non-obvious decision was made and the reasoning is worth keeping. Example: "use redis for JWT store instead of postgres because rotation cadence makes write amplification ugly."
- A gotcha cost real time. Example: "FastAPI startup hook fires twice under uvicorn `--reload`."
- A pattern emerged worth reusing. Example: "feature flag rollout via gradual percentage + kill switch."
- End of a substantive session, to write the daily log entry.

## When NOT to use

- Summarizing what's already obvious in the diff.
- "Might be useful later" — speculative notes pollute the vault.
- The same finding already exists in the vault (run `obsidian-recall` first if unsure).
- Mid-flight: don't capture in the middle of solving. Capture at a real breakpoint.

## What it does

1. Pick a note type (`decision`, `gotcha`, `api`, `architecture`, `process`, `pattern`, `task`, `session`).
2. Generate slug + frontmatter from inputs (title, tags, project).
3. Call `make-note.sh` to render from the matching template into the correct vault folder.
4. Open the new file (Edit tool) and add the actual content: context, decision/cause, reasoning, related wikilinks.
5. Run `validate-frontmatter.sh` to confirm health.
6. Add `[[wikilinks]]` to related notes — find them via a quick `recall-search.sh` on key terms.

## How

### Step 1 — pick type

| Event | Type |
|---|---|
| Chose A over B with reasoning | `decision` |
| Surprise that took time to diagnose | `gotcha` |
| Reusable solution | `pattern` |
| Wrote/used an API surface worth documenting | `api` |
| Mapped a subsystem boundary | `architecture` |
| Team/process rule | `process` |
| Domain term | `glossary` |
| Repo-scoped task note | `task` (requires `project`) |
| End-of-session log | `session` |

### Step 2 — generate the note shell

```bash
VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/ObsidianVault}"
path=$(bash skills/obsidian-capture/scripts/make-note.sh \
  "$VAULT" "<type>" "<title>" "<tag,tag>" "<project-or-empty>")
```

`path` is the absolute path of the created file. Keep it.

### Step 3 — fill the body

Use the Edit tool on `path`. Replace the template placeholder sections (Context, Decision, Reasoning, Consequences, etc.) with the actual content. Be brief; future-you wants the takeaway, not the play-by-play.

### Step 4 — add wikilinks

Find related notes:

```bash
bash skills/obsidian-recall/scripts/recall-search.sh "$VAULT" "<key-concept>"
```

Pick the most relevant hits. Add their slugs (filename without `.md`) as `[[slug]]` inside the body's "Related" section and also in the frontmatter `related:` list.

### Step 5 — validate

```bash
bash skills/obsidian-capture/scripts/validate-frontmatter.sh "$path"
```

Must exit 0. If it fails, fix the frontmatter (most often: missing `created`/`updated` or invalid `type`).

### Step 6 — confirm

Tell the user: `Captured <type>: <path>`. Don't echo the full note body back.

## Don't

- ❌ Write to `knowledge/` types (`api`, `architecture`, `process`, `glossary`, `pattern`) without explicit user intent — these are curated. Default to `decision` or `gotcha` for agent-initiated captures.
- ❌ Capture the same finding twice. `recall` first.
- ❌ Skip validation. A bad-frontmatter note hides from future recalls.
- ❌ Paste the raw note back at the user — it bloats context.

## Related skills

- `obsidian-recall` — read before write to avoid duplicates and find link targets.
- `obsidian-setup` — fix vault permissions if writes fail.
````

- [ ] **Step 2: Commit**

```bash
cd /home/keertan/codes/brain && git add skills/obsidian-capture/SKILL.md && git commit -m "feat: obsidian-capture SKILL.md with type selection and link discipline"
```

---

## Task 12: Copilot instructions template

**Files:**
- Create: `copilot/instructions.md`
- Create: `copilot/README.md`

- [ ] **Step 1: Write `copilot/instructions.md`**

Create `/home/keertan/codes/brain/copilot/instructions.md`:

```markdown
# Repository AI agent instructions

This repository participates in a shared second-brain system at `~/Documents/ObsidianVault/`.

## Before non-trivial work

Read `~/Documents/ObsidianVault/_meta/AGENTS.md` for vault conventions. Search the vault for relevant context with ripgrep before reading code:

```bash
rg --type md --files-with-matches --ignore-case --fixed-strings "<topic>" ~/Documents/ObsidianVault
```

Prioritize hits from:
1. `knowledge/` — durable curated docs
2. `projects/<this-repo>/` — repo-specific notes
3. `agent-memory/` — prior decisions and gotchas
4. `daily/` — recent session logs

Read at most 3–5 notes. Summarize briefly; do not dump raw bodies.

## When to write

Capture to the vault at natural breakpoints:

- Non-obvious decision → `agent-memory/decisions/YYYY-MM-DD-<slug>.md`
- Surprise that took real time → `agent-memory/gotchas/YYYY-MM-DD-<slug>.md`
- Reusable pattern → propose to user before writing to `knowledge/patterns/`

Every note must have frontmatter as defined in `~/Documents/ObsidianVault/_meta/frontmatter-schema.md`.

## Do not

- Write to `~/Documents/ObsidianVault/knowledge/` without explicit user approval.
- Delete vault notes.
- Capture trivial summaries or speculative "might be useful later" notes.

## Sync

Obsidian Sync mirrors this vault across the user's devices. Treat the vault as authoritative; do not maintain a separate per-repo doc that duplicates it.
```

- [ ] **Step 2: Write `copilot/README.md`**

Create `/home/keertan/codes/brain/copilot/README.md`:

```markdown
# Using this skill pack with GitHub Copilot

Copilot (especially VS Code agent mode) doesn't load Claude Code skills, but the Obsidian vault is plain markdown and works the same. The contract is `~/Documents/ObsidianVault/_meta/AGENTS.md`.

## Install per repo

```bash
mkdir -p .github
cp /path/to/brain/copilot/instructions.md .github/copilot-instructions.md
```

GitHub Copilot reads `.github/copilot-instructions.md` automatically and applies it to chat and agent mode sessions in that repo.

## Verify

In a Copilot chat, ask:

> Read `~/Documents/ObsidianVault/_meta/AGENTS.md` and tell me the three sections of the vault.

If Copilot reads it and reports `knowledge/`, `agent-memory/`, `projects/` — wiring is good.

## Cursor / Aider / Cline

Same approach. Drop `instructions.md` content into whatever per-repo agent-config file the editor honors (`.cursorrules`, `AGENTS.md`, etc.). The vault conventions in `_meta/AGENTS.md` are the same regardless of agent.
```

- [ ] **Step 3: Commit**

```bash
cd /home/keertan/codes/brain && git add copilot/ && git commit -m "feat: Copilot instructions template + cross-agent README"
```

---

## Task 13: End-to-end integration test

**Files:**
- Create: `tests/test-end-to-end.sh`

This task wires all the scripts together against a temp vault and exercises the full setup → recall → capture loop.

- [ ] **Step 1: Write the end-to-end test**

Create `/home/keertan/codes/brain/tests/test-end-to-end.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

if ! command -v rg >/dev/null 2>&1; then
  printf "ripgrep required for end-to-end test\n" >&2; exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
vault="$tmp/vault"

# 1. Scaffold a vault from scratch.
if ! bash skills/obsidian-setup/scripts/scaffold-vault.sh "$vault" >/dev/null; then
  printf "scaffold failed\n" >&2; exit 1
fi

# 2. Capture a decision.
path=$(bash skills/obsidian-capture/scripts/make-note.sh \
  "$vault" decision "Pick redis for JWT store" "auth,redis" "brain")
if [ ! -f "$path" ]; then printf "decision not captured\n" >&2; exit 1; fi

# 3. Validate the new note.
if ! bash skills/obsidian-capture/scripts/validate-frontmatter.sh "$path" >/dev/null 2>&1; then
  printf "captured note fails validation\n" >&2
  cat "$path" >&2; exit 1
fi

# 4. Recall by keyword should surface the new note.
hits=$(bash skills/obsidian-recall/scripts/recall-search.sh "$vault" "JWT")
if ! printf '%s\n' "$hits" | grep -q "pick-redis-for-jwt-store.md"; then
  printf "recall did not find the captured decision\n" >&2
  printf "hits were:\n%s\n" "$hits" >&2
  exit 1
fi

# 5. Capture a gotcha and a glossary note. Run recall again; expect ordering: glossary (knowledge/) before decision (agent-memory/).
glossary_path=$(bash skills/obsidian-capture/scripts/make-note.sh \
  "$vault" glossary "JWT" "auth" "")
if [ ! -f "$glossary_path" ]; then printf "glossary not captured\n" >&2; exit 1; fi

hits=$(bash skills/obsidian-recall/scripts/recall-search.sh "$vault" "JWT")
first=$(printf '%s\n' "$hits" | head -n1)
if ! printf '%s' "$first" | grep -q 'knowledge/glossary/jwt.md'; then
  printf "recall ranking broken — expected glossary first, got: %s\n" "$first" >&2
  exit 1
fi

# 6. Idempotent re-scaffold preserves user content.
echo "user content" > "$vault/_meta/AGENTS.md"
bash skills/obsidian-setup/scripts/scaffold-vault.sh "$vault" >/dev/null
if ! grep -q "user content" "$vault/_meta/AGENTS.md"; then
  printf "re-scaffold overwrote user file\n" >&2; exit 1
fi

printf "end-to-end ok\n"
```

- [ ] **Step 2: Run end-to-end test**

Run: `bash /home/keertan/codes/brain/tests/run-all.sh`
Expected: PASS for every test file, ending with `all tests passed`.

- [ ] **Step 3: Commit**

```bash
cd /home/keertan/codes/brain && git add tests/test-end-to-end.sh && git commit -m "test: end-to-end setup → capture → recall loop"
```

---

## Task 14: Real install + smoke test against user's actual vault path

**Files:**
- Modify: `~/.claude/settings.json` (add `additionalDirectories`)
- Create: `~/Documents/ObsidianVault/` (if absent)

This task runs the skills for real, not in a temp dir. Stops short of writing inside the user's existing vault contents — purely scaffolds missing pieces.

- [ ] **Step 1: Confirm vault path with the user**

Ask the user: "Use default vault path `~/Documents/ObsidianVault/`? It may already be populated via Obsidian Sync — confirm before I scaffold."

If user gives a different path, use that.

- [ ] **Step 2: Run scaffold against real path**

```bash
bash /home/keertan/codes/brain/skills/obsidian-setup/scripts/scaffold-vault.sh "$HOME/Documents/ObsidianVault"
```

Read output: `copied=N skipped=M`. If `skipped` is high, the user's vault already exists; this run only filled gaps.

- [ ] **Step 3: Patch `~/.claude/settings.json`**

Read current settings (use Read tool). If `additionalDirectories` exists and includes the vault path: skip. If it exists without the path: append. If it doesn't exist: add the array.

Use Edit tool with the smallest possible diff. Example, if the file currently ends with:

```json
  "skipAutoPermissionPrompt": true
}
```

Edit to:

```json
  "skipAutoPermissionPrompt": true,
  "additionalDirectories": ["/home/keertan/Documents/ObsidianVault"]
}
```

Validate the JSON parses after edit:

```bash
python3 -c "import json,sys; json.load(open('$HOME/.claude/settings.json'))" && echo "settings json valid"
```

- [ ] **Step 4: Smoke test — capture a sentinel note, recall it, delete it**

```bash
VAULT="$HOME/Documents/ObsidianVault"
path=$(bash /home/keertan/codes/brain/skills/obsidian-capture/scripts/make-note.sh \
  "$VAULT" gotcha "Install smoke test — $(date +%s)" "smoke-test" "brain")
bash /home/keertan/codes/brain/skills/obsidian-capture/scripts/validate-frontmatter.sh "$path"
bash /home/keertan/codes/brain/skills/obsidian-recall/scripts/recall-search.sh "$VAULT" "Install smoke test"
rm "$path"
```

Expected: capture prints a path, validator exits 0, recall returns that path, deletion succeeds.

- [ ] **Step 5: Report to user**

Surface:
- Vault path scaffolded.
- Files copied vs skipped.
- `additionalDirectories` patched (or already correct).
- Smoke test outcome.
- Suggested next: `/obsidian-recall <topic>` and `/obsidian-capture <type>` in everyday work.

- [ ] **Step 6: Final commit if needed**

If anything in the repo changed during the real-install run (it shouldn't — vault-template is the only source of truth and it was set in earlier tasks), commit. Otherwise nothing to do.

---

## Self-Review

**Spec coverage check:**

| Spec section | Task coverage |
|---|---|
| Vault structure (knowledge/agent-memory/projects/daily/_meta/templates) | Task 2 (dirs) + Task 3 (_meta) + Task 4 (templates) |
| Frontmatter schema | Task 3 (`_meta/frontmatter-schema.md`) + Task 5 (validator) |
| Linking conventions | Task 3 (`_meta/linking-conventions.md`) |
| AGENTS.md cross-agent contract | Task 3 (`_meta/AGENTS.md`) |
| obsidian-setup skill | Task 6 (script) + Task 7 (SKILL.md) |
| obsidian-recall skill | Task 8 (script) + Task 9 (SKILL.md) |
| obsidian-capture skill | Task 5 (validator) + Task 10 (make-note) + Task 11 (SKILL.md) |
| Write isolation (no agent writes to knowledge/) | Documented in SKILL.md files; not enforced in code (intentional — humans can write there) |
| Context budget (≤500 token recall) | Documented in `obsidian-recall/SKILL.md`; recall script returns paths only, summary is agent's responsibility |
| Cross-agent strategy (Copilot) | Task 12 |
| 60-second mtime concurrency rule | Documented in `_meta/AGENTS.md`; not enforced in code (deferred — risk is low for single user) |
| Phase 1 success criteria (setup, recall, capture end-to-end) | Task 13 (integration test) + Task 14 (real install) |

**Gaps deliberately deferred to later phases:**

- `obsidian-curate`, `obsidian-graph-walk`, `obsidian-daily-log`, `obsidian-project-bootstrap` — Phase 2 / Phase 3 per spec.
- Automated mtime concurrency enforcement — risk low for single-user, gate at write time later if needed.
- Semantic search — Phase 3 if grep proves insufficient.

**Placeholder scan:** No `TBD`, `TODO`, "implement later", "add error handling", or "similar to Task N" patterns. Each step has concrete code or commands.

**Type/name consistency:**
- `scaffold-vault.sh` referenced in Task 6 and Task 14 — same name, same args (`<vault-path>`).
- `recall-search.sh` args `<vault> <query> [max-hits]` consistent across Task 8, 9, 11, 13.
- `make-note.sh` args `<vault> <type> <title> [tags-csv] [project]` consistent across Task 10, 11, 13, 14.
- `validate-frontmatter.sh` args `<note.md>` consistent across Task 5, 11, 13, 14.
- Vault folder names match between `scaffold-vault.sh` (Task 6), templates (Task 4), and capture type→folder map (Task 10).
- Note type enum matches across `frontmatter-schema.md` (Task 3), `validate-frontmatter.sh` (Task 5), and `make-note.sh` (Task 10): decision, session, gotcha, api, architecture, process, glossary, pattern, project, task, meta.

Plan ready for execution.
