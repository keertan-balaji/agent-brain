---
type: meta
tags: [schema, agents]
status: active
created: 2026-05-17
updated: 2026-05-17
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
