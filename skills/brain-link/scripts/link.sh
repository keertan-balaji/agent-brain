#!/usr/bin/env bash
# brain-link: thin wrapper around `brain link`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <source_id> [-k 5]\n" "$0" >&2
  exit 1
fi

exec brain link "$@"
