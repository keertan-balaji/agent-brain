#!/usr/bin/env bash
# resolve-brain.sh
# Prints the path of the agent's namespace inside the user's vault.
# Resolution: <resolve-vault.sh output>/$BRAIN_SUBDIR (default: Agent-Brain).
#
# This is the path every operational obsidian-* script writes into. The vault
# root (everything outside Agent-Brain/) is the user's territory and must not
# be touched by skills.

set -uo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
vault=$(bash "$script_dir/resolve-vault.sh")
brain_subdir=${BRAIN_SUBDIR:-Agent-Brain}
printf '%s/%s\n' "$vault" "$brain_subdir"
