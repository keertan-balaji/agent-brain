#!/usr/bin/env bash
# scaffold-brain.sh <vault-path>
# Idempotently scaffolds the agent's namespace inside the user's vault.
# Creates <vault>/Agent-Brain/ with knowledge/, agent-memory/, projects/, daily/,
# _meta/, templates/ subdirs and copies vault-template/* into _meta/ + templates/.
# The user's own vault content (anything outside Agent-Brain/) is never touched.
# Existing files inside Agent-Brain/ are preserved (skip, don't overwrite).
#
# Override the subdir name with BRAIN_SUBDIR=Some-Name; default is Agent-Brain.

set -euo pipefail

vault=${1:-}
if [ -z "$vault" ]; then
  printf "usage: %s <vault-path>\n" "$0" >&2
  exit 1
fi

brain_subdir=${BRAIN_SUBDIR:-Agent-Brain}
brain="$vault/$brain_subdir"

script_dir=$(cd "$(dirname "$0")" && pwd)
template_dir=$(cd "$script_dir/../../../vault-template" 2>/dev/null && pwd) || {
  printf "vault-template not found relative to script at %s\n" "$script_dir" >&2
  exit 1
}

mkdir -p "$brain"

for d in \
  knowledge/architecture knowledge/api knowledge/process knowledge/glossary knowledge/patterns \
  agent-memory/decisions agent-memory/sessions agent-memory/gotchas agent-memory/prompts \
  projects daily _meta templates; do
  mkdir -p "$brain/$d"
done

copied=0
skipped=0
while IFS= read -r -d '' src; do
  rel=${src#"$template_dir/"}
  if [ "$(basename "$rel")" = ".gitkeep" ]; then
    continue
  fi
  dst="$brain/$rel"
  if [ -e "$dst" ]; then
    skipped=$((skipped + 1))
    continue
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  copied=$((copied + 1))
done < <(find "$template_dir" -type f -print0)

printf "brain scaffolded at %s (copied=%d skipped=%d)\n" "$brain" "$copied" "$skipped"
