#!/usr/bin/env bash
# scaffold-vault.sh <vault-path>
# Idempotently scaffolds an Obsidian vault: creates required dirs and copies vault-template/* into target.
# Existing files are preserved.

set -euo pipefail

vault=${1:-}
if [ -z "$vault" ]; then
  printf "usage: %s <vault-path>\n" "$0" >&2
  exit 1
fi

script_dir=$(cd "$(dirname "$0")" && pwd)
template_dir=$(cd "$script_dir/../../../vault-template" 2>/dev/null && pwd) || {
  printf "vault-template not found relative to script at %s\n" "$script_dir" >&2
  exit 1
}

mkdir -p "$vault"

for d in \
  knowledge/architecture knowledge/api knowledge/process knowledge/glossary knowledge/patterns \
  agent-memory/decisions agent-memory/sessions agent-memory/gotchas agent-memory/prompts \
  projects daily _meta templates; do
  mkdir -p "$vault/$d"
done

copied=0
skipped=0
while IFS= read -r -d '' src; do
  rel=${src#"$template_dir/"}
  if [ "$(basename "$rel")" = ".gitkeep" ]; then
    continue
  fi
  dst="$vault/$rel"
  if [ -e "$dst" ]; then
    skipped=$((skipped + 1))
    continue
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  copied=$((copied + 1))
done < <(find "$template_dir" -type f -print0)

printf "vault scaffolded at %s (copied=%d skipped=%d)\n" "$vault" "$copied" "$skipped"
