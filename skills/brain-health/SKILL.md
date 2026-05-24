---
name: brain-health
description: Use weekly or when investigating brain quality issues. Runs the Phase-1 audit (table sizes, under-captured sessions, orphan rows, stale-active sources). Phase 4 will add generative-lint mode (--lint).
---

# brain-health

Audit the brain. Read-only.

## When to use

- Weekly maintenance.
- When recall feels off (no hits where there should be hits → check stale-active or under-captured rates).
- After bulk operations (migration, mass ingest, schema change) to verify nothing leaked.

## What it reports

- Row counts per table.
- Sessions that ended with fewer than `--threshold` (default 3) events captured.
- Orphan classifications (rows referencing non-existent sources — a corruption signal).
- Sources with `status='active'` older than 90 days (stale signal; consider archiving).

Phase 4 will add a `--lint` mode that runs NLI contradictions + identify_gaps + surface user-facing questions. Phase 1 is the baseline.

## How

```bash
bash skills/brain-health/scripts/health.sh [--threshold 3]
```

Print is human-readable rich-table. CI integration: parse JSON via `brain health --json` (added in Phase 3 when JSON output lands).
