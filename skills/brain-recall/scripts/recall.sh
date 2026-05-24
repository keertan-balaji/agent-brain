#!/usr/bin/env bash
# brain-recall: thin wrapper to `brain recall`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <query> [recall flags]\n" "$0" >&2
  exit 1
fi

exec brain recall "$@"
