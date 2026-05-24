# Installation

The agent brain v2 ships as a Python package + 3 Claude Code skills + an Obsidian vault export.

## Prerequisites

- Python 3.12+ (`python3 --version`)
- Postgres 16+ with `pgvector` extension. Two paths:
  - **Docker (recommended for dev):** `docker compose up -d` from the repo root spins up `pgvector/pgvector:pg16` on `127.0.0.1:5433`.
  - **Native (recommended for prod):** install `postgresql-16` and `postgresql-16-pgvector` via your package manager, then create the brain database and role:
    ```bash
    sudo -u postgres psql -c "CREATE ROLE brain LOGIN PASSWORD 'CHANGE_ME'"
    sudo -u postgres psql -c "CREATE DATABASE brain OWNER brain"
    ```
- `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

## Install

```bash
git clone <repo> ~/codes/brain && cd ~/codes/brain
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
bash skills/brain-setup/scripts/setup.sh
```

Then in Claude Code, install the skills:

```bash
bash clients/install-claude-code.sh
```

## Verify

```bash
brain health
```

Should print a table of row counts (most zero on a fresh install) plus `brain_config` with seeded defaults.

## Vault wiring

Set `OBSIDIAN_VAULT` to your vault root if not at `~/Documents/ObsidianVault`. Optionally set `BRAIN_SUBDIR` (default `Agent-Brain`).

## Migrate v1 content (one-time)

If you have an existing v1 markdown vault under `<vault>/Agent-Brain/`, ingest it:

```bash
brain reingest "$OBSIDIAN_VAULT/Agent-Brain"
```

Re-running is idempotent — content-hash dedup keeps it clean.
