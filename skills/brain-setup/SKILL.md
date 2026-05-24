---
name: brain-setup
description: Use to install or initialize the agent brain (Postgres + Python + schema). Run on first install, when the brain database is missing, or when migrations need to be re-applied. Idempotent.
---

# brain-setup

Provision the agent brain: Postgres running, schema migrated, Python package installed, Obsidian vault detected.

## When to use

- First install of the agent brain on a machine.
- DB missing: another `brain ...` command failed with "could not connect to Postgres."
- Schema drift: pulled new migrations and want to apply them.
- Reset: spin down + spin up the dev database (with `--reset`).

## What it runs

1. Detect Postgres availability:
   - If `docker compose` works AND `pg_isready` against the brain compose service succeeds → use it.
   - Else, check for a local Postgres listening on `127.0.0.1:5432` with a `brain` database.
   - Else, offer to `docker compose up -d` from the repo root.
2. Ensure the `vector`, `pg_trgm`, `btree_gist` extensions are installed.
3. Run `alembic upgrade head` to apply all migrations.
4. Verify by calling `brain health` — should print non-zero `brain_config` row count.
5. Resolve the Obsidian vault path from `OBSIDIAN_VAULT` env or `~/Documents/ObsidianVault` default; print where it lands.

## How (the script)

```bash
bash skills/brain-setup/scripts/setup.sh
```

The script auto-detects existing Postgres before falling back to docker-compose. Reset with `--reset` (drops `brain_pg_data` volume; lossy).

## Don't

- Don't run on a production database — `--reset` drops data.
- Don't edit `alembic/versions/*` after running setup on multiple machines; downgrade-then-upgrade can fail if migration content changed mid-flight.
