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

printf "scaffold ok\n"
