---
name: brain-link
description: Use after capturing a new source or whenever you notice an orphan note. Calls propose_links to suggest related sources via FTS + vector + entity-graph fusion. Caps at top-5 by default; review and add wikilinks to the source's "Related" section.
---

# brain-link

Surface related sources for a freshly captured note so the brain knits together instead of accumulating orphans.

## When to use

- After capturing a new decision, gotcha, or pattern.
- Reviewing an old note that lacks a `related:` frontmatter list.
- Before drafting a new note — see what already exists in the neighborhood.

## When NOT to use

- The source is a one-off (e.g. raw tool output).
- You already linked this source this session.

## How

```bash
bash skills/brain-link/scripts/link.sh <source_id> [-k 5]
```

Prints a table of `(target_id, kind, score, rationale, head)`. Rationale is one of `vector_similarity`, `fts_overlap`, `shared_entity`.

Review the table, then add wikilinks (`[[note-name]]`) to the original source's `Related` section and frontmatter `related:` list via your Edit tool.

## Output budget

≤300 tokens. Do not dump the raw table at the user; pick the top 2-3 worth linking and explain why.
