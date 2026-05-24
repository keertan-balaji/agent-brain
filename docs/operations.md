# Operations

## Backup

Nightly `pg_dump` is the canonical disaster-recovery path. Add to cron:

```bash
0 2 * * * /usr/bin/pg_dump -U brain brain | gzip > "$HOME/Documents/ObsidianVault/Agent-Brain/_backups/brain-$(date +\%F).sql.gz"
```

The markdown view under `<vault>/Agent-Brain/` is a **partial fallback only** — see spec §Obsidian markdown view. Episodic stream, embeddings, retrieval logs, and procedure counters are NOT recoverable from markdown alone.

## Restore

```bash
gunzip -c brain-2026-05-24.sql.gz | psql -U brain brain
```

## Conflict resolution (markdown ↔ DB)

If the file-watcher (Phase 3) detects a markdown edit that conflicts with a recent DB write, both versions are kept (older invalidated with `invalidation_reason='conflict: see <id>'`). The user resolves via `brain reingest` after editing.

## Cost guards

Phase 1 has no LLM dependencies — no API costs. Phase 2+ introduces per-session cost caps configurable in `brain_config`.
