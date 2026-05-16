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
VAULT=$(bash skills/obsidian-setup/scripts/resolve-vault.sh)
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

- Write to `knowledge/` types (`api`, `architecture`, `process`, `glossary`, `pattern`) without explicit user intent — these are curated. Default to `decision` or `gotcha` for agent-initiated captures.
- Capture the same finding twice. `recall` first.
- Skip validation. A bad-frontmatter note hides from future recalls.
- Paste the raw note back at the user — it bloats context.

## Related skills

- `obsidian-recall` — read before write to avoid duplicates and find link targets.
- `obsidian-setup` — fix vault permissions if writes fail.
