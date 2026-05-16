---
type: meta
tags: [conventions, agents]
status: active
created: 2026-05-17
updated: 2026-05-17
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
