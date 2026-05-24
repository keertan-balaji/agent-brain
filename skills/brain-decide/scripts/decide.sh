#!/usr/bin/env bash
# brain-decide: thin wrapper around `brain decide`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf 'usage: %s "<title>" [--project <slug>]\n' "$0" >&2
  exit 1
fi

exec brain decide "$@"
