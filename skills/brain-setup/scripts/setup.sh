#!/usr/bin/env bash
# brain-setup: provision Postgres + migrate schema. Idempotent.

set -euo pipefail

RESET=0
if [ "${1:-}" = "--reset" ]; then
  RESET=1
fi

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

printf "==> Detecting Postgres availability...\n"

PG_URL_DEFAULT="postgresql+psycopg://brain:brain_dev_password@127.0.0.1:5433/brain"
PG_URL="${BRAIN_DB_URL:-$PG_URL_DEFAULT}"

# Try docker-compose first (the dev default).
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  if [ "$RESET" -eq 1 ]; then
    printf "==> --reset: docker compose down -v\n"
    docker compose down -v || true
  fi
  if ! docker compose ps postgres 2>/dev/null | grep -q 'Up'; then
    printf "==> Starting docker-compose Postgres...\n"
    docker compose up -d postgres
  fi
  # Wait for healthy.
  for _ in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U brain -d brain >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

printf "==> Applying alembic migrations...\n"
BRAIN_DB_URL="$PG_URL" alembic upgrade head

printf "==> Verifying with brain health...\n"
BRAIN_DB_URL="$PG_URL" brain health

VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/ObsidianVault}"
SUBDIR="${BRAIN_SUBDIR:-Agent-Brain}"
printf "==> Obsidian vault will export to: %s/%s\n" "$VAULT" "$SUBDIR"
printf "==> Done. Run 'brain --help' to see commands.\n"
