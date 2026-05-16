#!/usr/bin/env bash
# recall-search.sh <vault-path> <query> [max-hits]
# Searches vault for query, ranks by section priority, prints up to max-hits paths to stdout.
# Output: one absolute path per line, ordered by priority.
# Priority: knowledge/ > projects/ > agent-memory/ > daily/ > everything else.

set -euo pipefail

vault=${1:-}
query=${2:-}
max=${3:-5}

if [ -z "$vault" ] || [ -z "$query" ]; then
  printf "usage: %s <vault-path> <query> [max-hits]\n" "$0" >&2
  exit 1
fi

if [ ! -d "$vault" ]; then
  printf "vault not found: %s\n" "$vault" >&2
  exit 1
fi

matches=$(rg --files-with-matches --type md --ignore-case --fixed-strings -- "$query" "$vault" 2>/dev/null || true)

if [ -z "$matches" ]; then
  exit 0
fi

score_path() {
  local p=$1
  case "$p" in
    */knowledge/*) printf "0\t%s\n" "$p" ;;
    */projects/*)  printf "1\t%s\n" "$p" ;;
    */agent-memory/*) printf "2\t%s\n" "$p" ;;
    */daily/*) printf "3\t%s\n" "$p" ;;
    *) printf "4\t%s\n" "$p" ;;
  esac
}

while IFS= read -r line; do
  score_path "$line"
done <<< "$matches" | sort -k1,1n -k2,2 | cut -f2- | head -n "$max"
