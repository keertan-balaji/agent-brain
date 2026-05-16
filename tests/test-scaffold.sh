#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

required_dirs=(
  "vault-template/knowledge/architecture"
  "vault-template/knowledge/api"
  "vault-template/knowledge/process"
  "vault-template/knowledge/glossary"
  "vault-template/knowledge/patterns"
  "vault-template/agent-memory/decisions"
  "vault-template/agent-memory/sessions"
  "vault-template/agent-memory/gotchas"
  "vault-template/agent-memory/prompts"
  "vault-template/projects"
  "vault-template/daily"
  "vault-template/_meta"
  "vault-template/templates"
)
for d in "${required_dirs[@]}"; do
  if [ ! -d "$d" ]; then
    printf "missing dir: %s\n" "$d" >&2
    exit 1
  fi
done

required_files=(
  "vault-template/_meta/MOC.md"
  "vault-template/_meta/AGENTS.md"
  "vault-template/_meta/frontmatter-schema.md"
  "vault-template/_meta/linking-conventions.md"
  "vault-template/templates/decision.md"
  "vault-template/templates/session.md"
  "vault-template/templates/gotcha.md"
  "vault-template/templates/api-note.md"
  "vault-template/templates/architecture.md"
)
for f in "${required_files[@]}"; do
  if [ ! -f "$f" ]; then
    printf "missing file: %s\n" "$f" >&2
    exit 1
  fi
done

# --- scaffold-vault.sh integration check ---
SCAFFOLD=skills/obsidian-setup/scripts/scaffold-vault.sh
if [ ! -x "$SCAFFOLD" ]; then
  printf "scaffold script missing: %s\n" "$SCAFFOLD" >&2
  exit 1
fi

tmpvault=$(mktemp -d)
trap 'rm -rf "$tmpvault"' EXIT

if ! bash "$SCAFFOLD" "$tmpvault" >/dev/null 2>&1; then
  printf "scaffold-vault.sh failed on empty dir\n" >&2
  exit 1
fi

for d in knowledge/architecture agent-memory/decisions projects daily _meta templates; do
  if [ ! -d "$tmpvault/$d" ]; then
    printf "scaffold missing dir: %s\n" "$d" >&2; exit 1
  fi
done
for f in _meta/AGENTS.md _meta/MOC.md _meta/frontmatter-schema.md _meta/linking-conventions.md templates/decision.md; do
  if [ ! -f "$tmpvault/$f" ]; then
    printf "scaffold missing file: %s\n" "$f" >&2; exit 1
  fi
done

# Idempotency: re-running on existing vault must not error and must not duplicate or overwrite user files.
echo "user content" > "$tmpvault/_meta/AGENTS.md"
if ! bash "$SCAFFOLD" "$tmpvault" >/dev/null 2>&1; then
  printf "scaffold-vault.sh failed on existing vault\n" >&2; exit 1
fi
if ! grep -q "user content" "$tmpvault/_meta/AGENTS.md"; then
  printf "scaffold overwrote existing _meta/AGENTS.md\n" >&2; exit 1
fi

printf "scaffold ok\n"
