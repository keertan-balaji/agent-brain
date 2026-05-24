#!/usr/bin/env bash
# brain-summarize: thin wrapper around `brain summarize`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <prepare|finalize> [args...]\n" "$0" >&2
  exit 1
fi

exec brain summarize "$@"
