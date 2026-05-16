---
name: obsidian-project-bootstrap
description: MANDATORY at the start of every new project. Use IMMEDIATELY when entering a new repo, starting a new research task, beginning a new analysis, or any time the agent recognizes the current work as a distinct project that doesn't yet exist in the vault. Creates `projects/<name>/` with a task-type-appropriate index.md (research, development, repo-analysis, or generic) and required subdirs. Non-negotiable — every project starts here.
---

# obsidian-project-bootstrap

Initialize a project workspace in the vault before any other vault writes for that project.

## When to use

**Always**, at the moment you recognize the current work as a new project. Triggers:

- A new repo / codebase is being worked on for the first time this session.
- The user describes a new piece of work that spans more than a single ad-hoc question.
- A research question that will take more than one exchange to answer.
- A repo audit, migration eval, security review, onboarding pass.
- You're about to capture a decision or gotcha that doesn't have a project to attach to.

If you find yourself reaching for `obsidian-capture` and the project doesn't exist in `projects/`, bootstrap first.

## When NOT to use

- The project folder already exists in `projects/<name>/` — extend the existing index instead.
- The work is a one-shot question with no follow-up expected.
- The user explicitly asked for a vault-free interaction.

## What it does

1. Picks a project name (kebab-case, from repo name or user-supplied label).
2. Picks a task type — exactly one of: `research`, `development`, `repo-analysis`, `generic`.
3. Runs `bootstrap-project.sh` to create `projects/<name>/` with `tasks/` (always) and `modules/` (development only) and a task-type-specific `index.md` filled from the matching template.
4. The index.md ships with frontmatter (`type: project`, `task_type: <type>`, `project: <name>`, dates, status).
5. Refuses to overwrite an existing project — fail loudly so you extend instead of clobbering.

## How

### Step 1 — pick name

Default: repo basename (e.g., from `git rev-parse --show-toplevel | xargs basename`). Override if the user names it differently. Must be filesystem-safe; the script kebab-cases it.

### Step 2 — pick task type

| Work looks like | task_type |
|---|---|
| Building/shipping code in a repo | `development` |
| Investigating a question, gathering sources, no code output | `research` |
| Reading an existing repo to map/audit/onboard | `repo-analysis` |
| Doesn't fit any of the above | `generic` |

Pick exactly one. If genuinely unclear, use `generic` and refine later by editing the index frontmatter.

### Step 3 — bootstrap

```bash
REPO=/home/keertan/codes/brain
BRAIN=$(bash "$REPO/skills/obsidian-setup/scripts/resolve-brain.sh")
path=$(bash "$REPO/skills/obsidian-project-bootstrap/scripts/bootstrap-project.sh" \
  "$BRAIN" "<project-name>" "<task_type>" "<human-readable-title>")
```

`path` is the absolute path of `projects/<name>/index.md`. Keep it.

### Step 4 — fill the index

Use the Edit tool on `path`. The template ships with section headers tailored to the task type. Replace placeholder bullets with real content drawn from the user's request: scope, repo path, key questions, etc. Stay brief — the index is a directory, not a doc dump.

### Step 5 — link to existing knowledge

Run `recall-search.sh` for key concepts in the new project to find existing `knowledge/` notes worth linking from the index:

```bash
bash "$REPO/skills/obsidian-recall/scripts/recall-search.sh" "$BRAIN" "<concept>"
```

Add the hits as `[[wikilinks]]` in the index "Architecture pointers" / "Related" sections.

### Step 6 — validate

```bash
bash "$REPO/skills/obsidian-capture/scripts/validate-frontmatter.sh" "$path"
```

Must exit 0.

### Step 7 — confirm

Tell the user: `Project bootstrapped: <path> (task_type=<type>)`. From here on, all decisions / gotchas / tasks captured during this work use `project=<name>` in their frontmatter and live alongside (or link to) this index.

## Don't

- Bootstrap the same project twice. The script will refuse — that's intentional. Extend the index instead.
- Skip this step "because it's a quick task." If the task spans more than one capture, it's a project.
- Pick `generic` to avoid a decision. The task_type drives later curation; getting it right matters.
- Bootstrap a project just to capture a single one-shot decision. If there's no follow-up work, write the decision to `agent-memory/decisions/` with `project: <existing-name-or-null>`.
- Move existing notes around to "fit" the new project — link to them instead.

## Cross-agent enforcement

The mandate to bootstrap on new-project entry is encoded in `<vault>/_meta/AGENTS.md`. Other agents (Copilot, Cursor, etc.) reading that file follow the same rule via plain filesystem ops, even without this skill installed. The vault contract is the source of truth; this skill is the Claude Code shortcut.

## Related skills

- `obsidian-setup` — fix "vault not found" before bootstrap.
- `obsidian-recall` — find prior knowledge to link from the new index.
- `obsidian-capture` — once bootstrapped, captures attach to this project via `project: <name>` frontmatter.
