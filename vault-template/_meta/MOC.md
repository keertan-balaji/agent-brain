---
type: meta
tags: [moc, index]
status: active
created: 2026-05-17
updated: 2026-05-17
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
