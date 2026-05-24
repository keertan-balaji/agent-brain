#!/usr/bin/env bash
# brain-ingest-contextual: thin wrapper around `brain ingest`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <prepare-contexts|finalize-contexts> [args...]\n" "$0" >&2
  exit 1
fi

exec brain ingest "$@"
