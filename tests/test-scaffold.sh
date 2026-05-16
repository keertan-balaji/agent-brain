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

# --- scaffold-brain.sh integration check ---
SCAFFOLD=skills/obsidian-setup/scripts/scaffold-brain.sh
if [ ! -x "$SCAFFOLD" ]; then
  printf "scaffold script missing: %s\n" "$SCAFFOLD" >&2
  exit 1
fi

tmpvault=$(mktemp -d)
trap 'rm -rf "$tmpvault"' EXIT

# Simulate an existing user vault by planting a note that must NOT be touched.
mkdir -p "$tmpvault/Inbox"
echo "user note body — must not be touched" > "$tmpvault/Inbox/important.md"

if ! bash "$SCAFFOLD" "$tmpvault" >/dev/null 2>&1; then
  printf "scaffold-brain.sh failed on empty-ish vault\n" >&2
  exit 1
fi

brain="$tmpvault/Agent-Brain"
[ -d "$brain" ] || { printf "Agent-Brain/ not created\n" >&2; exit 1; }

# User's own content untouched.
grep -q "must not be touched" "$tmpvault/Inbox/important.md" || {
  printf "scaffold touched user vault content\n" >&2; exit 1
}
# Vault root should NOT have scaffolded sections.
for d in knowledge agent-memory projects daily _meta templates; do
  if [ -d "$tmpvault/$d" ]; then
    printf "scaffolded section leaked into vault root: %s\n" "$d" >&2; exit 1
  fi
done

# Required sections present under Agent-Brain/.
for d in knowledge/architecture agent-memory/decisions projects daily _meta templates; do
  if [ ! -d "$brain/$d" ]; then
    printf "scaffold missing dir under Agent-Brain/: %s\n" "$d" >&2; exit 1
  fi
done
for f in _meta/AGENTS.md _meta/MOC.md _meta/frontmatter-schema.md _meta/linking-conventions.md templates/decision.md; do
  if [ ! -f "$brain/$f" ]; then
    printf "scaffold missing file under Agent-Brain/: %s\n" "$f" >&2; exit 1
  fi
done

# Idempotency: re-running must not duplicate or overwrite files inside Agent-Brain/.
echo "user-edited agent doc" > "$brain/_meta/AGENTS.md"
if ! bash "$SCAFFOLD" "$tmpvault" >/dev/null 2>&1; then
  printf "scaffold-brain.sh failed on existing vault\n" >&2; exit 1
fi
if ! grep -q "user-edited agent doc" "$brain/_meta/AGENTS.md"; then
  printf "scaffold overwrote existing _meta/AGENTS.md\n" >&2; exit 1
fi

# BRAIN_SUBDIR override honored.
tmpvault2=$(mktemp -d)
BRAIN_SUBDIR="Custom-Brain" bash "$SCAFFOLD" "$tmpvault2" >/dev/null
[ -d "$tmpvault2/Custom-Brain/_meta" ] || { printf "BRAIN_SUBDIR override ignored\n" >&2; rm -rf "$tmpvault2"; exit 1; }
[ -d "$tmpvault2/Agent-Brain" ] && { printf "default brain dir created when override set\n" >&2; rm -rf "$tmpvault2"; exit 1; }
rm -rf "$tmpvault2"

printf "scaffold ok\n"
