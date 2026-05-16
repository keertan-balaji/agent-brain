---
name: obsidian-map-repo
description: Use when the user wants to import a coding repo or directory into the second brain — first-time onboarding to a codebase, "map this repo", "scan this repo into Obsidian", "start a brain for this project". Bootstraps the project folder if absent, then writes `projects/<repo>/repo-map.md` with stack detection, top-level layout, README excerpt, git activity, file-extension histogram, and a follow-up checklist. The output is the starting point for capturing architecture notes, decisions, and gotchas about that repo.
---

# obsidian-map-repo

Onboard a coding repo into the vault: bootstrap the project folder, then generate a structured `repo-map.md` describing what's in the repo today.

## When to use

- User says: "map this repo", "scan this directory into Obsidian", "start a brain for this project", "/obsidian-map-repo".
- Entering a repo Claude Code hasn't worked in before — the brain has no project folder for it yet.
- The repo's project folder exists but a fresh map is wanted (use `--force`).
- Onboarding a new codebase as part of a `task_type: development` project.

## When NOT to use

- The user just wants notes captured for one decision — use `obsidian-capture` directly.
- The work is research, not code — `obsidian-project-bootstrap` with `task_type: research` is the right tool.
- An up-to-date `repo-map.md` already exists and nothing has changed in the repo since.

## What it does

1. Resolves the repo's absolute path and derives a kebab-case slug from its basename.
2. If `projects/<slug>/` doesn't exist, bootstraps it as a `development` project (`obsidian-project-bootstrap` under the hood).
3. Scans the repo:
   - **Stack** — manifest files detected (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Gemfile`, `pom.xml`, `Dockerfile`, etc.).
   - **Top-level layout** — `find` to depth 2, common noise excluded (`.git`, `node_modules`, `__pycache__`, virtualenvs, build dirs).
   - **README excerpt** — first 30 lines of `README.md`/`.rst`/`.txt` if present.
   - **Git activity** — current branch + last 10 commits if a git repo.
   - **File counts** — top 10 extensions by file count.
4. Renders `projects/<slug>/repo-map.md` with proper frontmatter, plus a follow-up checklist.
5. Refuses to overwrite an existing map unless `--force` is passed (so accidental re-maps don't blow away annotations).

## How

### Step 1 — resolve vault and repo

```bash
BRAIN=/home/keertan/codes/brain
VAULT=$(bash "$BRAIN/skills/obsidian-setup/scripts/resolve-vault.sh")
# Default repo = current working directory's git root, else cwd.
REPO=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
```

If the user supplied a different path, use that. Otherwise the git root of the cwd.

### Step 2 — run the map

```bash
path=$(bash "$BRAIN/skills/obsidian-map-repo/scripts/map-repo.sh" "$VAULT" "$REPO")
```

If the script fails with "already exists", decide:
- If the user asked for a refresh, re-run with `--force`.
- Otherwise tell them the existing map and ask before clobbering.

### Step 3 — validate

```bash
bash "$BRAIN/skills/obsidian-capture/scripts/validate-frontmatter.sh" "$path"
```

Must exit 0.

### Step 4 — read and synthesize

Use the Read tool on the new map file. **Don't dump it back at the user verbatim** — it's reference material that lives in the vault. Instead emit a 3–5-line synthesis:

> Mapped `<repo-name>` into the brain. Stack: `<key langs>`. `<N>` top-level dirs. `<git-status>`. Suggested next actions saved in `repo-map.md`.

### Step 5 — surface high-value captures

Skim the map for things worth turning into proper notes:

- **Architecture insights** the README revealed → suggest `obsidian-capture` with `type: architecture` (knowledge/ — needs user approval per write discipline).
- **External APIs** mentioned → suggest `obsidian-capture` with `type: api`.
- **Glossary candidates** — domain terms in the README → `glossary` notes.

Don't write these yourself — point them out so the user decides what's worth keeping.

### Step 6 — link from project index

The project `index.md` already lists `[[ ]]` placeholders in its "Architecture pointers" / "Modules" / "Related" sections. Use the Edit tool to add `[[repo-map]]` to a relevant section so the index points at the new scan.

## What the map looks like

A typical generated map (Python project, in git):

```
---
type: project
tags: [map, repo-scan]
project: <slug>
status: active
created: 2026-05-17
updated: 2026-05-17
task_type: development
---

# Repo map — <repo-name>

## Location
`<abs-path>`

## Stack
- Python (pyproject.toml)
- Make (Makefile)

## Top-level layout
```
src/
src/main.py
tests/
tests/test_x.py
docs/
README.md
pyproject.toml
```

## README excerpt
*From `README.md`:*
```markdown
# myrepo
A demo project...
```

## Git activity
Branch: `main`
Recent commits:
```
abc123 feat: initial commit
def456 docs: tweak
```

## File counts
- `.py`: 12
- `.md`: 3

## Suggested follow-ups
- [ ] Capture key architecture notes ...
```

## Don't

- Don't run on directories that aren't actually code repos (`~/Documents`, `~`, etc.) — the noise filters help but you'll still produce a huge useless map.
- Don't re-map repeatedly in a session. The map is a snapshot; capture deltas as `agent-memory/` notes between scans.
- Don't dump the map body at the user — the file is the artifact, the chat gets a synthesis.
- Don't promote the map to `knowledge/` — it's a snapshot, not curated knowledge.
- Don't run with `--force` without warning the user; the existing map may have hand annotations.

## Related skills

- `obsidian-project-bootstrap` — called automatically if the project doesn't exist yet.
- `obsidian-capture` — for the architecture/api/gotcha notes the map surfaces.
- `obsidian-recall` — searches the map alongside the rest of the vault on future queries.
