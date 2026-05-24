#!/usr/bin/env bash
# brain-promote-answer: thin wrapper around `brain promote-answer`. All args passthrough.

set -euo pipefail

if [ $# -lt 1 ]; then
  printf "usage: %s <cache_key_hex> [--kind faq] [--yes]\n" "$0" >&2
  exit 1
fi

exec brain promote-answer "$@"
