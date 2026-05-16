#!/usr/bin/env bash
# connect-vault.sh <vault-path>
# Validates the supplied path and scaffolds the agent's namespace inside it
# at <vault>/Agent-Brain/ (override via $BRAIN_SUBDIR). The user's own vault
# content — anything outside Agent-Brain/ — is never touched. Persists the
# vault path to $BRAIN_VAULT_CONFIG (default: <brain-repo>/.vault-path).
#
# Behavior:
#   - empty / missing / file path  → reject
#   - empty dir                    → accept, scaffold Agent-Brain/
#   - dir containing .obsidian/    → accept (confirmed Obsidian vault), scaffold Agent-Brain/
#   - dir with content but no .obsidian/ → accept with stderr warning, scaffold Agent-Brain/
#
# Output: absolute vault path on stdout.

set -euo pipefail

raw=${1:-}
if [ -z "$raw" ]; then
  printf "usage: %s <vault-path>\n" "$0" >&2
  printf "  resolves to absolute path, validates, scaffolds gaps, persists choice.\n" >&2
  exit 1
fi

if [ ! -e "$raw" ]; then
  printf "vault path does not exist: %s\n" "$raw" >&2
  exit 1
fi
if [ ! -d "$raw" ]; then
  printf "vault path is not a directory: %s\n" "$raw" >&2
  exit 1
fi

# Normalize to absolute (no realpath dependency: cd + pwd).
abs=$(cd "$raw" && pwd)

if [ ! -r "$abs" ] || [ ! -w "$abs" ]; then
  printf "vault path not readable+writable: %s\n" "$abs" >&2
  exit 1
fi

# Classify.
if [ -d "$abs/.obsidian" ]; then
  : # confirmed Obsidian vault
elif [ -z "$(ls -A "$abs" 2>/dev/null)" ]; then
  : # empty dir, fine
else
  printf "warning: %s has content but no .obsidian/ — treating as plain notes dir\n" "$abs" >&2
fi

# Scaffold the agent namespace via scaffold-brain.sh (idempotent: skips existing files).
script_dir=$(cd "$(dirname "$0")" && pwd)
scaffold="$script_dir/scaffold-brain.sh"
if [ ! -x "$scaffold" ]; then
  printf "scaffold helper not found: %s\n" "$scaffold" >&2
  exit 1
fi
bash "$scaffold" "$abs" >/dev/null

# Persist.
config_file=${BRAIN_VAULT_CONFIG:-}
if [ -z "$config_file" ]; then
  repo_root=$(cd "$script_dir/../../.." && pwd)
  config_file="$repo_root/.vault-path"
fi
config_dir=$(dirname "$config_file")
mkdir -p "$config_dir"
printf '%s\n' "$abs" > "$config_file"

printf '%s\n' "$abs"
