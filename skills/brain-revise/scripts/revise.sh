#!/usr/bin/env bash
# brain-revise: thin wrapper around `brain revise`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <prepare|finalize> [args...]\n" "$0" >&2
  exit 1
fi

exec brain revise "$@"
