#!/usr/bin/env bash
# resolve-vault.sh
# Prints the resolved Obsidian vault path on stdout.
# Resolution order (first hit wins):
#   1. $OBSIDIAN_VAULT environment variable
#   2. Persisted choice in $BRAIN_VAULT_CONFIG (default: <brain-repo>/.vault-path)
#   3. Default: $HOME/Documents/ObsidianVault
#
# Does not validate the path exists. Callers may layer their own checks.

set -uo pipefail

if [ -n "${OBSIDIAN_VAULT:-}" ]; then
  printf '%s\n' "$OBSIDIAN_VAULT"
  exit 0
fi

config_file=${BRAIN_VAULT_CONFIG:-}
if [ -z "$config_file" ]; then
  script_dir=$(cd "$(dirname "$0")" && pwd)
  repo_root=$(cd "$script_dir/../../.." && pwd)
  config_file="$repo_root/.vault-path"
fi

if [ -f "$config_file" ]; then
  saved=$(head -n1 "$config_file" | tr -d '\r\n' || true)
  if [ -n "$saved" ]; then
    printf '%s\n' "$saved"
    exit 0
  fi
fi

printf '%s\n' "$HOME/Documents/ObsidianVault"
